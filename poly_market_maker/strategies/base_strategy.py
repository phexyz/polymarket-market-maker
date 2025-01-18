import logging
from typing import Tuple
from abc import ABC, abstractmethod

from poly_market_maker.orderbook import OwnOrderBook
from poly_market_maker.order import Order
from poly_market_maker.types import MarketState


class BaseStrategy(ABC):
    """Base market making strategy"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.place_orders = None
        self.cancel_orders = None

    @abstractmethod
    def get_orders(self, market_state: MarketState) -> tuple[list[Order], list[Order]]:
        """
        Get orders to cancel and place based on current market state
        Returns: Tuple of (orders_to_cancel, orders_to_place)
        """
        pass
