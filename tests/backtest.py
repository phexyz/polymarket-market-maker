import pandas as pd
import datetime
from typing import Dict
import glob
import json
import re

from poly_market_maker.types import (
    MarketState,
    Token,
    SportsStrategyState,
    ScoreBoard,
    OrderBookEntry,
    OwnOrderBook,
    Side,
)
from poly_market_maker.strategies.front_run_strategy import FrontRunStrategy
from poly_market_maker.utils import setup_logging


class MockStrategyManager:
    def __init__(self, config_path: str):
        setup_logging("401705153")
        # Initialize strategy
        with open(config_path) as f:
            config = json.load(f)
        self.strategy = FrontRunStrategy(config)

        # Find and load CSV file
        self.strategy_states = self.read_strategy_states()

        # Initialize account state
        self.balances = {Token.A: 0, Token.B: 0, Token.C: 1000}
        self.active_orders = []
        self.pnl_history = []

    def read_strategy_states(self):
        """Read strategy states from CSV file"""
        strategy_states = []

        with open("game_data_401705153_updated.csv", "r") as f:
            # Process file line by line
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Clean up own_orders references
                line = re.sub(r"own_orders=<[^>]+>", "own_orders=None", line)

                try:
                    state_dict: SportsStrategyState = eval(line)
                    state_dict.market_state.own_orders = OwnOrderBook(
                        orders=[],
                        balances={Token.A: 0, Token.B: 0, Token.C: 1000},
                        orders_being_placed=False,
                        orders_being_cancelled=False,
                    )

                    if state_dict.market_state.away_team_asks:
                        strategy_states.append(state_dict)
                    else:
                        break
                except Exception as e:
                    print(f"Error processing line: {e}")
                    continue

        return strategy_states

    def _execute_orders(
        self, orders_to_place, orders_to_cancel, state: SportsStrategyState
    ):
        """Simulate order execution"""
        # Cancel orders
        for order in orders_to_cancel:
            if order in self.active_orders:
                self.active_orders.remove(order)

        # Place and fill new orders
        for order in orders_to_place:
            # Use best price from order book for fills
            if order.side == Side.BUY:
                fill_price = (
                    min(ask.price for ask in state.market_state.get_asks(order.token))
                    if order.token == Token.A
                    else min(
                        ask.price for ask in state.market_state.get_asks(order.token)
                    )
                )
            else:  # SELL
                fill_price = (
                    max(bid.price for bid in state.market_state.get_bids(order.token))
                    if order.token == Token.A
                    else max(
                        bid.price for bid in state.market_state.get_bids(order.token)
                    )
                )

            # Update balances based on trade
            if order.side == Side.BUY:
                self.balances[order.token] += order.size
                self.balances[Token.C] -= order.size * fill_price
            else:  # SELL
                self.balances[order.token] -= order.size
                self.balances[Token.C] += order.size * fill_price

            # self.active_orders.append(order) TODO: add order not filled simulation

    def run_backtest(self):
        """Run backtest through historical data"""
        print("Starting backtest...")
        print(f"Initial balances: {self.balances}")

        for idx, state in enumerate(self.strategy_states):
            # Get strategy orders
            state.market_state.own_orders = OwnOrderBook(
                orders=self.active_orders,
                balances=self.balances,
                orders_being_placed=False,
                orders_being_cancelled=False,
            )
            orders_to_place, orders_to_cancel = self.strategy.get_orders(state)

            # Execute orders
            self._execute_orders(orders_to_place, orders_to_cancel, state)

            # Record PnL
            total_value = (
                self.balances[Token.C]
                + self.balances[Token.A] * state.market_state.away_team_price
                + self.balances[Token.B] * state.market_state.home_team_price
            )
            self.pnl_history.append(
                {
                    "timestamp": state.market_state.timestamp,
                    "total_value": total_value,
                    "balances": self.balances.copy(),
                }
            )

            best_bid = (
                max(bid.price for bid in state.market_state.away_team_bids)
                if state.market_state.away_team_bids
                else None
            )
            best_ask = (
                min(ask.price for ask in state.market_state.away_team_asks)
                if state.market_state.away_team_asks
                else None
            )
            try:
                print(
                    f"Time: {state.market_state.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | Score: {None if state.score_board is None or state.score_board.away_score is None or state.score_board.home_score is None else f'{state.score_board.away_score}-{state.score_board.home_score}'} | "
                    f"Best bid: {best_bid:.3f} | Best ask: {best_ask:.3f} | "
                    f"Orders to place: {orders_to_place if orders_to_place else 'None'} | "
                    f"Balances: {self.balances}"
                )
            except TypeError:
                print("One or more values are None")

        print("\nBacktest complete!")
        print(f"Final balances: {self.balances}")
        print(f"Final portfolio value: {self.pnl_history[-1]['total_value']}")


if __name__ == "__main__":
    backtest = MockStrategyManager("config/front_run.json")
    backtest.run_backtest()
