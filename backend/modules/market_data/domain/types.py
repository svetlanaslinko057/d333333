"""
FOMO Market Data - Domain Types
Единые типы данных для всей системы
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum

# ═══════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════

class Venue(str, Enum):
    BINANCE = "binance"
    BYBIT = "bybit"
    COINBASE = "coinbase"
    HYPERLIQUID = "hyperliquid"

class MarketType(str, Enum):
    SPOT = "spot"
    PERP = "perp"
    FUTURES = "futures"
    OPTION = "option"

class ContractType(str, Enum):
    LINEAR_PERP = "linear_perp"
    INVERSE_PERP = "inverse_perp"
    LINEAR_FUTURES = "linear_futures"
    INVERSE_FUTURES = "inverse_futures"
    SPOT = "spot"

class DataQualitySource(str, Enum):
    REALTIME = "realtime"
    CACHED = "cached"
    INTEL = "intel"
    CALCULATED = "calculated"

# ═══════════════════════════════════════════════════════════════
# CORE ENTITIES
# ═══════════════════════════════════════════════════════════════

class Asset(BaseModel):
    """Базовый актив (BTC, ETH, etc.)"""
    asset_id: str  # "btc", "eth"
    symbol: str  # "BTC"
    name: str  # "Bitcoin"
    type: str = "cryptocurrency"
    category: Optional[str] = None
    description: Optional[str] = None
    links: Optional[Dict[str, List[str]]] = None
    contracts: Optional[List[Dict[str, Any]]] = None
    icon_url: Optional[str] = None

class Instrument(BaseModel):
    """Торговый инструмент на конкретной бирже"""
    instrument_id: str  # "binance:perp:BTCUSDT"
    venue: Venue
    market_type: MarketType
    native_symbol: str  # "BTCUSDT"
    base: str  # "BTC"
    quote: str  # "USDT"
    status: str = "trading"
    tick_size: Optional[float] = None
    lot_size: Optional[float] = None
    contract_type: Optional[ContractType] = None
    settle_asset: Optional[str] = None
    
    @classmethod
    def make_id(cls, venue: str, market_type: str, native_symbol: str) -> str:
        return f"{venue}:{market_type}:{native_symbol}"

class SymbolMapping(BaseModel):
    """Маппинг инструментов к базовому активу"""
    asset_id: str
    instrument_id: str
    venue: Venue
    market_type: MarketType
    native_symbol: str
    priority: int = 50  # для выбора primary source

# ═══════════════════════════════════════════════════════════════
# MARKET DATA TYPES (нормализованные)
# ═══════════════════════════════════════════════════════════════

class Ticker(BaseModel):
    """Нормализованный тикер"""
    ts: int  # ms epoch
    instrument_id: str
    last: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    change_24h: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    trades_24h: Optional[int] = None

class OrderBookLevel(BaseModel):
    price: float
    qty: float

class OrderBook(BaseModel):
    """Нормализованный orderbook"""
    ts: int
    instrument_id: str
    depth: int
    seq: Optional[int] = None
    bids: List[List[float]]  # [[price, qty], ...]
    asks: List[List[float]]

class Trade(BaseModel):
    """Нормализованная сделка"""
    ts: int
    instrument_id: str
    trade_id: str
    price: float
    qty: float
    side: Literal["buy", "sell"]

class Candle(BaseModel):
    """Нормализованная свеча"""
    t: int  # open time ms
    o: float  # open
    h: float  # high
    l: float  # low
    c: float  # close
    v: float  # volume

class CandleResponse(BaseModel):
    ts: int
    instrument_id: str
    granularity: str
    candles: List[Candle]

# ═══════════════════════════════════════════════════════════════
# DERIVATIVES DATA
# ═══════════════════════════════════════════════════════════════

class FundingRate(BaseModel):
    """Текущий funding rate"""
    ts: int
    instrument_id: str
    funding_rate: float
    funding_time: int  # next funding time ms

class FundingHistoryPoint(BaseModel):
    funding_time: int
    funding_rate: float

class FundingHistory(BaseModel):
    ts: int
    instrument_id: str
    items: List[FundingHistoryPoint]

class OpenInterest(BaseModel):
    ts: int
    instrument_id: str
    open_interest: float  # contracts
    open_interest_usd: Optional[float] = None

class LongShortRatio(BaseModel):
    ts: int
    instrument_id: str
    long_ratio: float
    short_ratio: float
    long_short_ratio: float

class Liquidation(BaseModel):
    t: int
    side: Literal["buy", "sell"]
    price: float
    qty: float
    value_usd: Optional[float] = None

class LiquidationsResponse(BaseModel):
    ts: int
    instrument_id: str
    items: List[Liquidation]

class MarkPrice(BaseModel):
    ts: int
    instrument_id: str
    mark_price: float
    index_price: Optional[float] = None

# ═══════════════════════════════════════════════════════════════
# API RESPONSE TYPES
# ═══════════════════════════════════════════════════════════════

class DataQuality(BaseModel):
    """Качество данных для UI"""
    price: DataQualitySource = DataQualitySource.REALTIME
    market_cap: Optional[DataQualitySource] = None
    sources: List[str] = []

class GlobalMetrics(BaseModel):
    coverage_market_cap: Optional[float] = None
    coverage_volume_24h: Optional[float] = None
    btc_dominance: Optional[float] = None
    eth_dominance: Optional[float] = None

class BenchmarkAsset(BaseModel):
    asset_id: str
    symbol: str
    price: float
    change_24h: Optional[float] = None
    volume_24h: Optional[float] = None

class FearGreed(BaseModel):
    value: int
    label: str
    source: str = "internal"
    updated_at: int

class Sentiment(BaseModel):
    fear_greed: Optional[FearGreed] = None

class Activity(BaseModel):
    id: str
    type: str
    title: str
    asset_id: Optional[str] = None
    source: str = "intel"
    published_at: int
    url: Optional[str] = None

class MarketOverviewResponse(BaseModel):
    ts: int
    quote: str = "USD"
    global_metrics: GlobalMetrics = Field(alias="global")
    benchmarks: List[BenchmarkAsset] = []
    sentiment: Sentiment = Sentiment()
    top_gainers_24h: List[Dict[str, Any]] = []
    top_losers_24h: List[Dict[str, Any]] = []
    new_activities: List[Activity] = []
    
    class Config:
        populate_by_name = True

class Sparkline(BaseModel):
    range: str
    points: List[float]

class MarketAssetItem(BaseModel):
    asset_id: str
    rank: Optional[int] = None
    symbol: str
    name: str
    icon_url: Optional[str] = None
    price: float
    change_1h: Optional[float] = None
    change_24h: Optional[float] = None
    change_7d: Optional[float] = None
    market_cap: Optional[float] = None
    fdv: Optional[float] = None
    volume_24h: Optional[float] = None
    circulating_supply: Optional[float] = None
    max_supply: Optional[float] = None
    sparkline: Optional[Sparkline] = None
    data_quality: DataQuality = DataQuality()

class MarketAssetsResponse(BaseModel):
    ts: int
    tab: str = "full"
    quote: str = "USD"
    page: int = 1
    page_size: int = 100
    total: int = 0
    items: List[MarketAssetItem] = []

class Supplies(BaseModel):
    circulating: Optional[float] = None
    total: Optional[float] = None
    max: Optional[float] = None

class PriceRange(BaseModel):
    low: Optional[float] = None
    high: Optional[float] = None

class ATHInfo(BaseModel):
    price: Optional[float] = None
    date: Optional[str] = None

class AssetMetrics(BaseModel):
    quote: str = "USD"
    price: float
    change_24h: Optional[float] = None
    range_24h: Optional[PriceRange] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    fdv: Optional[float] = None
    dominance: Optional[float] = None
    supplies: Supplies = Supplies()
    ath: Optional[ATHInfo] = None
    atl: Optional[ATHInfo] = None

class AssetCoverage(BaseModel):
    venues: List[str] = []
    instruments: int = 0

class AssetResponse(BaseModel):
    ts: int
    asset: Asset
    metrics: AssetMetrics
    coverage: AssetCoverage

class PerformanceItem(BaseModel):
    range: str
    change: float

class AssetPerformanceResponse(BaseModel):
    ts: int
    asset_id: str
    quote: str = "USD"
    items: List[PerformanceItem] = []

class ChartPoint(BaseModel):
    t: int
    v: float

class AssetChartResponse(BaseModel):
    ts: int
    asset_id: str
    quote: str = "USD"
    series: str = "price"
    range: str = "7d"
    granularity: str = "1h"
    points: Optional[List[ChartPoint]] = None
    candles: Optional[List[Candle]] = None

class DerivativesInfo(BaseModel):
    mark_price: Optional[float] = None
    index_price: Optional[float] = None
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None

class VenueInstrument(BaseModel):
    instrument_id: str
    venue: str
    market_type: str
    native_symbol: str
    base: str
    quote: str
    last_price: float
    volume_24h: Optional[float] = None
    volume_share: Optional[float] = None
    spread_bps: Optional[float] = None
    derivatives: Optional[DerivativesInfo] = None

class AssetVenuesResponse(BaseModel):
    ts: int
    asset_id: str
    quote: str = "USD"
    type: str = "all"
    items: List[VenueInstrument] = []

# ═══════════════════════════════════════════════════════════════
# PROVIDER CAPABILITIES
# ═══════════════════════════════════════════════════════════════

class ProviderCapabilities(BaseModel):
    """Возможности провайдера"""
    venue: Venue
    has_spot: bool = False
    has_perp: bool = False
    has_futures: bool = False
    has_orderbook: bool = True
    has_trades: bool = True
    has_candles: bool = True
    has_funding: bool = False
    has_funding_history: bool = False
    has_open_interest: bool = False
    has_long_short_ratio: bool = False
    has_liquidations: bool = False
    has_mark_price: bool = False
    has_index_price: bool = False
    has_top_trader_ratio: bool = False
    has_agg_trades: bool = False
    has_websocket: bool = False
