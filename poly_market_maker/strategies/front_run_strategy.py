from dataclasses import dataclass
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium import webdriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import csv
import time
from poly_market_maker.strategies.base_strategy import BaseStrategy
from poly_market_maker.gamma_api import GammaApi
from poly_market_maker.clob_api import ClobApi
from poly_market_maker.types import MarketState, Token
from poly_market_maker.orderbook import Order


@dataclass
class FrontRunConfig:
    game_id: str
    market_id: str
    poll_interval: float = 0.5  # Default polling interval in seconds


class FrontRunStrategy(BaseStrategy):
    def __init__(
        self,
        config_dict: dict,
        gamma_api: GammaApi,
        clob_api: ClobApi,
    ):
        assert isinstance(config_dict, dict)
        print("FrontRunStrategy initialized")

        super().__init__()
        config = self._get_config(config_dict)
        self.game_id = config.game_id
        self.market_id = config.market_id
        self.home_team = "HOME"
        self.away_team = "AWAY"
        self.poll_interval = config.poll_interval

        self.gamma_api = gamma_api
        self.clob_api = clob_api
        self.market = self._get_market()

        # Initialize Chrome WebDriver
        self.driver = webdriver.Chrome()
        self.driver.get(f"https://www.espn.com/nba/game/_/gameId/{self.game_id}")
        self.wait = WebDriverWait(
            self.driver,
            timeout=10,
            poll_frequency=self.poll_interval,
            ignored_exceptions=(StaleElementReferenceException,),
        )

        # Initialize score state
        self.current_scores = {"home": None, "away": None, "last_update": None}

        # Initialize CSV file
        self.csv_filename = f"game_data_{self.game_id}.csv"
        self._initialize_csv()

    def _initialize_csv(self):
        """Initialize CSV file with headers"""
        self.header = [
            "Timestamp",
            f"{self.away_team}_Score",
            f"{self.home_team}_Score",
            f"{self.away_team}_Price",
            f"{self.home_team}_Price",
            f"{self.away_team}_Order_Book_Bids",
            f"{self.away_team}_Order_Book_Asks",
            "Score_Changed",
            "Spread",
            "Mid_Price_Away",
            "Mid_Price_Home",
            "Balance_Token_Away",
            "Balance_Token_B",
        ]

        # Create file with headers if it doesn't exist
        try:
            with open(self.csv_filename, "r"):
                pass
        except FileNotFoundError:
            with open(
                self.csv_filename, mode="w", newline="", encoding="utf-8"
            ) as file:
                writer = csv.DictWriter(file, fieldnames=self.header)
                writer.writeheader()

    def _get_market(self):
        """Get market from gamma API using market_id"""
        if not self.gamma_api:
            raise ValueError("gamma_api is required but not provided")

        # Query the market using market_id
        markets = self.gamma_api.get_markets(querystring_params={"id": self.market_id})
        if not markets or len(markets) == 0:
            return None
        market = markets[0]
        if not market:
            raise ValueError(f"No market found with ID {self.market_id}")

        return market

    @staticmethod
    def _get_config(config: dict):
        return FrontRunConfig(
            game_id=config.get("game_id"),
            market_id=config.get("market_id"),
            poll_interval=config.get("poll_interval", 0.5),
        )

    def get_orders(self, market_state: MarketState) -> tuple[list[Order], list[Order]]:
        """
        Process current market state and collect game data
        Returns: Empty orders since this is a data collection strategy
        """
        # Get current scores
        new_scores = self._get_scores()
        score_changed = self._scores_changed(new_scores)

        # Prepare the row of data to write
        row = {
            "Timestamp": market_state.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            f"{self.away_team}_Score": new_scores["away"],
            f"{self.home_team}_Score": new_scores["home"],
            f"{self.away_team}_Price": market_state.away_team_price,
            f"{self.home_team}_Price": market_state.home_team_price,
            f"{self.away_team}_Order_Book_Bids": str(
                [
                    {"price": b.price, "size": b.size}
                    for b in market_state.away_team_bids
                ]
            ),
            f"{self.away_team}_Order_Book_Asks": str(
                [
                    {"price": a.price, "size": a.size}
                    for a in market_state.away_team_asks
                ]
            ),
            "Score_Changed": score_changed,
            "Spread": market_state.spread,
            "Mid_Price_Away": market_state.away_team_mid_price,
            "Mid_Price_Home": market_state.home_team_mid_price,
            "Balance_Token_Away": market_state.balances[Token.A],
            "Balance_Token_B": market_state.balances[Token.B],
        }

        # Write to CSV
        with open(self.csv_filename, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.header)
            writer.writerow(row)

        if score_changed:
            print(f"\nScore Update at {market_state.timestamp}:")
            print(f"{self.away_team}: {new_scores['away']}")
            print(f"{self.home_team}: {new_scores['home']}")
            print(f"Away Team Price: {market_state.away_team_price}")
            print(f"Home Team Price: {market_state.home_team_price}")
            print(f"Spread: {market_state.spread}")

        return [], []

    def _get_scores(self):
        """Get current scores using WebDriverWait and parse them"""
        default_scores = {
            "away": None,
            "home": None,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            # Wait for score elements to be present
            score_elements = self.wait.until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "Gamestrip__Score"))
            )

            if len(score_elements) >= 2:
                away_score = score_elements[0].text.strip()
                home_score = score_elements[1].text.strip()

                return {
                    "away": away_score,
                    "home": home_score,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            return default_scores
        except TimeoutException:
            return default_scores

    def _scores_changed(self, new_scores):
        """Check if scores have changed"""
        if not new_scores:
            return False

        changed = (
            new_scores["home"] != self.current_scores["home"]
            or new_scores["away"] != self.current_scores["away"]
        )

        if changed:
            self.current_scores = {
                "home": new_scores["home"],
                "away": new_scores["away"],
                "last_update": new_scores["timestamp"],
            }

        return changed
