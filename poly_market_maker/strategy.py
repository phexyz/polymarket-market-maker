from enum import Enum
import json
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List

from poly_market_maker.orderbook import OrderManager
from poly_market_maker.price_feed import PriceFeed
from poly_market_maker.types import Token, Collateral, OrderBookEntry, MarketState
from poly_market_maker.constants import MAX_DECIMALS

from poly_market_maker.strategies.base_strategy import BaseStrategy
from poly_market_maker.strategies.amm_strategy import AMMStrategy
from poly_market_maker.strategies.bands_strategy import BandsStrategy
from poly_market_maker.strategies.front_run_strategy import FrontRunStrategy
from poly_market_maker.gamma_api import GammaApi
from poly_market_maker.clob_api import ClobApi
from poly_market_maker.orderbook import OwnOrderBook


class Strategy(Enum):
    AMM = "amm"
    BANDS = "bands"
    FRONT_RUN = "front_run"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for strategy in Strategy:
                if value.lower() == strategy.value.lower():
                    return strategy
        return super()._missing_(value)


@dataclass
class MarketOrderBook:
    """Represents the full market order book"""

    bids: List[OrderBookEntry]
    asks: List[OrderBookEntry]

    @classmethod
    def empty(cls):
        return cls(bids=[], asks=[])


class StrategyManager:
    def __init__(
        self,
        strategy: str,
        config_path: str,
        price_feed: PriceFeed,
        order_book_manager: OrderManager,
        gamma_api: GammaApi,
        clob_api: ClobApi,
    ) -> BaseStrategy:
        self.logger = logging.getLogger(self.__class__.__name__)

        with open(config_path) as fh:
            config = json.load(fh)

        self.price_feed = price_feed
        self.order_manager = order_book_manager
        self.gamma_api = gamma_api
        self.clob_api = clob_api

        match Strategy(strategy):
            case Strategy.AMM:
                self.strategy = AMMStrategy(config)
            case Strategy.BANDS:
                self.strategy = BandsStrategy(config)
            case Strategy.FRONT_RUN:
                self.strategy = FrontRunStrategy(
                    config,
                    gamma_api=self.gamma_api,
                    clob_api=self.clob_api,
                )
            case _:
                raise Exception("Invalid strategy")

    def get_orders(self) -> OwnOrderBook:
        return self.order_manager.get_order_book()

    def get_market_orders(self) -> MarketOrderBook:
        """Get the full market order book for the current market"""
        try:
            orderbook = self.clob_api.client.get_order_book(
                self.strategy.market.clobTokenIds[0]
            )
            if not orderbook:
                self.logger.warning("Got empty market order book")
                return MarketOrderBook.empty()

            # Convert to our internal format
            bids = [
                OrderBookEntry(price=float(bid.price), size=float(bid.size))
                for bid in orderbook.bids
            ]
            asks = [
                OrderBookEntry(price=float(ask.price), size=float(ask.size))
                for ask in orderbook.asks
            ]

            # Sort the books
            bids.sort(key=lambda x: x.price, reverse=True)  # Highest price first
            asks.sort(key=lambda x: x.price)  # Lowest price first

            self.logger.debug(
                f"Market Order Book - Bids: {len(bids)}, Asks: {len(asks)}"
            )
            if bids:
                self.logger.debug(f"Best Bid: {bids[0].price}")
            if asks:
                self.logger.debug(f"Best Ask: {asks[0].price}")

            return MarketOrderBook(bids=bids, asks=asks)

        except Exception as e:
            self.logger.error(f"Failed to get market orders: {e}")
            return MarketOrderBook.empty()

    def get_market_state(self) -> MarketState:
        """Get current market state including orderbook, prices, and derived statistics"""
        try:
            # Get market orders
            market_book = self.get_market_orders()

            # Get our own orders and balances
            own_book = self.get_orders()
            if None in (own_book.orders, own_book.balances):
                self.logger.error("Failed to get order book state")
                return None

            # Combine market orders with our orders
            bids = market_book.bids.copy()
            asks = market_book.asks.copy()

            # Add our orders to the market book
            for order in own_book.orders:
                entry = OrderBookEntry(price=order.price, size=order.size)
                if order.side == "buy":
                    bids.append(entry)
                else:
                    asks.append(entry)

            # Resort after adding our orders
            if bids:
                bids.sort(key=lambda x: x.price, reverse=True)
            if asks:
                asks.sort(key=lambda x: x.price)

            # Get token prices
            try:
                token_prices = self.get_token_prices()
            except Exception as e:
                self.logger.error(f"Failed to get token prices: {e}")
                return None

            # Create market state object
            market_state = MarketState(
                timestamp=datetime.now(),
                market=self.strategy.market,
                away_team_price=token_prices[Token.A],
                home_team_price=token_prices[Token.B],
                away_team_bids=bids,
                away_team_asks=asks,
                balances=own_book.balances,
            )

            # Log market state summary
            self.logger.info(f"Market State Summary:")
            self.logger.info(f"Away Team Price: {market_state.away_team_price}")
            self.logger.info(f"Home Team Price: {market_state.home_team_price}")
            self.logger.info(f"Spread: {market_state.spread}")
            self.logger.info(f"Number of Bids: {len(bids)}")
            self.logger.info(f"Number of Asks: {len(asks)}")

            return market_state

        except Exception as e:
            self.logger.error(f"Error getting market state: {e}")
            return None

    def synchronize(self):
        """Synchronize strategy with current market state"""
        self.logger.debug("Synchronizing strategy...")

        try:
            market_state = self.get_market_state()
            if not market_state:
                self.logger.error("Failed to get market state")
                return

            self.logger.debug(f"Market state: {market_state}")

            # Get orders based on current market state
            orders_to_cancel, orders_to_place = self.strategy.get_orders(market_state)

            self.logger.debug(f"Orders to cancel: {len(orders_to_cancel)}")
            self.logger.debug(f"Orders to place: {len(orders_to_place)}")

            # self.cancel_orders(orders_to_cancel)
            # self.place_orders(orders_to_place)

        except Exception as e:
            self.logger.error(f"Error in synchronize: {e}")

    def get_token_prices(self):
        price_a = round(
            self.price_feed.get_price(Token.A),
            MAX_DECIMALS,
        )
        price_b = round(1 - price_a, MAX_DECIMALS)
        return {Token.A: price_a, Token.B: price_b}

    def cancel_orders(self, orders_to_cancel):
        if len(orders_to_cancel) > 0:
            self.logger.info(
                f"About to cancel {len(orders_to_cancel)} existing orders!"
            )
            self.order_manager.cancel_orders(orders_to_cancel)

    def place_orders(self, orders_to_place):
        if len(orders_to_place) > 0:
            self.logger.info(f"About to place {len(orders_to_place)} new orders!")
            self.order_manager.place_orders(orders_to_place)
