import pandas as pd
import plotly.express as px
import pyrchidekt as pydk
from pyrchidekt.api import getDeckById
from pyrchidekt.deck import Deck
from pathlib import Path
import numpy as np
import requests
import plotly.graph_objects as go
# Color combo name mapping for Magic: The Gathering
# Keys are frozensets of full color names (case-insensitive when looked up).
COLOR_COMBO_NAMES = {
    # Mono-colors
    frozenset(["White"]): "White",
    frozenset(["Blue"]): "Blue",
    frozenset(["Black"]): "Black",
    frozenset(["Red"]): "Red",
    frozenset(["Green"]): "Green",

    # Two-color guilds (unordered)
    frozenset(["White", "Blue"]): "Azorius",
    frozenset(["Blue", "Black"]): "Dimir",
    frozenset(["Black", "Red"]): "Rakdos",
    frozenset(["Red", "Green"]): "Gruul",
    frozenset(["Green", "White"]): "Selesnya",
    frozenset(["White", "Black"]): "Orzhov",
    frozenset(["Blue", "Red"]): "Izzet",
    frozenset(["Black", "Green"]): "Golgari",
    frozenset(["Red", "White"]): "Boros",
    frozenset(["Green", "Blue"]): "Simic",

    # Three-color "shard" names
    frozenset(["White", "Green", "Blue"]): "Bant",
    frozenset(["White", "Blue", "Black"]): "Esper",
    frozenset(["Blue", "Black", "Red"]): "Grixis",
    frozenset(["Black", "Red", "Green"]): "Jund",
    frozenset(["Red", "Green", "White"]): "Naya",

    # Three-color "wedge" names (Khans)
    frozenset(["White", "Black", "Green"]): "Abzan",
    frozenset(["White", "Blue", "Red"]): "Jeskai",
    frozenset(["Blue", "Black", "Green"]): "Sultai",
    frozenset(["White", "Black", "Red"]): "Mardu",
    frozenset(["Blue", "Red", "Green"]): "Temur",

    #Four Color Names 
    frozenset(["Blue", "Red", "Green", "Black"]): "No-White",
    frozenset(["Blue", "Red", "White", "Black"]): "No-Green",
    frozenset(["Blue", "Green", "White", "Black"]): "No-Red",
    frozenset(["Green", "Red", "White", "Black"]): "No-Blue",
    frozenset(["Blue", "Red", "White", "Green"]): "No-Black",

    #Five-color
    frozenset(["White", "Blue", "Black", "Red", "Green"]): "Five-color (WUBRG)",
}

def get_combo_name(colors):
    """
    Return a friendly name for a color combination.

    colors: iterable of color names (e.g., ['Red','Blue'] or ('Blue','red'))
    Returns: string like 'Izzet', 'Bant', 'Four-color (no White)', or 'Five-color'
    """
    if colors is None:
        return None
    # normalize input to capitalized color names
    normalized = {c.strip().capitalize() for c in colors if c and str(c).strip()}
    if not normalized:
        return None

    # direct lookup (mono/2/3-color known names)
    key = frozenset(normalized)
    if key in COLOR_COMBO_NAMES:
        return COLOR_COMBO_NAMES[key]

    # four-color -> identify the missing color
    all_colors = {"White", "Blue", "Black", "Red", "Green"}
    if len(normalized) == 4:
        missing = (all_colors - normalized).pop()
        return f"Four-color (no {missing})"

    # five-color
    if len(normalized) == 5:
        return "Five-color (WUBRG)"

    # fallback: return sorted letter codes (WUBRG) and a readable form
    letter_map = {"White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G"}
    letters = "".join(sorted(letter_map[c] for c in normalized))
    names = "/".join(sorted(normalized))
    return f"{names} ({letters})"

def calculate_deck_stats(deck: Deck, player, card_stats):
    stats = {"player": player, "mdfc": 0}
    cat_dict = {category.name: category for category in deck.categories}
    total_price = 0
    total_nonland = 0
    mana_value = []
    commander_identity = []
    for card in deck.cards:
        oracle = card.card.oracle_card
        types = oracle.types
        for type in types:
            if type not in stats:
                stats[type] = 0
            stats[type] += card.quantity
        if oracle.layout == "modal_dfc":
            stats["mdfc"] += card.quantity
        if card.card.prices["tcg"] > 0:
            price = card.card.prices["tcg"]
        elif card.card.prices["ck"] > 0:
            price = card.card.prices["ck"]
        else:
            price = card.card.prices["tcgfoil"]
        total_price += price
        if "Land" not in types:
            total_nonland += price
            mana_value.append(oracle.cmc)
            card_stats.append(
                {
                    "name": oracle.name,
                    "price": price,
                    "count": card.quantity,
                    "identity": oracle.color_identity,
                    "mv": oracle.cmc,
                    "type": types,
                    "mdfc": oracle.layout == "modal_dfc",
                    "category": oracle.default_category,
                    "player": player,
                }
            )
        for color in oracle.color_identity:
            if color not in commander_identity:
                commander_identity.append(color)
    stats["identity"] = commander_identity
    stats["total_price"] = total_price
    stats["total_non_land"] = total_nonland
    stats["lands_mdfc"] = stats["mdfc"] + stats["Land"]

    #     for face in oracle.faces[1:]:
    #         if face.type not in stats:
    #             stats[face.name] = 0
    #         stats[face.name] += 1
    # for card in deck.cards:
    #     if card.name not in card_counter:
    #         card_counter[card.name] = 0
    ## Color identity
    return stats, card_stats


# filepath: c:\Users\neilf\Documents\code\parse_games_to_dataframe.py
def parse_games_to_dataframe(file_path):
    data = []
    current_game = None

    with open(file_path, "r") as file:
        lines = file.readlines()

    for line in lines:
        row = line.strip().split(",")
        if row[0].startswith("Game"):
            current_game = row[0]
            players = row[1:]
        elif row[0] == "Decklist":
            decklists = row[1:]
        elif row[0] == "Turn Order":
            turn = row[1:]
        elif row[0] == "Placement":
            placements = row[1:]
        elif row[0] == "Time of win":
            time_of_win = row[1:]
        elif row[0] == "Turn of exit":
            turn_of_exit = row[1:]
        elif row[0] == "# Lands":
            lands = row[1:]
        elif row[0] == "Deck Count":
            deck_counts = row[1:]
        elif row[0] == "Comm Casts":
            commander_casts = row[1:]
            # Add data for each player in the current game
            for i, player in enumerate(players):
                if player:  # Ensure the player field is not empty
                    data.append(
                        {
                            "Game": current_game,
                            "Player": player,
                            "Decklist": decklists[i] if i < len(decklists) else None,
                            "Placement": placements[i] if i < len(placements) else None,
                            "Turn Order": turn[i] if i < len(turn) else None,
                        }
                    )

    # Convert the data into a Pandas DataFrame
    df = pd.DataFrame(data)
    return df


# Example usage
curr_season = 3
output_dir = Path(r"C:\Users\neilf\Documents\Code\clash")
file_path = output_dir / f"Commander TTS Stats - Season {curr_season}.csv"
npz_path = output_dir / f"season{curr_season}_decks.npy"
df = parse_games_to_dataframe(file_path)
figures_dir =  output_dir / 'figures' / f'Season{curr_season}'
if not figures_dir.exists():
    figures_dir.mkdir(parents=True)
# print(len(df))
# Display the DataFrame
# print(df)

# Save to a CSV file if needed
# df.to_csv(output_path, index=False)
# base_stats = True
# placement_stats = True
# deck_stats = True
# card_stats = []


def calculate_base_stats(season, graph_decks=True, no_figure=True):
    card_stats = []
    for stat in df.columns:
        if stat in ["Game", "Player", "Decklist"]:
            if stat == "Decklist":
                if graph_decks:
                    df["deck_id"] = df[stat].apply(
                        lambda x: (
                            int(x.split("/")[4])
                            if (isinstance(x, str) and len(x.split("/")) > 3)
                            else x
                        )
                    )
                    if npz_path.exists():
                        print("found decks downloaded")
                        df["decks"] = np.load(npz_path, allow_pickle=True)
                    else:
                        print("No decks found")
                        df["decks"] = df["deck_id"].apply(
                            lambda x: getDeckById(x) if isinstance(x, int) else x
                        )
                        np.save(npz_path, df["decks"].tolist())

                    deck_stats_list = []
                    for index in range(len(df)):
                        row = df.iloc[index]
                        deck = row["decks"]
                        if isinstance(deck, Deck):
                            single_deck_stats, card_stats = calculate_deck_stats(
                                deck, row["Player"], card_stats
                            )
                            deck_stats_list.append(single_deck_stats)
                    deck_stats = pd.DataFrame(deck_stats_list).fillna(0)
                # df[stat] = df[stat].apply(lambda x: pydk.Deck.fromJson(x).name if isinstance(x, str) else x)
        else:
            graph_stat = {"player": [], stat: []}
            for player in df.Player.unique():
                if player in df[stat].values:
                    dat = df.loc[df["Player"] == player, stat]
                else:
                    dat = df.loc[df["Player"] == player, stat]
                dat = dat[dat != ""]
                graph_stat["player"].append(player)
                if len(dat.dropna().values.astype(int)) > 0:
                    graph_stat[stat].append(dat.dropna().values.astype(int).mean())
                else:
                    graph_stat[stat].append(0)
                graph_df = pd.DataFrame(graph_stat)
            if not no_figure:
                fig = px.bar(
                    graph_df,
                    x="player",
                    y=stat,
                    color="player",
                    title=f"{stat} by Player",
                )
                fig.write_image(f"figures/Season{season}/{stat}.png")

        placement_stats = []

        for player in df.Player.unique():
            finishes = df.loc[df["Player"] == player, "Placement"].astype(int)
            finishes[finishes > 4] = 4
            total_len = len(finishes)
            if total_len > 2:
                for idx in range(1, 5):
                    placement_stats.append(
                        {
                            "Player": player,
                            "placement": idx,
                            "Finish Percentage": finishes[finishes == idx].count()
                            * 100
                            / total_len,
                            "count": finishes[finishes == idx].count(),
                            "value_str": f"{finishes[finishes == idx].count()} / {total_len}",
                        }
                    )
        turn_stats = []
        for player in df.Player.unique():
            turn = df.loc[df["Player"] == player, "Turn Order"].replace('', np.nan).dropna().astype(int)
            total_len = len(turn)
            if total_len > 2:
                for idx in range(1, 5):
                    turn_stats.append(
                        {
                            "Player": player,
                            "turn": idx,
                            "Finish Percentage": turn[turn == idx].count()
                            * 100
                            / total_len,
                            "count": turn[turn == idx].count(),
                            "value_str": f"{turn[turn == idx].count()} / {total_len}",
                        }
                    )
    return pd.DataFrame(placement_stats), pd.DataFrame(turn_stats), deck_stats, pd.DataFrame(card_stats)


def graph_count_stats(graph_df, season, keyword='placement'):
    for placement in range(1, 5):
        # fig = px.bar(
        #     graph_df[graph_df["placement"] == placement],
        #     x="player",
        #     y="count",
        #     color="player",
        #     title=f"Finishes {placement}",
        # )
        # # fig.update_layout(yaxis_range=(0, 8))
        # print("writing image")
        # fig.write_image(Path(f"Season{season}_placement_{placement}_raw.png"))
        fig = px.bar(
            graph_df[graph_df[keyword] == placement],
            x="Player",
            y="Finish Percentage",
            color="Player",
            text="value_str",
            title=f"{keyword} {placement} Finishes",
        )
        # fig.update_layout(yaxis_range=(0, 1))
        fig.update(layout_showlegend=False)

        fig.write_image(f"figures/Season{season}/{keyword}_{placement}.png")


def graph_deck_stats(graph_df, season):
    deck_graph_data = []
    graph_df['color_identity'] = graph_df['identity'].apply(get_combo_name)
    identity_choices = graph_df['color_identity'].value_counts()
    for idx in COLOR_COMBO_NAMES.values():
        if idx not in identity_choices:
            identity_choices[idx] = 0
    identity_df = identity_choices.to_frame().rename(columns={0: 'Count'})
    
    # Split into two columns
    mid_point = len(identity_df) // 2
    col1 = identity_df.iloc[:mid_point]
    col2 = identity_df.iloc[mid_point:]
    
    # Create HTML with two columns
    html_content = """
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .two-column {{ display: flex; gap: 40px; }}
            table {{ border-collapse: collapse; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #4CAF50; color: white; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <h2>Color Identity Distribution - Season {season}</h2>
        <div class="two-column">
            {col1}
            {col2}
        </div>
    </body>
    </html>
    """.format(
        season=season,
        col1=col1.to_html(classes='table table-striped', border=0),
        col2=col2.to_html(classes='table table-striped', border=0)
    )
    
    with open(figures_dir / f'identity_choices_Season{season}.html', 'w') as f:
        f.write(html_content)
    for player in graph_df.player.unique():
        player_data = graph_df[graph_df["player"] == player]
        if len(player_data) > 2:
            player_color_counter = {}
            player_stats = {"player": player}
            for stat_count in [
                "Instant",
                "Creature",
                "Sorcery",
                "Artifact",
                "Land",
                "Enchantment",
                "mdfc",
                "Planeswalker",
                "Battle",
                "total_price",
                "total_non_land",
            ]:
                if stat_count in player_data:
                    stat_mean = player_data[stat_count].mean()
                else:
                    stat_mean = 0
                player_stats[stat_count] = stat_mean

            deck_graph_data.append(player_stats)
            player_identity_choices = player_data['color_identity'].value_counts()
            
            # Save player identity choices to two-column HTML
            player_identity_df = player_identity_choices.to_frame().rename(columns={0: 'Count'})
            mid_point = len(player_identity_df) // 2
            p_col1 = player_identity_df.iloc[:mid_point]
            p_col2 = player_identity_df.iloc[mid_point:]
            
            p_html_content = """
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .two-column {{ display: flex; gap: 40px; }}
                    table {{ border-collapse: collapse; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background-color: #4CAF50; color: white; }}
                    tr:nth-child(even) {{ background-color: #f2f2f2; }}
                </style>
            </head>
            <body>
                <h2>Color Identity Distribution - {player} - Season {season}</h2>
                <div class="two-column">
                    {col1}
                    {col2}
                </div>
            </body>
            </html>
            """.format(
                player=player,
                season=season,
                col1=p_col1.to_html(classes='table table-striped', border=0),
                col2=p_col2.to_html(classes='table table-striped', border=0)
            )
            
            with open(figures_dir / f'identity_choices_{player}_Season{season}.html', 'w') as f:
                f.write(p_html_content)

            for colors in player_data["identity"]:
                for color in colors:
                    if color not in player_color_counter:
                        player_color_counter[color] = 0
                    player_color_counter[color] += 1
            
            player_color_graph = [
                {"Color": k, "Percentage of time Played": (v * 100) / len(player_data)}
                for k, v in player_color_counter.items()
            ]
            color_dict = {x: x.lower() for x in player_color_counter.keys()}
            color_dict["White"] = "lightgoldenrodyellow"
            player_color_df = pd.DataFrame(player_color_graph)
            fig = px.bar(
                player_color_df,
                x="Color",
                y="Percentage of time Played",
                color="Color",
                category_orders={"Color": ["White", "Blue", "Black", "Red", "Green"]},
                color_discrete_map=color_dict,
                title=f"{player} Color Distribution",
            )
            fig.update(layout_showlegend=False)
            fig.write_image(f"figures/Season{season}/color_identity_{player}.png")
    deck_df = pd.DataFrame(deck_graph_data)
    for stat in ["total_price", "total_non_land"]:
        title_text_mapping = {
            "total_price": "Total Price",
            "total_non_land": "Total Non-Land Price",
            "player": "Player",
        }
        deck_df[stat] = deck_df[stat].astype(int)
        fig = px.bar(
            deck_df,
            x="player",
            y=stat,
            labels=title_text_mapping,
            color="player",
            text=stat,
            title=title_text_mapping[stat],
        )
        fig.update(layout_showlegend=False)

        # fig.update_layout(yaxis_range=(0, 1))
        fig.write_image(f"figures/Season{season}/placement_{stat}.png")


def graph_card_stats(card_df, deck_df, season):
    cat_df = pd.DataFrame([])
    color_df = pd.DataFrame([])
    for player in card_df.player.unique():
        player_card_df = card_df[card_df.player == player]
        num_games = len(deck_df[deck_df["player"] == player])
        if num_games > 2:
            card_counter_df = {}
            cat_counter_df = {}
            color_counter = {}
            for row in player_card_df.iterrows():
                card_name = row[1]["name"]
                if card_name not in card_counter_df:
                    card_counter_df[card_name] = {k: v for k, v in row[1].items()}
                else:
                    card_counter_df[card_name]["count"] += row[1]["count"]
                card_cat = row[1]["category"]
                if card_cat not in cat_counter_df:
                    cat_counter_df[card_cat] = {
                        "category": card_cat,
                        "Count Per Deck": row[1]["count"] / num_games,
                        "player": player,
                    }
                else:
                    cat_counter_df[card_cat]["Count Per Deck"] += (row[1]["count"] / num_games)
                if 'Land' not in row[1]['type']:
                    for color in row[1]['identity']:
                        if color not in color_counter:
                            color_counter[color] = {
                                "Color": color,
                                "Count Per Deck": row[1]["count"] / num_games,
                                "player": player,
                            }
                        else:
                            color_counter[color]["Count Per Deck"] += (row[1]["count"] / num_games)

            player_card_df = pd.DataFrame(card_counter_df.values())
            cat_df_player = pd.DataFrame(cat_counter_df.values())
            color_df_player = pd.DataFrame(color_counter.values())
            cat_df = pd.concat([cat_df,cat_df_player])
            color_df = pd.concat([color_df, color_df_player])
            ### Uncomment from here 
            # ========================================================
            for card_type in [
                "Creature",
                "Artifact",
                "Enchantment",
                "Instant",
                "Sorcery",
            ]:
                type_df = player_card_df.loc[
                    player_card_df["type"].apply(lambda x: card_type in x)
                ]
                type_df = type_df.sort_values("count", ascending=False)
                df = type_df.iloc[:14][["name", "count"]]
                fig = go.Figure(
                    data=[
                        go.Table(
                            columnwidth=[40, 10],
                            header=dict(
                                values=list(df.columns),
                                fill_color="paleturquoise",
                                align="left",
                            ),
                            cells=dict(
                                values=[df["name"], df["count"]],
                                fill_color="lavender",
                                align="left",
                            ),
                        )
                    ]
                )
                fig.update_layout({'title': f'{player} Most Played {card_type}'})
                fig.write_image(f"figures/Season{season}/{player}_{card_type}_most_played.png")
                # breakpoint()
    # for category in cat_df['category'].unique():
    #     data_category = cat_df[cat_df['category'] == category]
    #     fig = px.bar(
    #         data_category,
    #         x='player',
    #         y="Count Per Deck",
    #         color="player",
    #         title=f"{category} Comparison",
    #     )
    #     fig.update(layout_showlegend=False)
    #     fig.write_image(f"figures/Season{season}/category_{category}.png")
    
                    ## ========================================================
    color_dict = {x: x.lower() for x in color_df.Color.unique()}
    color_dict["White"] = "lightgoldenrodyellow"
    for player in color_df['player'].unique():
        player_color_df = color_df[color_df['player'] == player]
        fig = px.bar(
            player_color_df,
            x="Color",
            y="Count Per Deck",
            color="Color",
            category_orders={"Color": ["White", "Blue", "Black", "Red", "Green"]},
            color_discrete_map=color_dict,
            title=f"{player} Card Color Distribution",
        )
        fig.update(layout_showlegend=False)
        fig.write_image(f"figures/Season{season}/color_identity_cards_{player}.png")
    return False


graph_placement, graph_deck, graph_cards = True, True, True
placement_stats, turn_stats, deck_stats, card_stats = calculate_base_stats(curr_season, graph_decks=True, no_figure=False)


if graph_placement:
    graph_count_stats(placement_stats, curr_season)
    graph_count_stats(turn_stats, curr_season, keyword='turn')

if graph_deck:
    graph_deck_stats(deck_stats, curr_season)

if graph_cards:
    graph_card_stats(card_stats, deck_stats, curr_season)

