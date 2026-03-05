"""
Aggregator Service
Агрегация данных из нескольких провайдеров
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import asyncio

from ..domain.types import (
    Venue, MarketType, Ticker, Candle,
    MarketAssetItem, DataQuality, DataQualitySource, Sparkline,
    GlobalMetrics, MarketOverviewResponse, BenchmarkAsset
)
from ..providers.registry import provider_registry
from .instrument_registry import instrument_registry

class Aggregator:
    """
    Агрегатор рыночных данных.
    Собирает данные из нескольких источников и предоставляет унифицированный view.
    """
    
    # Benchmark активы для overview
    BENCHMARK_ASSETS = ["btc", "eth", "sol", "bnb"]
    
    # Категории активов
    ASSET_CATEGORIES = {
        "btc": "Cryptocurrency",
        "eth": "Smart Contract Platform",
        "sol": "Smart Contract Platform",
        "bnb": "Exchange Token",
        "xrp": "Payment",
        "doge": "Meme",
        "ada": "Smart Contract Platform",
    }
    
    def __init__(self):
        self._ticker_cache: Dict[str, Ticker] = {}
        self._ticker_cache_ts: Dict[str, int] = {}
        self._cache_ttl_ms = 5000  # 5 секунд
    
    def _now_ms(self) -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    
    async def get_ticker_for_asset(self, asset_id: str) -> Optional[Ticker]:
        """Получает лучший тикер для актива"""
        # Проверяем кеш
        cache_key = f"ticker:{asset_id}"
        if cache_key in self._ticker_cache:
            if self._now_ms() - self._ticker_cache_ts.get(cache_key, 0) < self._cache_ttl_ms:
                return self._ticker_cache[cache_key]
        
        # Получаем primary инструмент
        instrument = instrument_registry.get_primary_instrument(asset_id, MarketType.PERP)
        if not instrument:
            instrument = instrument_registry.get_primary_instrument(asset_id)
        
        if not instrument:
            return None
        
        # Получаем провайдера
        provider = provider_registry.get(instrument.venue)
        if not provider:
            return None
        
        try:
            ticker = await provider.get_ticker(instrument.native_symbol)
            
            # Кешируем
            self._ticker_cache[cache_key] = ticker
            self._ticker_cache_ts[cache_key] = self._now_ms()
            
            return ticker
        except Exception as e:
            print(f"[Aggregator] Failed to get ticker for {asset_id}: {e}")
            return None
    
    async def get_candles_for_asset(
        self,
        asset_id: str,
        granularity: str = "1h",
        limit: int = 100
    ) -> List[Candle]:
        """Получает свечи для актива"""
        instrument = instrument_registry.get_primary_instrument(asset_id, MarketType.PERP)
        if not instrument:
            instrument = instrument_registry.get_primary_instrument(asset_id)
        
        if not instrument:
            return []
        
        provider = provider_registry.get(instrument.venue)
        if not provider:
            return []
        
        try:
            return await provider.get_candles(instrument.native_symbol, granularity, limit=limit)
        except Exception as e:
            print(f"[Aggregator] Failed to get candles for {asset_id}: {e}")
            return []
    
    async def build_market_asset_item(self, asset_id: str) -> Optional[MarketAssetItem]:
        """Строит MarketAssetItem для таблицы"""
        asset = instrument_registry.get_asset(asset_id)
        if not asset:
            return None
        
        ticker = await self.get_ticker_for_asset(asset_id)
        if not ticker:
            return None
        
        # Получаем источники данных
        venues = instrument_registry.get_venues_for_asset(asset_id)
        
        # Sparkline (7d, последние 168 точек по 1h)
        candles = await self.get_candles_for_asset(asset_id, "1h", 168)
        sparkline = None
        if candles:
            # Берем каждую 4-ю точку для 7d sparkline
            points = [c.c for c in candles[::4]]
            sparkline = Sparkline(range="7d", points=points[-42:])  # ~7 days
        
        # Рассчитываем изменения
        change_7d = None
        if candles and len(candles) >= 168:
            price_7d_ago = candles[0].c
            change_7d = (ticker.last - price_7d_ago) / price_7d_ago if price_7d_ago > 0 else None
        
        change_1h = None
        if candles and len(candles) >= 1:
            price_1h_ago = candles[-1].o
            change_1h = (ticker.last - price_1h_ago) / price_1h_ago if price_1h_ago > 0 else None
        
        return MarketAssetItem(
            asset_id=asset_id,
            symbol=asset.symbol,
            name=asset.name,
            icon_url=asset.icon_url,
            price=ticker.last,
            change_1h=change_1h,
            change_24h=ticker.change_24h,
            change_7d=change_7d,
            volume_24h=ticker.volume_24h,
            market_cap=None,  # Требует supply из Asset Intel
            fdv=None,
            circulating_supply=None,
            max_supply=None,
            sparkline=sparkline,
            data_quality=DataQuality(
                price=DataQualitySource.REALTIME,
                sources=[v.value for v in venues]
            )
        )
    
    async def get_market_assets(
        self,
        page: int = 1,
        page_size: int = 100,
        sort_by: str = "volume_24h",
        direction: str = "desc"
    ) -> List[MarketAssetItem]:
        """Получает список активов для таблицы"""
        # Убеждаемся что реестр синхронизирован
        await instrument_registry.sync_all()
        
        assets = instrument_registry.list_assets()
        
        # Параллельно получаем данные для всех активов
        tasks = [self.build_market_asset_item(a.asset_id) for a in assets[:page_size * page]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Фильтруем успешные результаты
        items = [r for r in results if isinstance(r, MarketAssetItem) and r is not None]
        
        # Сортировка
        reverse = direction == "desc"
        if sort_by == "volume_24h":
            items.sort(key=lambda x: x.volume_24h or 0, reverse=reverse)
        elif sort_by == "price":
            items.sort(key=lambda x: x.price or 0, reverse=reverse)
        elif sort_by == "change_24h":
            items.sort(key=lambda x: x.change_24h or 0, reverse=reverse)
        
        # Пагинация
        start = (page - 1) * page_size
        end = start + page_size
        
        # Добавляем rank
        for i, item in enumerate(items):
            item.rank = start + i + 1
        
        return items[start:end]
    
    async def get_market_overview(self) -> MarketOverviewResponse:
        """Получает overview для главной страницы"""
        await instrument_registry.sync_all()
        
        # Получаем benchmark тикеры
        benchmarks = []
        total_volume = 0
        btc_price = 0
        eth_price = 0
        
        for asset_id in self.BENCHMARK_ASSETS:
            ticker = await self.get_ticker_for_asset(asset_id)
            if ticker:
                benchmarks.append(BenchmarkAsset(
                    asset_id=asset_id,
                    symbol=asset_id.upper(),
                    price=ticker.last,
                    change_24h=ticker.change_24h,
                    volume_24h=ticker.volume_24h
                ))
                total_volume += ticker.volume_24h or 0
                
                if asset_id == "btc":
                    btc_price = ticker.last
                elif asset_id == "eth":
                    eth_price = ticker.last
        
        # Считаем coverage market cap (упрощенно - только BTC + ETH)
        # В реальности нужен supply из Asset Intel
        btc_supply = 19_900_000  # Примерное значение
        eth_supply = 120_000_000
        
        btc_mcap = btc_price * btc_supply
        eth_mcap = eth_price * eth_supply
        total_mcap = btc_mcap + eth_mcap  # Упрощенно
        
        btc_dominance = btc_mcap / total_mcap if total_mcap > 0 else 0
        eth_dominance = eth_mcap / total_mcap if total_mcap > 0 else 0
        
        return MarketOverviewResponse(
            ts=self._now_ms(),
            quote="USD",
            global_metrics=GlobalMetrics(
                coverage_market_cap=total_mcap,
                coverage_volume_24h=total_volume,
                btc_dominance=btc_dominance,
                eth_dominance=eth_dominance
            ),
            benchmarks=benchmarks,
            top_gainers_24h=[],  # Требует полный список активов
            top_losers_24h=[],
            new_activities=[]  # Из Asset Intel
        )
    
    async def get_top_gainers_losers(self, limit: int = 5) -> Dict[str, List[Dict]]:
        """Получает топ gainers/losers"""
        assets = await self.get_market_assets(page=1, page_size=100, sort_by="change_24h", direction="desc")
        
        gainers = [
            {"asset_id": a.asset_id, "symbol": a.symbol, "price": a.price, "change_24h": a.change_24h, "volume_24h": a.volume_24h}
            for a in assets if a.change_24h and a.change_24h > 0
        ][:limit]
        
        losers = [
            {"asset_id": a.asset_id, "symbol": a.symbol, "price": a.price, "change_24h": a.change_24h, "volume_24h": a.volume_24h}
            for a in sorted(assets, key=lambda x: x.change_24h or 0) if a.change_24h and a.change_24h < 0
        ][:limit]
        
        return {"gainers": gainers, "losers": losers}


# Singleton instance
aggregator = Aggregator()
