from dataclasses import dataclass
from typing import Optional, Union, List, Dict
import pickle
import time
from poly_market_maker.strategies.base_strategy import BaseStrategy
from poly_market_maker.gamma_api import GammaApi
from poly_market_maker.clob_api import ClobApi
from poly_market_maker.types import (
    MarketState,
    Token,
    SportsStrategyState,
    ScoreBoard,
    Side,
    OrderReset,
)
from poly_market_maker.orderbook import Order
from datetime import timedelta
from collections import deque
from py_clob_client.clob_types import OrderType


class FrontRunStrategy(BaseStrategy):
    def __init__(
        self,
        config: dict,
    ):
        assert isinstance(config, dict), "config must be a dictionary"
        print("FrontRunStrategy initialized")

        super().__init__()
        self.game_id = config["game_id"]
        self.home_team = "HOME"
        self.away_team = "AWAY"
        self.away_token = Token.A
        self.home_token = Token.B

        # Initialize score state
        self.state: SportsStrategyState = None
        self.reset: OrderReset = None
        self.order_size = 10  # size * price needs to be greater than 1 dollar
        self.reset_delay = 10

        # Initialize CSV file
        self.json_filename = f"game_data_{self.game_id}_updated.json"
        self._initialize_json()

    def _initialize_json(self):
        """Initialize pickle file"""
        try:
            with open(self.json_filename, "rb"):
                pass
        except FileNotFoundError:
            with open(self.json_filename, "wb") as file:
                pickle.dump([], file)

    def save_state_to_file(self):
        # Log state before saving
        self.logger.debug(f"Saving state to pickle: {self.json_filename}")
        # Append single state using pickle
        with open(self.json_filename, "ab") as file:
            pickle.dump(self.state, file)

    def _get_favored_token(
        self, old_state: SportsStrategyState, new_state: SportsStrategyState
    ) -> Token | None:

        if old_state == None or new_state == None:
            return None

        # handle the case where game has ended
        if "Final" in new_state.score_board.game_time:
            if new_state.score_board.away_score > new_state.score_board.home_score:
                return Token.A
            else:
                return Token.B

        away_diff = new_state.score_board.away_score - old_state.score_board.away_score
        home_diff = new_state.score_board.home_score - old_state.score_board.home_score

        # Compare score differences between states
        old_diff = abs(
            old_state.score_board.away_score - old_state.score_board.home_score
        )
        new_diff = abs(
            new_state.score_board.away_score - new_state.score_board.home_score
        )
        diff_in_diff = abs(new_diff - old_diff)
        diff_pct = diff_in_diff * 1.0 / old_diff if old_diff > 0 else 1

        # Print all the score differences
        self.logger.info(f"Away score diff: {away_diff}")
        self.logger.info(f"Home score diff: {home_diff}")
        self.logger.info(f"Old score diff: {old_diff}")
        self.logger.info(f"New score diff: {new_diff}")
        self.logger.info(f"Score difference change: {diff_in_diff}")
        self.logger.info(f"Score difference change percentage: {diff_pct}")

        if diff_in_diff >= 2 and diff_pct >= 0.1:
            if away_diff > 0:
                return Token.A
            elif home_diff > 0:
                return Token.B

        return None

    def build_order(
        self,
        state: SportsStrategyState,
        token: Token,
        side: Side,
        default_to_FOK: bool = True,
    ):

        price = state.market_state.get_best_limit_price(token=token, side=side)
        order_type = OrderType.GTC

        if side == Side.SELL:
            price = 0.01
            order_type = OrderType.FOK
        elif price == None:
            if default_to_FOK:
                order_type = OrderType.FOK
                price = 0.99
            else:
                return None

        return Order(
            size=self.order_size,
            price=price,
            side=side,
            token=token,
            order_type=order_type,
        )

    def get_orders(
        self, new_state: SportsStrategyState
    ) -> tuple[list[Order], list[Order]]:
        """
        Process current market state and collect game data
        Returns: Empty orders since this is a data collection strategy
        """
        orders_to_place = []
        orders_to_cancel = []

        # check if score changed, then place orders
        for favored_token in [
            self._get_favored_token(old_state=self.state, new_state=new_state)
        ]:
            self.logger.info(
                f"Favored token: {favored_token.value if favored_token else None}"
            )
            if favored_token == None:
                continue
            new_order = self.build_order(
                state=new_state,
                token=favored_token,
                side=Side.BUY,
                default_to_FOK=False,
            )
            if new_order == None:
                continue

            orders_to_place.append(new_order)
            self.logger.info(
                f"Strategy order returned - Orders to place: {orders_to_place}, Orders to cancel: {orders_to_cancel}"
            )

            # reset logic
            reset_from_new_order = OrderReset(
                trigger_timestamp=new_state.market_state.timestamp
                + timedelta(seconds=self.reset_delay),
                token=new_order.token,
                size=new_order.size,
            )

            if self.reset:
                # if we had an order unfavored by the new change
                if self.reset.token != favored_token:

                    orders_to_place_from_reset, orders_to_cancel_from_reset = (
                        self.consume_reset(self.reset, new_state)
                    )
                    orders_to_place.extend(orders_to_place_from_reset)
                    orders_to_cancel.extend(orders_to_cancel_from_reset)
                    self.logger.info(
                        f"Early reset order returned - Orders to place: {orders_to_place}, Orders to cancel: {orders_to_cancel}"
                    )

                    self.reset = reset_from_new_order
                # favored by the new change
                else:
                    # increase the size
                    self.reset = OrderReset(
                        trigger_timestamp=reset_from_new_order.trigger_timestamp,
                        token=reset_from_new_order.token,
                        size=self.reset.size + reset_from_new_order.size,
                    )
            else:
                self.reset = reset_from_new_order

        # Log reset processing status
        if self.reset:
            self.logger.info(
                f"Processing reset: token={self.reset.token.value}, "
                f"size={self.reset.size}, "
                f"trigger_time={self.reset.trigger_timestamp}, "
                f"reset_timestamp={self.reset.trigger_timestamp}, "
                f"market_timestamp={new_state.market_state.timestamp}, "
                f"comparison_result={self.reset.trigger_timestamp <= new_state.market_state.timestamp}"
            )
        else:
            self.logger.info("No reset to process")
        # if there are any existing reset
        if (
            self.reset
            and self.reset.trigger_timestamp <= new_state.market_state.timestamp
        ):
            self.logger.info(
                f"Reset triggered at {new_state.market_state.timestamp} for token {self.reset.token.value} with size {self.reset.size}"
            )
            # consume the reset
            orders_to_place_from_reset, orders_to_cancel_from_reset = (
                self.consume_reset(self.reset, new_state)
            )
            orders_to_place.extend(orders_to_place_from_reset)
            orders_to_cancel.extend(orders_to_cancel_from_reset)
            self.logger.info(
                f"Timed reset order returned - Orders to place: {orders_to_place}, Orders to cancel: {orders_to_cancel}"
            )
            self.reset = None

        # Update state
        self.state = new_state
        self.state.market_state.set_orders_to_place(orders_to_place)
        self.state.market_state.set_orders_to_cancel(orders_to_cancel)
        self.save_state_to_file()

        return orders_to_place, orders_to_cancel

    def consume_reset(self, reset: OrderReset, state: SportsStrategyState):
        target_token = reset.token

        # consume the reset
        orders_to_place = [
            self.build_order(
                state=state,
                token=target_token,
                side=Side.SELL,
                default_to_FOK=True,
            )
        ]

        orders_to_cancel = []

        for active_order in state.market_state.own_orders.orders:
            if active_order.token == target_token:
                orders_to_cancel.append(active_order)

        return orders_to_place, orders_to_cancel
