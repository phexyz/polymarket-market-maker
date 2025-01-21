from enum import Enum
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List

from poly_market_maker.orderbook import OrderManager
from poly_market_maker.types import (
    Token,
    Collateral,
    OrderBookEntry,
    MarketState,
    OwnOrderBook,
    Market,
    SportsStrategyState,
)
from poly_market_maker.constants import MAX_DECIMALS

from poly_market_maker.strategies.base_strategy import BaseStrategy
from poly_market_maker.strategies.amm_strategy import AMMStrategy
from poly_market_maker.strategies.bands_strategy import BandsStrategy
from poly_market_maker.strategies.front_run_strategy import FrontRunStrategy
from poly_market_maker.gamma_api import GammaApi
from poly_market_maker.clob_api import ClobApi
from poly_market_maker.scores import ScoreFeed


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
        config: dict,
        order_book_manager: OrderManager,
        gamma_api: GammaApi,
        clob_api: ClobApi,
        market: Market,
    ) -> BaseStrategy:
        self.logger = logging.getLogger(self.__class__.__name__)

        self.order_manager: OrderManager = order_book_manager
        self.gamma_api: GammaApi = gamma_api
        self.clob_api: ClobApi = clob_api
        self.market: Market = market
        self.score_feed: ScoreFeed = ScoreFeed(game_id=config["game_id"])

        match Strategy(strategy):
            case Strategy.AMM:
                self.strategy = AMMStrategy(config)
            case Strategy.BANDS:
                self.strategy = BandsStrategy(config)
            case Strategy.FRONT_RUN:
                self.strategy = FrontRunStrategy(config)
            case _:
                raise Exception("Invalid strategy")

    def get_market_orders(self) -> MarketOrderBook:
        """Get the full market order book for Token 0 for the current market"""
        try:
            token_0_orderbook = self.clob_api.client.get_order_book(
                self.market.clobTokenIds[0]
            )
            if not token_0_orderbook:
                self.logger.warning("Got empty market order book")
                return MarketOrderBook.empty()

            # Convert to our internal format
            bids = [
                OrderBookEntry(price=float(bid.price), size=float(bid.size))
                for bid in token_0_orderbook.bids
            ]
            asks = [
                OrderBookEntry(price=float(ask.price), size=float(ask.size))
                for ask in token_0_orderbook.asks
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

    def get_token_prices(self):
        price_a = self.clob_api.get_price(self.market.token_id(Token.A))
        price_b = self.clob_api.get_price(self.market.token_id(Token.B))
        return {Token.A: price_a, Token.B: price_b}

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

            # Get token prices
            try:
                token_prices = self.get_token_prices()
            except Exception as e:
                self.logger.error(f"Failed to get token prices: {e}")
                return None

            # Create market state object
            market_state = MarketState(
                timestamp=datetime.now(),
                away_team_price=token_prices[Token.A],
                home_team_price=token_prices[Token.B],
                away_team_bids=market_book.bids,
                away_team_asks=market_book.asks,
                own_orders=own_book,
            )

            return market_state

        except Exception as e:
            self.logger.error(f"Error getting market state: {e}")
            return None

    def get_strategy_state(self) -> SportsStrategyState:
        market_state = self.get_market_state()
        score_board = self.score_feed.get_scoreboard()
        if market_state == None or score_board == None:
            return None
        return SportsStrategyState(market_state=market_state, score_board=score_board)

    def synchronize(self):
        """Synchronize strategy with current market state"""
        self.logger.debug("Synchronizing strategy...")

        try:
            external_state = self.get_strategy_state()
            if not external_state:
                self.logger.error("Failed to get strategy external state")
                return

            # Get orders based on current market state
            orders_to_place, orders_to_cancel = self.strategy.get_orders(external_state)

            self.cancel_orders(orders_to_cancel)
            self.place_orders(orders_to_place)

        except Exception as e:
            self.logger.error(f"Error in synchronize: {e}")

    def get_orders(self) -> OwnOrderBook:
        return self.order_manager.get_order_book()

    def cancel_orders(self, orders_to_cancel):
        if len(orders_to_cancel) > 0:
            self.logger.info(
                f"About to cancel {len(orders_to_cancel)} existing orders!"
            )
            self.order_manager.cancel_orders(orders_to_cancel)

    def place_orders(self, orders_to_place):
        if len(orders_to_place) > 0:
            self.logger.info(
                f"About to place {len(orders_to_place)} new orders! Orders to place: {orders_to_place}"
            )
            self.order_manager.place_orders(orders_to_place)
