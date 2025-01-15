import logging
from prometheus_client import start_http_server
import time
import csv

from poly_market_maker.args import get_args
from poly_market_maker.price_feed import PriceFeedClob
from poly_market_maker.gas import GasStation, GasStrategy
from poly_market_maker.utils import setup_logging, setup_web3
from poly_market_maker.order import Order, Side
from poly_market_maker.market import Market
from poly_market_maker.types import Token, Collateral
from poly_market_maker.clob_api import ClobApi
from poly_market_maker.lifecycle import Lifecycle
from poly_market_maker.orderbook import OrderBookManager
from poly_market_maker.contracts import Contracts
from poly_market_maker.metrics import keeper_balance_amount
from poly_market_maker.strategy import StrategyManager
from poly_market_maker.gamma_api import GammaMarketClient

from selenium import webdriver
from selenium.webdriver.common.by import By


class AppFrontRun:
    """Sports betting front running on Polymarket CLOB"""

    def __init__(self, args: list):
        setup_logging()
        self.logger = logging.getLogger(__name__)

        args = get_args(args)
        self.sync_interval = args.sync_interval

        # self.min_tick = args.min_tick
        # self.min_size = args.min_size

        # server to expose the metrics.
        self.metrics_server_port = args.metrics_server_port
        start_http_server(self.metrics_server_port)

        self.web3 = setup_web3(args.rpc_url, args.private_key)
        self.address = self.web3.eth.account.from_key(args.private_key).address

        self.clob_api = ClobApi(
            host=args.clob_api_url,
            chain_id=self.web3.eth.chain_id,
            private_key=args.private_key,
        )

        self.gas_station = GasStation(
            strat=GasStrategy(args.gas_strategy),
            w3=self.web3,
            url=args.gas_station_url,
            fixed=args.fixed_gas_price,
        )
        self.contracts = Contracts(self.web3, self.gas_station)

        self.market = Market(
            args.condition_id,
            self.clob_api.get_collateral_address(),
        )

        self.price_feed = PriceFeedClob(self.market, self.clob_api)

        self.order_book_manager = OrderBookManager(
            args.refresh_frequency, max_workers=1
        )
        self.order_book_manager.get_orders_with(self.get_orders)
        self.order_book_manager.get_balances_with(self.get_balances)
        self.order_book_manager.cancel_orders_with(
            lambda order: self.clob_api.cancel_order(order.id)
        )
        self.order_book_manager.place_orders_with(self.place_order)
        self.order_book_manager.cancel_all_orders_with(
            lambda _: self.clob_api.cancel_all_orders()
        )
        self.order_book_manager.start()

        # Initialize the WebDriver
        self.game_id = "401705126"
        self.driver = webdriver.Chrome()
        self.driver.get(f"https://www.espn.com/nba/game/_/gameId/{self.game_id}")

        self.gamma_api = GammaMarketClient()
        # self.active_markets = self.clob_api.get_current_nba_markets()
        self.active_markets = [
            mkt
            for mkt in self.gamma_api.get_current_nba_markets()
            if mkt.slug == "nba-bkn-por-2025-01-14"
        ]

    """
    main
    """

    def main(self):
        # Define the CSV filename
        csv_filename = f"game_data_{self.game_id}.csv"

        # Define the header for the CSV file
        header = [
            "Timestamp",
            "Scores",
            "Market",
            "Price0",
            "Price1",
            "Order Book Bids",
            "Order Book Asks",
        ]

        # Check if the CSV file already exists to avoid rewriting the header
        file_exists = False
        try:
            with open(csv_filename, "r"):
                file_exists = True
        except FileNotFoundError:
            pass

        # Open the CSV file in append mode
        with open(csv_filename, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=header)

            # Write the header if the file doesn't already exist
            if not file_exists:
                writer.writeheader()

            prev_scores_dict = {}

            # Continuous data collection
            while True:
                # Collect scores
                scores = self.driver.find_elements(By.CLASS_NAME, "Gamestrip__Score")
                scores_dict = {
                    f"Score {idx + 1}": score.text for idx, score in enumerate(scores)
                }
                if scores_dict == prev_scores_dict:
                    continue
                prev_scores_dict = scores_dict

                # Iterate over active markets and log data
                for mkt in self.active_markets:
                    price0 = self.clob_api.get_price(mkt.clobTokenIds[0])
                    price1 = self.clob_api.get_price(mkt.clobTokenIds[1])
                    orderBook = self.clob_api.client.get_order_book(mkt.clobTokenIds[0])

                    # Format bids and asks as strings
                    bids = [
                        {"price": bid.price, "size": bid.size} for bid in orderBook.bids
                    ]
                    asks = [
                        {"price": ask.price, "size": ask.size} for ask in orderBook.asks
                    ]

                    # Prepare the row of data to write
                    row = {
                        "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "Scores": str(scores_dict),
                        "Market": mkt.slug,
                        "Price0": price0,
                        "Price1": price1,
                        "Order Book Bids": str(bids),
                        "Order Book Asks": str(asks),
                    }
                    writer.writerow(row)

                # Wait 0.5 seconds before the next iteration
                time.sleep(0.5)

    """
    lifecycle
    """

    def startup(self):
        self.logger.info("Running startup callback...")
        self.approve()
        time.sleep(5)  # 5 second initial delay so that bg threads fetch the orderbook
        self.logger.info("Startup complete!")

    def synchronize(self):
        """
        Synchronize the orderbook by cancelling orders out of bands and placing new orders if necessary
        """
        self.logger.debug("Synchronizing ...")

        self.logger.debug("Synchronized !")

    def shutdown(self):
        """
        Shut down the keeper
        """
        self.logger.info("Keeper shutting down...")
        self.order_book_manager.cancel_all_orders()
        self.logger.info("Keeper is shut down!")

    """
    handlers
    """

    def get_balances(self) -> dict:
        """
        Fetch the onchain balances of collateral and conditional tokens for the keeper
        """
        self.logger.debug(f"Getting balances for address: {self.address}")

        collateral_balance = self.contracts.token_balance_of(
            self.clob_api.get_collateral_address(), self.address
        )
        token_A_balance = self.contracts.token_balance_of(
            self.clob_api.get_conditional_address(),
            self.address,
            self.market.token_id(Token.A),
        )
        token_B_balance = self.contracts.token_balance_of(
            self.clob_api.get_conditional_address(),
            self.address,
            self.market.token_id(Token.B),
        )
        gas_balance = self.contracts.gas_balance(self.address)

        keeper_balance_amount.labels(
            accountaddress=self.address,
            assetaddress=self.clob_api.get_collateral_address(),
            tokenid="-1",
        ).set(collateral_balance)
        keeper_balance_amount.labels(
            accountaddress=self.address,
            assetaddress=self.clob_api.get_conditional_address(),
            tokenid=self.market.token_id(Token.A),
        ).set(token_A_balance)
        keeper_balance_amount.labels(
            accountaddress=self.address,
            assetaddress=self.clob_api.get_conditional_address(),
            tokenid=self.market.token_id(Token.B),
        ).set(token_B_balance)
        keeper_balance_amount.labels(
            accountaddress=self.address,
            assetaddress="0x0",
            tokenid="-1",
        ).set(gas_balance)

        return {
            Collateral: collateral_balance,
            Token.A: token_A_balance,
            Token.B: token_B_balance,
        }

    def get_orders(self) -> list[Order]:
        orders = self.clob_api.get_orders(self.market.condition_id)
        return [
            Order(
                size=order_dict["size"],
                price=order_dict["price"],
                side=Side(order_dict["side"]),
                token=self.market.token(order_dict["token_id"]),
                id=order_dict["id"],
            )
            for order_dict in orders
        ]

    def place_order(self, new_order: Order) -> Order:
        order_id = self.clob_api.place_order(
            price=new_order.price,
            size=new_order.size,
            side=new_order.side.value,
            token_id=self.market.token_id(new_order.token),
        )
        return Order(
            price=new_order.price,
            size=new_order.size,
            side=new_order.side,
            id=order_id,
            token=new_order.token,
        )

    def approve(self):
        """
        Approve the keeper on the collateral and conditional tokens
        """
        collateral = self.clob_api.get_collateral_address()
        conditional = self.clob_api.get_conditional_address()
        exchange = self.clob_api.get_exchange()

        self.contracts.max_approve_erc20(collateral, self.address, exchange)
        self.contracts.max_approve_erc1155(conditional, self.address, exchange)
