"""
Aggregation Engine v2
Сердце Market Data Engine - агрегация данных из множества провайдеров
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import statistics

from ..domain.types import (
    Venue, MarketType, Ticker, Candle,
    FundingRate, OpenInterest, Liquidation
)
from ..providers.registry import provider_registry
from .instrument_registry import instrument_registry

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"

@dataclass
class ProviderScore:
    """Скоринг провайдера для выбора лучшего источника"""
    venue: Venue
    health: float = 1.0  # 0-1
    freshness: float = 1.0  # 0-1, based on data age
    liquidity: float = 1.0  # 0-1, based on volume/spread
    latency: float = 1.0  # 0-1, inverse of latency
    
    @property
    def total_score(self) -> float:
        """Weighted total score"""
        weights = {
            "health": 0.4,
            "freshness": 0.3,
            "liquidity": 0.2,
            "latency": 0.1
        }
        return (
            self.health * weights["health"] +
            self.freshness * weights["freshness"] +
            self.liquidity * weights["liquidity"] +
            self.latency * weights["latency"]
        )

@dataclass
class VolumeBreakdown:
    """Volume разбивка по типам рынков"""
    spot: float = 0.0
    perp: float = 0.0
    futures: float = 0.0
    
    @property
    def total(self) -> float:
        return self.spot + self.perp + self.futures

@dataclass
class DerivativesSnapshot:
    """Агрегированные деривативные метрики"""
    funding_rate: Optional[float] = None
    funding_rate_annualized: Optional[float] = None
    open_interest_usd: Optional[float] = None
    liquidations_1h_usd: Optional[float] = None
    liquidations_24h_usd: Optional[float] = None
    long_short_ratio: Optional[float] = None

@dataclass
class QualityMetrics:
    """Метрики качества данных"""
    freshness_ms: int = 0
    health: HealthStatus = HealthStatus.HEALTHY
    confidence: float = 1.0
    sources_count: int = 0
    outliers_removed: int = 0

@dataclass
class AssetMarketSnapshot:
    """
    Главная единица агрегации - полный снимок рынка актива.
    Это то, что сохраняется в Redis и отдается через API.
    """
    ts: int
    asset_id: str
    quote: str = "USD"
    price: float = 0.0
    price_change_24h: Optional[float] = None
    volume: VolumeBreakdown = field(default_factory=VolumeBreakdown)
    derivatives: DerivativesSnapshot = field(default_factory=DerivativesSnapshot)
    sources: Dict[str, List[str]] = field(default_factory=dict)
    quality: QualityMetrics = field(default_factory=QualityMetrics)
    
    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "asset_id": self.asset_id,
            "quote": self.quote,
            "price": self.price,
            "change_24h": self.price_change_24h,
            "volume": {
                "spot": self.volume.spot,
                "perp": self.volume.perp,
                "futures": self.volume.futures,
                "total": self.volume.total
            },
            "derivatives": {
                "funding_rate": self.derivatives.funding_rate,
                "funding_rate_annualized": self.derivatives.funding_rate_annualized,
                "open_interest_usd": self.derivatives.open_interest_usd,
                "liquidations_1h_usd": self.derivatives.liquidations_1h_usd,
                "long_short_ratio": self.derivatives.long_short_ratio
            },
            "sources": self.sources,
            "quality": {
                "freshness_ms": self.quality.freshness_ms,
                "health": self.quality.health.value,
                "confidence": self.quality.confidence,
                "sources_count": self.quality.sources_count
            }
        }

@dataclass
class GlobalMarketSnapshot:
    """Глобальные метрики рынка"""
    ts: int
    quote: str = "USD"
    coverage_market_cap: Optional[float] = None
    coverage_volume_24h: float = 0.0
    btc_dominance: Optional[float] = None
    eth_dominance: Optional[float] = None
    active_assets: int = 0
    
    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "quote": self.quote,
            "coverage_market_cap": self.coverage_market_cap,
            "coverage_volume_24h": self.coverage_volume_24h,
            "btc_dominance": self.btc_dominance,
            "eth_dominance": self.eth_dominance,
            "active_assets": self.active_assets
        }


class AggregationEngineV2:
    """
    Aggregation Engine v2
    
    Принципы:
    1. Агрегатор НЕ ходит в биржи напрямую - читает из провайдеров
    2. Price = median (устойчив к выбросам) или VWAP (точнее)
    3. Volume суммируется отдельно по типам (spot/perp/futures)
    4. Каждый источник имеет score для выбора лучшего
    """
    
    # Outlier threshold - отклонение от медианы
    OUTLIER_THRESHOLD = 0.05  # 5%
    
    # Минимальный confidence для включения в агрегацию
    MIN_CONFIDENCE = 0.5
    
    def __init__(self):
        self._snapshot_cache: Dict[str, AssetMarketSnapshot] = {}
        self._global_snapshot: Optional[GlobalMarketSnapshot] = None
        self._provider_scores: Dict[Venue, ProviderScore] = {}
    
    def _now_ms(self) -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    
    # ═══════════════════════════════════════════════════════════════
    # PRICE AGGREGATION
    # ═══════════════════════════════════════════════════════════════
    
    def aggregate_price_median(self, prices: List[float]) -> Tuple[float, int]:
        """
        Агрегация цены методом медианы.
        Возвращает (median_price, outliers_removed)
        """
        if not prices:
            return 0.0, 0
        
        if len(prices) == 1:
            return prices[0], 0
        
        # Первая итерация - получаем медиану
        median = statistics.median(prices)
        
        # Фильтруем outliers
        filtered = [p for p in prices if abs(p - median) / median <= self.OUTLIER_THRESHOLD]
        outliers_removed = len(prices) - len(filtered)
        
        if not filtered:
            return median, outliers_removed
        
        # Финальная медиана без outliers
        return statistics.median(filtered), outliers_removed
    
    def aggregate_price_vwap(self, price_volume_pairs: List[Tuple[float, float]]) -> float:
        """
        Volume Weighted Average Price.
        price_volume_pairs: [(price, volume), ...]
        """
        if not price_volume_pairs:
            return 0.0
        
        total_value = sum(p * v for p, v in price_volume_pairs)
        total_volume = sum(v for _, v in price_volume_pairs)
        
        if total_volume == 0:
            return price_volume_pairs[0][0]  # fallback to first price
        
        return total_value / total_volume
    
    # ═══════════════════════════════════════════════════════════════
    # VOLUME AGGREGATION
    # ═══════════════════════════════════════════════════════════════
    
    def aggregate_volume(self, volumes_by_type: Dict[MarketType, List[float]]) -> VolumeBreakdown:
        """Агрегация volume по типам рынков"""
        breakdown = VolumeBreakdown()
        
        for market_type, volumes in volumes_by_type.items():
            total = sum(volumes)
            if market_type == MarketType.SPOT:
                breakdown.spot = total
            elif market_type == MarketType.PERP:
                breakdown.perp = total
            elif market_type == MarketType.FUTURES:
                breakdown.futures = total
        
        return breakdown
    
    # ═══════════════════════════════════════════════════════════════
    # DERIVATIVES AGGREGATION
    # ═══════════════════════════════════════════════════════════════
    
    def aggregate_funding(self, funding_rates: List[float]) -> Tuple[float, float]:
        """
        Агрегация funding rate (median).
        Returns: (funding_rate, annualized_rate)
        """
        if not funding_rates:
            return None, None
        
        median_rate = statistics.median(funding_rates)
        # Annualized = rate * 3 (8h intervals) * 365
        annualized = median_rate * 3 * 365
        
        return median_rate, annualized
    
    def aggregate_open_interest(self, oi_values: List[float]) -> float:
        """Агрегация OI (sum)"""
        return sum(oi_values) if oi_values else 0.0
    
    # ═══════════════════════════════════════════════════════════════
    # MAIN AGGREGATION
    # ═══════════════════════════════════════════════════════════════
    
    async def build_asset_snapshot(self, asset_id: str) -> Optional[AssetMarketSnapshot]:
        """
        Строит полный снимок рынка для актива.
        Собирает данные со всех провайдеров и агрегирует.
        """
        instruments = instrument_registry.get_asset_instruments(asset_id)
        if not instruments:
            return None
        
        # Коллекторы данных
        prices: List[float] = []
        price_volume_pairs: List[Tuple[float, float]] = []
        volumes_by_type: Dict[MarketType, List[float]] = {
            MarketType.SPOT: [],
            MarketType.PERP: [],
            MarketType.FUTURES: []
        }
        funding_rates: List[float] = []
        oi_values: List[float] = []
        sources: Dict[str, List[str]] = {
            "price": [],
            "volume": [],
            "funding": [],
            "oi": []
        }
        changes_24h: List[float] = []
        
        # Собираем данные со всех инструментов
        for inst in instruments:
            provider = provider_registry.get(inst.venue)
            if not provider:
                continue
            
            try:
                ticker = await provider.get_ticker(inst.native_symbol)
                
                # Price
                if ticker.last and ticker.last > 0:
                    prices.append(ticker.last)
                    sources["price"].append(inst.venue.value)
                    
                    if ticker.volume_24h:
                        price_volume_pairs.append((ticker.last, ticker.volume_24h))
                
                # Volume
                if ticker.volume_24h:
                    if inst.market_type in volumes_by_type:
                        volumes_by_type[inst.market_type].append(ticker.volume_24h)
                    sources["volume"].append(inst.venue.value)
                
                # 24h change
                if ticker.change_24h is not None:
                    changes_24h.append(ticker.change_24h)
                
                # Derivatives
                if inst.market_type == MarketType.PERP:
                    caps = provider.capabilities()
                    
                    # Funding
                    if caps.has_funding:
                        try:
                            funding = await provider.get_funding(inst.native_symbol)
                            if funding and funding.funding_rate:
                                funding_rates.append(funding.funding_rate)
                                sources["funding"].append(inst.venue.value)
                        except:
                            pass
                    
                    # Open Interest
                    if caps.has_open_interest:
                        try:
                            oi = await provider.get_open_interest(inst.native_symbol)
                            if oi and oi.open_interest_usd:
                                oi_values.append(oi.open_interest_usd)
                                sources["oi"].append(inst.venue.value)
                        except:
                            pass
            
            except Exception as e:
                print(f"[Aggregator] Error fetching {inst.instrument_id}: {e}")
                continue
        
        if not prices:
            return None
        
        # Агрегация
        price, outliers = self.aggregate_price_median(prices)
        vwap_price = self.aggregate_price_vwap(price_volume_pairs) if price_volume_pairs else price
        volume = self.aggregate_volume(volumes_by_type)
        funding_rate, funding_annualized = self.aggregate_funding(funding_rates)
        oi_total = self.aggregate_open_interest(oi_values)
        
        # Change 24h
        change_24h = statistics.median(changes_24h) if changes_24h else None
        
        # Quality metrics
        confidence = min(1.0, len(prices) / 4)  # Max confidence with 4+ sources
        
        snapshot = AssetMarketSnapshot(
            ts=self._now_ms(),
            asset_id=asset_id,
            quote="USD",
            price=price,  # Используем median как default
            price_change_24h=change_24h,
            volume=volume,
            derivatives=DerivativesSnapshot(
                funding_rate=funding_rate,
                funding_rate_annualized=funding_annualized,
                open_interest_usd=oi_total if oi_total > 0 else None
            ),
            sources=sources,
            quality=QualityMetrics(
                freshness_ms=0,  # TODO: track actual freshness
                health=HealthStatus.HEALTHY,
                confidence=confidence,
                sources_count=len(prices),
                outliers_removed=outliers
            )
        )
        
        # Cache
        self._snapshot_cache[asset_id] = snapshot
        
        return snapshot
    
    async def build_global_snapshot(self) -> GlobalMarketSnapshot:
        """Строит глобальные метрики рынка"""
        await instrument_registry.sync_all()
        
        assets = instrument_registry.list_assets()
        total_volume = 0.0
        btc_volume = 0.0
        eth_volume = 0.0
        active_count = 0
        
        # Параллельно собираем snapshots
        tasks = [self.build_asset_snapshot(a.asset_id) for a in assets[:100]]  # Top 100
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, AssetMarketSnapshot):
                active_count += 1
                total_volume += result.volume.total
                
                if result.asset_id == "btc":
                    btc_volume = result.volume.total
                elif result.asset_id == "eth":
                    eth_volume = result.volume.total
        
        # Dominance by volume (temporary until we have supply data)
        btc_dominance = btc_volume / total_volume if total_volume > 0 else None
        eth_dominance = eth_volume / total_volume if total_volume > 0 else None
        
        self._global_snapshot = GlobalMarketSnapshot(
            ts=self._now_ms(),
            quote="USD",
            coverage_volume_24h=total_volume,
            btc_dominance=btc_dominance,
            eth_dominance=eth_dominance,
            active_assets=active_count
        )
        
        return self._global_snapshot
    
    # ═══════════════════════════════════════════════════════════════
    # MARKET PAIRS (для /assets/{id}/venues)
    # ═══════════════════════════════════════════════════════════════
    
    async def get_market_pairs(self, asset_id: str) -> List[dict]:
        """
        Получает список market pairs с аналитикой.
        Аналог CMC "market pairs".
        """
        instruments = instrument_registry.get_asset_instruments(asset_id)
        if not instruments:
            return []
        
        pairs = []
        total_volume = 0.0
        
        # Первый проход - собираем данные
        for inst in instruments:
            provider = provider_registry.get(inst.venue)
            if not provider:
                continue
            
            try:
                ticker = await provider.get_ticker(inst.native_symbol)
                
                pair = {
                    "instrument_id": inst.instrument_id,
                    "venue": inst.venue.value,
                    "market_type": inst.market_type.value,
                    "native_symbol": inst.native_symbol,
                    "price": ticker.last,
                    "volume_24h": ticker.volume_24h or 0,
                    "spread_bps": None
                }
                
                # Spread
                if ticker.bid and ticker.ask and ticker.bid > 0:
                    spread = (ticker.ask - ticker.bid) / ticker.bid * 10000
                    pair["spread_bps"] = round(spread, 2)
                
                pairs.append(pair)
                total_volume += ticker.volume_24h or 0
                
            except:
                continue
        
        # Второй проход - volume share
        for pair in pairs:
            if total_volume > 0:
                pair["volume_share"] = round(pair["volume_24h"] / total_volume, 4)
            else:
                pair["volume_share"] = 0
        
        # Сортировка по volume
        pairs.sort(key=lambda x: x["volume_24h"], reverse=True)
        
        return pairs
    
    # ═══════════════════════════════════════════════════════════════
    # TOP GAINERS / LOSERS
    # ═══════════════════════════════════════════════════════════════
    
    async def get_top_movers(self, limit: int = 10) -> Dict[str, List[dict]]:
        """Топ gainers и losers по 24h change"""
        await instrument_registry.sync_all()
        
        assets = instrument_registry.list_assets()
        movers = []
        
        for asset in assets[:100]:
            snapshot = self._snapshot_cache.get(asset.asset_id)
            if not snapshot:
                snapshot = await self.build_asset_snapshot(asset.asset_id)
            
            if snapshot and snapshot.price_change_24h is not None:
                movers.append({
                    "asset_id": snapshot.asset_id,
                    "symbol": asset.symbol,
                    "price": snapshot.price,
                    "change_24h": snapshot.price_change_24h,
                    "volume_24h": snapshot.volume.total
                })
        
        # Сортировка
        gainers = sorted(
            [m for m in movers if m["change_24h"] > 0],
            key=lambda x: x["change_24h"],
            reverse=True
        )[:limit]
        
        losers = sorted(
            [m for m in movers if m["change_24h"] < 0],
            key=lambda x: x["change_24h"]
        )[:limit]
        
        return {"gainers": gainers, "losers": losers}
    
    def get_cached_snapshot(self, asset_id: str) -> Optional[AssetMarketSnapshot]:
        """Получает snapshot из кеша"""
        return self._snapshot_cache.get(asset_id)
    
    def get_global_snapshot(self) -> Optional[GlobalMarketSnapshot]:
        """Получает глобальный snapshot"""
        return self._global_snapshot


# Singleton instance
aggregation_engine = AggregationEngineV2()
