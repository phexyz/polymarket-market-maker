import pandas as pd
from datetime import datetime
from typing import Dict
import glob
import json

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


class MockStrategyManager:
    def __init__(self, config_path: str):
        # Initialize strategy
        with open(config_path) as f:
            config = json.load(f)
        self.strategy = FrontRunStrategy(config)

        # Find and load CSV file
        csv_pattern = f"game_data_{config['game_id']}.csv"
        csv_files = glob.glob(csv_pattern)
        if not csv_files:
            raise FileNotFoundError(f"No CSV file found matching {csv_pattern}")

        self.df = pd.read_csv(csv_files[0])

        # Initialize account state
        self.balances = {Token.A: 0, Token.B: 0, Token.C: 1000}
        self.active_orders = []
        self.pnl_history = []

    def _parse_row_to_state(self, row) -> SportsStrategyState:
        """Convert a CSV row to SportsStrategyState"""
        # Parse order book entries
        bids = eval(row[f"{self.strategy.away_team}_Order_Book_Bids"])
        asks = eval(row[f"{self.strategy.away_team}_Order_Book_Asks"])

        # Convert bid/ask prices and sizes to float
        for bid in bids:
            bid["price"] = float(bid["price"])
            bid["size"] = float(bid["size"])
        for ask in asks:
            ask["price"] = float(ask["price"])
            ask["size"] = float(ask["size"])

        market_state = MarketState(
            timestamp=datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S"),
            away_team_price=float(row[f"{self.strategy.away_team}_Price"]),
            home_team_price=float(row[f"{self.strategy.home_team}_Price"]),
            away_team_bids=[OrderBookEntry(**bid) for bid in bids],
            away_team_asks=[OrderBookEntry(**ask) for ask in asks],
            own_orders=OwnOrderBook(
                orders=self.active_orders,
                balances=self.balances,
                orders_being_placed=False,
                orders_being_cancelled=False,
            ),
        )

        score_board = ScoreBoard(
            away_score=int(row[f"{self.strategy.away_team}_Score"]),
            home_score=int(row[f"{self.strategy.home_team}_Score"]),
            game_time="NA",
        )

        return SportsStrategyState(market_state=market_state, score_board=score_board)

    def _execute_orders(self, orders_to_place, orders_to_cancel):
        """Simulate order execution"""
        # Cancel orders
        for order in orders_to_cancel:
            if order in self.active_orders:
                self.active_orders.remove(order)

        # Place and fill new orders
        for order in orders_to_place:
            fill_price = order.price

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

        for idx, row in self.df.iterrows():
            # Convert row to strategy state
            state = self._parse_row_to_state(row)

            # Get strategy orders
            orders_to_place, orders_to_cancel = self.strategy.get_orders(state)
            print("back test orders", orders_to_place, orders_to_cancel)

            # Execute orders
            self._execute_orders(orders_to_place, orders_to_cancel)

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

            if orders_to_place or orders_to_cancel:
                print(f"\nTimestamp: {state.market_state.timestamp}")
                print(
                    f"Scores: {state.score_board.away_score}-{state.score_board.home_score}"
                )
                print(f"Orders placed: {len(orders_to_place)}")
                print(f"Orders cancelled: {len(orders_to_cancel)}")
                print(f"Current balances: {self.balances}")
                print(f"Portfolio value: {total_value}")

        print("\nBacktest complete!")
        print(f"Final balances: {self.balances}")
        print(f"Final portfolio value: {self.pnl_history[-1]['total_value']}")


if __name__ == "__main__":
    backtest = MockStrategyManager("config/front_run.json")
    backtest.run_backtest()
