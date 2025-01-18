from poly_market_maker.gamma_api import GammaApi
from datetime import datetime
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.static import teams
import json


def get_team_mapping():
    """Get NBA team name to abbreviation mapping"""
    # Manual mapping for Polymarket slug names to NBA tricode
    special_cases = {
        "ind": "IND",  # Pacers
        "det": "DET",  # Pistons
        "phx": "PHX",  # Suns
        "was": "WAS",  # Wizards
        "cle": "CLE",  # Cavaliers
        "okc": "OKC",  # Thunder
        "lac": "LAC",  # Clippers
        "por": "POR",  # Trail Blazers
        "hou": "HOU",  # Rockets
        "sac": "SAC",  # Kings
        "nyk": "NYK",  # Knicks
        "gsw": "GSW",  # Warriors
        "nop": "NOP",  # Pelicans
        "sas": "SAS",  # Spurs
        "bos": "BOS",  # Celtics
        "tor": "TOR",  # Raptors
        "mem": "MEM",  # Grizzlies
        "atl": "ATL",  # Hawks
        "chi": "CHI",  # Bulls
        "orl": "ORL",  # Magic
        "mil": "MIL",  # Bucks
        "dal": "DAL",  # Mavericks
        "min": "MIN",  # Timberwolves
        "phi": "PHI",  # 76ers
        "den": "DEN",  # Nuggets
        "cha": "CHA",  # Hornets
        "uta": "UTA",  # Jazz
        "mia": "MIA",  # Heat
        "lal": "LAL",  # Lakers
        "bkn": "BKN",  # Nets
    }
    return special_cases


def get_current_nba_games():
    client = GammaApi()
    current_markets = client.get_current_nba_markets()

    # Get today's NBA games from NBA API
    board = scoreboard.ScoreBoard()
    games = board.get_dict()["scoreboard"]["games"]

    print("\nCurrent Markets from Polymarket:")
    print("-" * 80)
    for market in current_markets:
        print(f"Market: {market.description}")
        print(f"Slug: {market.slug}")
        print(f"Market ID: {market.id}")
        print()

    print("\nNBA Games from API:")
    print("-" * 80)
    for game in games:
        print(f"{game['awayTeam']['teamTricode']} @ {game['homeTeam']['teamTricode']}")
        print(f"Game ID: {game['gameId']}")
        print(f"Status: {game['gameStatus']}")
        print()

    # Get team mapping
    team_mapping = get_team_mapping()

    print("\nMatched Games:")
    print("-" * 80)

    game_data = {}
    for market in current_markets:
        # Extract teams from the market slug
        # Example slug: "nba-ind-det-2025-01-16"
        slug_parts = market.slug.split("-")
        if len(slug_parts) >= 4:  # Make sure we have enough parts
            team1 = slug_parts[1].lower()  # ind
            team2 = slug_parts[2].lower()  # det

            # Find matching NBA game
            matching_game = None
            for game in games:
                home_team = game["homeTeam"]["teamTricode"]
                away_team = game["awayTeam"]["teamTricode"]

                # Convert slug teams to uppercase for comparison
                team1_code = team_mapping.get(team1)
                team2_code = team_mapping.get(team2)

                # Check both combinations (home/away) for matching
                if (team1_code == home_team and team2_code == away_team) or (
                    team1_code == away_team and team2_code == home_team
                ):
                    matching_game = game
                    break

            if matching_game:
                game_id = matching_game["gameId"]
                market_id = market.id

                # Determine which team is home/away based on NBA API data
                if team_mapping.get(team1) == matching_game["homeTeam"]["teamTricode"]:
                    home_team = team_mapping.get(team1)
                    away_team = team_mapping.get(team2)
                else:
                    home_team = team_mapping.get(team2)
                    away_team = team_mapping.get(team1)

                game_data[game_id] = {
                    "game_id": game_id,
                    "market_id": market_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "poll_interval": 0.5,
                }

                print(f"\nGame ID: {game_id}")
                print(f"Market ID: {market_id}")
                print(f"Teams: {away_team} @ {home_team}")
                print(f"Description: {market.description}")
                print("-" * 80)

    # Save the game data to a file
    with open("game_market_mapping.json", "w") as f:
        json.dump(game_data, f, indent=4)

    print("\nSample front_run.json configuration:")
    print("-" * 80)
    for game in game_data.values():
        print("\n{")
        print('    "game_id": "' + str(game["game_id"]) + '",')
        print('    "market_id": "' + str(game["market_id"]) + '",')
        print('    "home_team": "' + game["home_team"] + '",')
        print('    "away_team": "' + game["away_team"] + '",')
        print('    "poll_interval": 0.5')
        print("}")

    print("\nFull game data has been saved to game_market_mapping.json")


if __name__ == "__main__":
    get_current_nba_games()
