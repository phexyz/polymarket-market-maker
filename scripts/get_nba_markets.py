from poly_market_maker.gamma_api import GammaApi
from poly_market_maker.types import Market
from datetime import datetime, timedelta
import json
import re
import requests

# Map league to sport/league path for ESPN API
LEAGUE_TO_SPORT = {
    "nba": "basketball/nba",
    "nhl": "hockey/nhl",
    "nfl": "football/nfl",
    "mlb": "baseball/mlb",
}


def get_current_sports_markets(client: GammaApi, league: str) -> "list[Market]":
    """Get current sports markets from Polymarket for a given league"""
    end_date_max = (
        (datetime.now() + timedelta(days=9))
        .replace(hour=23, minute=59, second=59, microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    start_date_min = (
        (datetime.now() - timedelta(days=9))
        .replace(hour=23, minute=59, second=59, microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    querystring_params = {
        "start_date_min": start_date_min,
        "end_date_max": end_date_max,
        "active": True,
        "close": False,
        "limit": 10000,
    }

    markets = client.get_markets(
        querystring_params=querystring_params, parse_pydantic=True
    )

    # Current datetime
    current_time = datetime.now()
    current_date = current_time.date()

    def is_current_sports_market(mkt: Market):
        if not mkt.description:
            return False
        if league not in mkt.slug:
            return False
        start_time_pattern = r"(\w+ \d+ at \d{1,2}:\d{2}[AP]M ET)"
        match = re.search(start_time_pattern, mkt.description)
        if match:
            start_time_str = match.group(1)
            # Convert to datetime format
            start_time_str = (
                start_time_str.replace(" at", "").replace(" ET", "") + " 2025"
            )
            event_time = datetime.strptime(start_time_str, "%B %d %I:%M%p %Y")
            # Check if event is on the target date and after the current time
            return event_time.date() == current_date
        return False

    # Use filter to find valid events
    filtered_markets = filter(lambda mkt: is_current_sports_market(mkt), markets)

    # Convert to list to display results
    return list(filtered_markets)


def get_game_details(event):
    game_id = event.get("id", "Unknown ID")

    # Extract the teams
    competitors = event.get("competitions", [{}])[0].get("competitors", [])
    home_team_abbreviation = next(
        (
            team["team"].get("abbreviation", "Unknown")
            for team in competitors
            if team.get("homeAway") == "home"
        ),
        "Unknown Home Team",
    )
    away_team_abbreviation = next(
        (
            team["team"].get("abbreviation", "Unknown")
            for team in competitors
            if team.get("homeAway") == "away"
        ),
        "Unknown Away Team",
    )

    # Return the results
    return game_id, away_team_abbreviation.lower(), home_team_abbreviation.lower()


def get_matchups(league: str):
    # ESPN API endpoint for sports matchups
    if league not in LEAGUE_TO_SPORT:
        raise ValueError(f"Unsupported league: {league}")

    sport_path = LEAGUE_TO_SPORT[league]
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard"

    try:
        # Fetch the scoreboard data
        response = requests.get(url)
        response.raise_for_status()  # Raise exception for HTTP errors
        data = response.json()

        # Get the list of events (games)
        events = data.get("events", [])
        if not events:
            print(f"No {league.upper()} games found for today.")
            return []

        print(f"{league.upper()} Matchups for {datetime.now().strftime('%Y-%m-%d')}:")

        ret = []
        for event in events:
            res = get_game_details(event)
            ret.append(res)
        return ret
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {league.upper()} matchups: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []


def get_current_games(league: str):
    client = GammaApi()
    current_markets = get_current_sports_markets(client, league)

    # Get today's games from ESPN API
    games_data = get_matchups(league)

    print(f"\nCurrent {league.upper()} Markets from Polymarket:")
    print("-" * 80)
    for market in current_markets:
        print(f"Market: {market.description}")
        print(f"Slug: {market.slug}")
        print(f"Market ID: {market.id}")
        print()

    print(f"\n{league.upper()} Games from API:")
    print("-" * 80)
    for game_id, away_team, home_team in games_data:
        print(f"{away_team} @ {home_team}")
        print(f"Game ID: {game_id}")
        print()

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

            # Find matching game
            matching_game = None
            for game_id, away_team, home_team in games_data:
                # Check both combinations (home/away) for matching
                if (team1 == home_team and team2 == away_team) or (
                    team1 == away_team and team2 == home_team
                ):
                    matching_game = (game_id, away_team, home_team)
                    break

            if matching_game:
                game_id, away_team_code, home_team_code = matching_game
                market_id = market.id

                # Determine which team is home/away based on API data
                if team1 == home_team_code.lower():
                    home_team = home_team_code
                    away_team = away_team_code
                else:
                    home_team = home_team_code
                    away_team = away_team_code

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

    return game_data


def print_all_leagues_config():
    leagues = ["nba", "nhl", "nfl", "mlb"]
    all_game_data = {}

    for league in leagues:
        league_games = get_current_games(league)
        all_game_data[league] = league_games

    print("\nCombined Configuration for All Leagues:")
    print("-" * 80)

    for league, games in all_game_data.items():
        if games:
            print(f"\n{league.upper()} Games:")
            for game in games.values():
                print("\n{")
                print('    "game_id": "' + str(game["game_id"]) + '",')
                print('    "market_id": "' + str(game["market_id"]) + '",')
                print('    "home_team": "' + game["home_team"] + '",')
                print('    "away_team": "' + game["away_team"] + '",')
                print('    "poll_interval": 0.5')
                print("}")


if __name__ == "__main__":
    print_all_leagues_config()
