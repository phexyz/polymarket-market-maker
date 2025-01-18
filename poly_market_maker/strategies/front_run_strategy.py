from dataclasses import dataclass
from typing import Optional, Union, List, Dict
import csv
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
        self.order_size = 1000.0
        self.reset_delay = 3
        # Initialize CSV file
        self.csv_filename = f"game_data_{self.game_id}_updated.csv"
        self._initialize_csv()

    def _initialize_csv(self):
        """Initialize CSV file"""
        # Create file if it doesn't exist
        try:
            with open(self.csv_filename, "r"):
                pass
        except FileNotFoundError:
            with open(self.csv_filename, "w") as file:
                pass

    def save_state_to_csv(self):
        # Write state as a single line
        with open(self.csv_filename, "a") as file:
            file.write(str(self.state) + "\n")

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
        diff_pct = diff_in_diff * 1.0 / old_diff >= 0.3

        print("away_diff:", away_diff)
        print("home_diff:", home_diff)
        print("old_diff:", old_diff)
        print("new_diff:", new_diff)
        print("diff_in_diff:", diff_in_diff)
        print("diff_pct:", diff_pct)
        print("scoreboard:", new_state.score_board)

        if diff_in_diff >= 2 and diff_pct:
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

        if price == None:
            if default_to_FOK:
                order_type = OrderType.FOK
                price = 0.0 if side == Side.SELL else 1.0
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
            print(favored_token)
            if favored_token == None:
                continue
            new_order = self.build_order(
                state=new_state,
                token=favored_token,
                side=Side.BUY,
                default_to_FOK=False,
            )
            print("new_order", new_order)
            if new_order == None:
                continue

            orders_to_place.append(new_order)
            print("in strategy order returned", orders_to_place, orders_to_cancel)

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
                    print(
                        "in strategy early reset order returned",
                        orders_to_place,
                        orders_to_cancel,
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

        # if there are any existing reset
        if (
            self.reset
            and self.reset.trigger_timestamp <= new_state.market_state.timestamp
        ):
            # consume the reset
            orders_to_place_from_reset, orders_to_cancel_from_reset = (
                self.consume_reset(self.reset, new_state)
            )
            orders_to_place.extend(orders_to_place_from_reset)
            orders_to_cancel.extend(orders_to_cancel_from_reset)
            print(
                "in strategy timed reset order returned",
                orders_to_place,
                orders_to_cancel,
            )
            self.reset = None

        # Update state
        self.state = new_state
        self.save_state_to_csv()

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
