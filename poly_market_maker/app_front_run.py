import logging
from prometheus_client import start_http_server
import time
import csv
import json

from py_clob_client.clob_types import OrderType

from poly_market_maker.args import get_args
from poly_market_maker.gas import GasStation, GasStrategy
from poly_market_maker.utils import setup_logging, setup_web3
from poly_market_maker.types import Token, Collateral, Order, Side
from poly_market_maker.clob_api import ClobApi
from poly_market_maker.lifecycle import Lifecycle
from poly_market_maker.orderbook import OrderManager
from poly_market_maker.contracts import Contracts
from poly_market_maker.metrics import keeper_balance_amount
from poly_market_maker.strategy import StrategyManager
from poly_market_maker.gamma_api import GammaApi

from selenium import webdriver
from selenium.webdriver.common.by import By


class AppFrontRun:
    """Sports betting front running on Polymarket CLOB"""

    def __init__(self, args: list):
        setup_logging(args.market_id)
        self.logger = logging.getLogger(__name__)

        args = get_args(args)
        self.sync_interval = 0.5

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
        self.gamma_api = GammaApi()

        self.gas_station = GasStation(
            strat=GasStrategy(args.gas_strategy),
            w3=self.web3,
            url=args.gas_station_url,
            fixed=args.fixed_gas_price,
        )
        self.contracts = Contracts(self.web3, self.gas_station)

        self.market = self.gamma_api.get_markets(
            querystring_params={"id": args.market_id}
        )[0]

        self.order_book_manager = OrderManager(args.refresh_frequency, max_workers=1)
        self.order_book_manager.get_orders_with(self.get_orders)
        self.order_book_manager.get_balances_with(self.get_balances)
        self.order_book_manager.cancel_orders_with(
            lambda order: self.clob_api.cancel_order(order.id)
        )
        self.order_book_manager.place_orders_with(self.place_order)

        self.order_book_manager.cancel_all_orders_with(
            lambda _: self.clob_api.cancel_all_orders()
        )
        # self.order_book_manager.clear_all_positions_with(self.clear_all_positions)
        self.order_book_manager.start()

        with open(args.strategy_config) as fh:
            strategy_config = json.load(fh)
        self.logger.info(f"Strategy config: {strategy_config}")

        self.strategy_manager = StrategyManager(
            args.strategy,
            strategy_config,
            self.order_book_manager,
            self.gamma_api,
            self.clob_api,
            self.market,
        )

    """
    main
    """

    def main(self):
        self.logger.debug(self.sync_interval)
        with Lifecycle() as lifecycle:
            lifecycle.on_startup(self.startup)
            lifecycle.every(self.sync_interval, self.synchronize)  # Sync every 5s
            lifecycle.on_shutdown(self.shutdown)

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
        self.strategy_manager.synchronize()
        self.logger.debug("Synchronized !")

    def shutdown(self):
        """
        Shut down the keeper
        """
        self.logger.info("Keeper shutting down...")
        self.order_book_manager.cancel_all_orders()
        self.clear_all_positions_orders()
        self.logger.info("Keeper is shut down!")

    """
    handlers
    """

    def get_balances(self) -> dict:
        """
        Fetch the onchain balances of collateral and conditional tokens for the keeper
        """

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
                order_type=OrderType(order_dict["order_type"]),
            )
            for order_dict in orders
        ]

    def place_order(self, new_order: Order) -> Order:
        order_id = self.clob_api.place_order(
            price=new_order.price,
            size=new_order.size,
            side=new_order.side.value,
            token_id=self.market.token_id(new_order.token),
            order_type=new_order.order_type,
        )
        return Order(
            price=new_order.price,
            size=new_order.size,
            side=new_order.side,
            id=order_id,
            token=new_order.token,
            order_type=new_order.order_type,
        )

    def clear_all_positions_orders(self):
        """
        Clear all positions by placing opposite orders of equal size
        """
        # Get all current open orders
        balances = self.get_balances()
        self.logger.debug(f"clear_all_positions: Balances: {balances}")
        orders = []

        # For each order, place an opposite order with same size
        # Get token balances for A and B
        token_balances = {k: v for k, v in balances.items() if k in [Token.A, Token.B]}

        # Find token with larger balance
        if token_balances[Token.A] > token_balances[Token.B]:
            larger_token = Token.A
            balance_diff = token_balances[Token.A] - token_balances[Token.B]
        else:
            larger_token = Token.B
            balance_diff = token_balances[Token.B] - token_balances[Token.A]

        # Only place order if there is a balance difference
        if balance_diff > 0:
            clearing_order = Order(
                size=balance_diff,
                price=0.01,
                side=Side.SELL,
                token=larger_token,
                order_type=OrderType.FOK,
            )

            self.logger.info(
                f"clear_all_positions: Placing clearing order: {clearing_order}"
            )
            orders.append(clearing_order)
        self.order_book_manager.place_orders(orders=orders)

    def approve(self):
        """
        Approve the keeper on the collateral and conditional tokens
        """
        collateral = self.clob_api.get_collateral_address()
        conditional = self.clob_api.get_conditional_address()
        exchange = self.clob_api.get_exchange()

        self.contracts.max_approve_erc20(collateral, self.address, exchange)
        self.logger.debug(f"Approved ERC20 for {exchange}")
        self.contracts.max_approve_erc1155(conditional, self.address, exchange)
        self.logger.debug(f"Approved ERC1155 for {exchange}")
