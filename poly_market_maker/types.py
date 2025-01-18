from __future__ import annotations
from typing import Optional, Union, List, Dict
from pydantic import BaseModel
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from py_clob_client.order_builder.constants import BUY, SELL
from typeguard import typechecked
from py_clob_client.clob_types import OrderType


class OwnOrderBook:
    """Represents the current snapshot of the order book.

    Attributes:
        -orders: Current list of active orders.
        -balances: Current balances state.
        -orders_being_placed: `True` if at least one order is currently being placed. `False` otherwise.
        -orders_being_cancelled: `True` if at least one orders is currently being cancelled. `False` otherwise.
    """

    def __init__(
        self,
        orders: list[Order],
        balances: dict,
        orders_being_placed: bool,
        orders_being_cancelled: bool,
    ):
        assert isinstance(orders_being_placed, bool)
        assert isinstance(orders_being_cancelled, bool)

        self.orders = orders
        self.balances = balances
        self.orders_being_placed = orders_being_placed
        self.orders_being_cancelled = orders_being_cancelled


@typechecked
@dataclass(frozen=True, slots=True)
class Trade(BaseModel):
    id: int
    taker_order_id: str
    market: str
    asset_id: str
    side: str
    size: str
    fee_rate_bps: str
    price: str
    status: str
    match_time: str
    last_update: str
    outcome: str
    maker_address: str
    owner: str
    transaction_hash: str
    bucket_index: str
    maker_orders: list[str]
    type: str


class SimpleMarket(BaseModel):
    id: int
    question: str
    # start: str
    end: str
    description: str
    active: bool
    # deployed: Optional[bool]
    funded: bool
    # orderMinSize: float
    # orderPriceMinTickSize: float
    rewardsMinSize: float
    rewardsMaxSpread: float
    # volume: Optional[float]
    spread: float
    outcomes: str
    outcome_prices: str
    clob_token_ids: Optional[str]


class ClobReward(BaseModel):
    id: str  # returned as string in api but really an int?
    conditionId: str
    assetAddress: str
    rewardsAmount: float  # only seen 0 but could be float?
    rewardsDailyRate: int  # only seen ints but could be float?
    startDate: str  # yyyy-mm-dd formatted date string
    endDate: str  # yyyy-mm-dd formatted date string


class Tag(BaseModel):
    id: str
    label: Optional[str] = None
    slug: Optional[str] = None
    forceShow: Optional[bool] = None  # missing from current events data
    createdAt: Optional[str] = None  # missing from events data
    updatedAt: Optional[str] = None  # missing from current events data
    _sync: Optional[bool] = None


class PolymarketEvent(BaseModel):
    id: str  # "11421"
    ticker: Optional[str] = None
    slug: Optional[str] = None
    title: Optional[str] = None
    startDate: Optional[str] = None
    creationDate: Optional[str] = (
        None  # fine in market event but missing from events response
    )
    endDate: Optional[str] = None
    image: Optional[str] = None
    icon: Optional[str] = None
    active: Optional[bool] = None
    closed: Optional[bool] = None
    archived: Optional[bool] = None
    new: Optional[bool] = None
    featured: Optional[bool] = None
    restricted: Optional[bool] = None
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    reviewStatus: Optional[str] = None
    createdAt: Optional[str] = None  # 2024-07-08T01:06:23.982796Z,
    updatedAt: Optional[str] = None  # 2024-07-15T17:12:48.601056Z,
    competitive: Optional[float] = None
    volume24hr: Optional[float] = None
    enableOrderBook: Optional[bool] = None
    liquidityClob: Optional[float] = None
    _sync: Optional[bool] = None
    commentCount: Optional[int] = None
    # markets: list[str, 'Market'] # forward reference Market defined below - TODO: double check this works as intended
    markets: Optional[list[Market]] = None
    tags: Optional[list[Tag]] = None
    cyom: Optional[bool] = None
    showAllOutcomes: Optional[bool] = None
    showMarketImages: Optional[bool] = None


class Market(BaseModel):
    id: int
    question: Optional[str] = None
    condition_id: Optional[str] = None
    slug: Optional[str] = None
    resolutionSource: Optional[str] = None
    endDate: Optional[str] = None
    liquidity: Optional[float] = None
    startDate: Optional[str] = None
    image: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    outcome: Optional[list] = None
    outcomePrices: Optional[list] = None
    volume: Optional[float] = None
    active: Optional[bool] = None
    closed: Optional[bool] = None
    marketMakerAddress: Optional[str] = None
    createdAt: Optional[str] = None  # date type worth enforcing for dates?
    updatedAt: Optional[str] = None
    new: Optional[bool] = None
    featured: Optional[bool] = None
    submitted_by: Optional[str] = None
    archived: Optional[bool] = None
    resolvedBy: Optional[str] = None
    restricted: Optional[bool] = None
    groupItemTitle: Optional[str] = None
    groupItemThreshold: Optional[int] = None
    questionID: Optional[str] = None
    enableOrderBook: Optional[bool] = None
    orderPriceMinTickSize: Optional[float] = None
    orderMinSize: Optional[int] = None
    volumeNum: Optional[float] = None
    liquidityNum: Optional[float] = None
    endDateIso: Optional[str] = None  # iso format date = None
    startDateIso: Optional[str] = None
    hasReviewedDates: Optional[bool] = None
    volume24hr: Optional[float] = None
    clobTokenIds: Optional[list] = None
    umaBond: Optional[int] = None  # returned as string from api?
    umaReward: Optional[int] = None  # returned as string from api?
    volume24hrClob: Optional[float] = None
    volumeClob: Optional[float] = None
    liquidityClob: Optional[float] = None
    acceptingOrders: Optional[bool] = None
    negRisk: Optional[bool] = None
    commentCount: Optional[int] = None
    _sync: Optional[bool] = None
    events: Optional[list[PolymarketEvent]] = None
    ready: Optional[bool] = None
    deployed: Optional[bool] = None
    funded: Optional[bool] = None
    deployedTimestamp: Optional[str] = None  # utc z datetime string
    acceptingOrdersTimestamp: Optional[str] = None  # utc z datetime string,
    cyom: Optional[bool] = None
    competitive: Optional[float] = None
    pagerDutyNotificationEnabled: Optional[bool] = None
    reviewStatus: Optional[str] = None  # deployed, draft, etc.
    approved: Optional[bool] = None
    clobRewards: Optional[list[ClobReward]] = None
    rewardsMinSize: Optional[int] = (
        None  # would make sense to allow float but we'll see
    )
    rewardsMaxSpread: Optional[float] = None
    spread: Optional[float] = None

    def __repr__(self):
        return f"Market[id={self.id}, condition_id={self.condition_id}, question={self.question}]"

    def token_id(self, token: Token) -> int:
        if not self.clobTokenIds:
            raise ValueError("No CLOB token IDs available")
        return self.clobTokenIds[token.value]

    def token(self, token_id: int) -> Token:
        if not self.clobTokenIds:
            raise ValueError("No CLOB token IDs available")
        for token in Token:
            if token_id == self.clobTokenIds[token.value]:
                return token
        raise ValueError("Unrecognized token ID")


class ComplexMarket(BaseModel):
    id: int
    condition_id: str
    question_id: str
    tokens: Union[str, str]
    rewards: str
    minimum_order_size: str
    minimum_tick_size: str
    description: str
    category: str
    end_date_iso: str
    game_start_time: str
    question: str
    market_slug: str
    min_incentive_size: str
    max_incentive_spread: str
    active: bool
    closed: bool
    seconds_delay: int
    icon: str
    fpmm: str
    name: str
    description: Union[str, None] = None
    price: float
    tax: Union[float, None] = None


class SimpleEvent(BaseModel):
    id: int
    ticker: str
    slug: str
    title: str
    description: str
    end: str
    active: bool
    closed: bool
    archived: bool
    restricted: bool
    new: bool
    featured: bool
    restricted: bool
    markets: str


class Source(BaseModel):
    id: Optional[str]
    name: Optional[str]


class Article(BaseModel):
    source: Optional[Source]
    author: Optional[str]
    title: Optional[str]
    description: Optional[str]
    url: Optional[str]
    urlToImage: Optional[str]
    publishedAt: Optional[str]
    content: Optional[str]


Collateral = "Collateral"


class Token(Enum):
    A = 0
    B = 1
    C = 2

    def complement(self):
        return Token.B if self == Token.A else Token.A


@typechecked
@dataclass(frozen=True, slots=True)
class OrderBookEntry:
    price: float
    size: float


@typechecked
@dataclass(slots=True)
class MarketState:
    """Container for all market state information at a point in time"""

    timestamp: datetime

    # Token prices
    away_team_price: float
    home_team_price: float

    # Market order book
    away_team_bids: List[OrderBookEntry]
    away_team_asks: List[OrderBookEntry]

    # Our own orders and balances
    own_orders: OwnOrderBook

    # Market summary stats
    away_team_mid_price: float = None
    home_team_mid_price: float = None
    spread: float = None
    volume_24h: float = None

    def __post_init__(self):
        """Calculate derived statistics"""
        if self.away_team_bids and self.away_team_asks:
            best_bid = max(bid.price for bid in self.away_team_bids)
            best_ask = min(ask.price for ask in self.away_team_asks)
            self.away_team_mid_price = (best_bid + best_ask) / 2
            self.home_team_mid_price = 1 - self.away_team_mid_price
            self.spread = best_ask - best_bid

    def get_best_limit_price(self, token: Token, side: Side) -> float | None:
        if side == Side.BUY:
            return self.get_min_ask(token)
        elif side == Side.SELL:
            return self.get_max_bid(token)

    def get_max_bid(self, token: Token) -> float | None:
        bids = self.get_bids(token)
        if not bids:
            return None
        return bids[0].price

    def get_min_ask(self, token: Token) -> float | None:
        asks = self.get_asks(token)
        if not asks:
            return None
        return asks[0].price

    def get_bids(self, token: Token) -> List[OrderBookEntry]:
        """Get bids for the given token"""
        if token == Token.A:
            return self.away_team_bids
        elif token == Token.B:
            return [
                OrderBookEntry(price=1 - bid.price, size=bid.size)
                for bid in self.away_team_asks
            ]
        else:
            raise ValueError(f"Invalid token {token} - must be Token.A or Token.B")

    def get_asks(self, token: Token) -> List[OrderBookEntry]:
        """Get asks for the given token"""
        if token == Token.A:
            return self.away_team_asks
        elif token == Token.B:
            return [
                OrderBookEntry(price=1 - ask.price, size=ask.size)
                for ask in self.away_team_bids
            ]
        else:
            raise ValueError(f"Invalid token {token} - must be Token.A or Token.B")

    def get_mid_price(self, token: Token) -> float:
        """Get mid price for the given token"""
        if token == Token.A:
            return self.away_team_mid_price
        elif token == Token.B:
            return self.home_team_mid_price
        else:
            raise ValueError(f"Invalid token {token} - must be Token.A or Token.B")

    def get_price(self, token: Token) -> float:
        """Get price for the given token"""
        if token == Token.A:
            return self.away_team_price
        elif token == Token.B:
            return self.home_team_price
        else:
            raise ValueError(f"Invalid token {token} - must be Token.A or Token.B")


class Side(Enum):
    BUY = BUY
    SELL = SELL

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for side in Side:
                if value.lower() == side.value.lower():
                    return side
        return super()._missing_(value)


@typechecked
class Order:
    def __init__(
        self,
        size: float,
        price: float,
        side: Side,
        token: Token,
        order_type,
        id: None | str = None,
    ):
        if isinstance(size, int):
            size = float(size)

        assert isinstance(size, float)
        assert isinstance(price, float)
        assert isinstance(side, Side)
        assert isinstance(token, Token)
        if id is not None:
            assert isinstance(id, str)

        self.size = size
        self.price = price
        self.side = side
        self.token = token
        self.id = id
        self.order_type = order_type

    def __repr__(self):
        return f"Order[id={self.id}, price={self.price}, size={self.size}, side={self.side.value}, token={self.token.value}, order_type={self.order_type}]"


@typechecked
@dataclass(frozen=True, slots=True)
class OrderReset:
    trigger_timestamp: datetime
    token: Token
    size: float


@typechecked
@dataclass(frozen=True, slots=True)
class ScoreBoard:
    away_score: int
    home_score: int
    game_time: str

    def changed(self, other_score_board: ScoreBoard, threshold: float) -> Token | None:
        """
        Compare two score boards and return Token.A if away team scored, Token.B if home team scored,
        or None if no change or negative change
        """
        if not other_score_board:
            return None

        away_diff = self.away_score - other_score_board.away_score
        home_diff = self.home_score - other_score_board.home_score

        if away_diff >= threshold:
            return Token.A
        elif home_diff >= threshold:
            return Token.B
        else:
            return None

    def get_score(self, token: Token) -> int:
        """Get score for the given token (A=away, B=home)"""
        assert isinstance(token, Token)
        if token == Token.A:
            return self.away_score
        elif token == Token.B:
            return self.home_score
        else:
            raise ValueError(f"Invalid token {token} - must be Token.A or Token.B")


@typechecked
@dataclass(frozen=True, slots=True)
class SportsStrategyState:
    market_state: MarketState
    score_board: ScoreBoard
