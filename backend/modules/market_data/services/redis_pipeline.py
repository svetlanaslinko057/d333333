"""
Redis Data Pipeline
Асинхронный pipeline для заполнения Redis данными из провайдеров.
Stage 5: Redis Realtime Layer
"""

import asyncio
import logging
from typing import Optional, List, Dict
from datetime import datetime, timezone

from ..store.redis_store import redis_store
from ..providers.registry import provider_registry
from .instrument_registry import instrument_registry
from .aggregation_engine import aggregation_engine

logger = logging.getLogger(__name__)


class RedisPipeline:
    """
    Redis Pipeline - центральный компонент для синхронизации данных.
    
    Принципы:
    1. Периодически собирает данные со всех провайдеров
    2. Нормализует и записывает в Redis с TTL
    3. Публикует обновления через PubSub
    """
    
    def __init__(self):
        self._running = False
        self._tasks: List[asyncio.Task] = []
        
        # Интервалы обновления (в секундах)
        self.TICKER_INTERVAL = 3  # Fast - price updates
        self.FUNDING_INTERVAL = 60  # Slow - every minute
        self.ASSET_SNAPSHOT_INTERVAL = 5  # Aggregated snapshots
        self.GLOBAL_SNAPSHOT_INTERVAL = 30  # Global metrics
        
    async def start(self):
        """Запускает все pipelines"""
        if self._running:
            logger.warning("[Pipeline] Already running")
            return
        
        logger.info("[Pipeline] Starting Redis data pipeline...")
        
        # Connect to Redis
        try:
            await redis_store.connect()
        except Exception as e:
            logger.error(f"[Pipeline] Redis connection failed: {e}")
            return
        
        self._running = True
        
        # Launch parallel tasks
        self._tasks = [
            asyncio.create_task(self._ticker_loop()),
            asyncio.create_task(self._funding_loop()),
            asyncio.create_task(self._asset_snapshot_loop()),
            asyncio.create_task(self._global_snapshot_loop()),
        ]
        
        logger.info("[Pipeline] All loops started")
    
    async def stop(self):
        """Останавливает все pipelines"""
        self._running = False
        
        for task in self._tasks:
            task.cancel()
        
        await redis_store.disconnect()
        logger.info("[Pipeline] Stopped")
    
    # ═══════════════════════════════════════════════════════════════
    # TICKER LOOP - High frequency price updates
    # ═══════════════════════════════════════════════════════════════
    
    async def _ticker_loop(self):
        """Loop для обновления тикеров"""
        logger.info("[Pipeline] Ticker loop started")
        
        while self._running:
            try:
                await self._update_tickers()
                await asyncio.sleep(self.TICKER_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Pipeline] Ticker loop error: {e}")
                await asyncio.sleep(5)
    
    async def _update_tickers(self):
        """Обновляет все тикеры в Redis"""
        instruments = instrument_registry.list_instruments()[:200]  # Top 200
        
        if not instruments:
            logger.warning("[Pipeline] No instruments to update")
            return
        
        # Group by venue for batch requests
        by_venue: Dict[str, List] = {}
        for inst in instruments:
            venue = inst.venue.value
            if venue not in by_venue:
                by_venue[venue] = []
            by_venue[venue].append(inst)
        
        # Parallel fetch per venue
        tasks = []
        for venue_name, venue_instruments in by_venue.items():
            tasks.append(self._fetch_venue_tickers(venue_name, venue_instruments))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful updates
        total = sum(r for r in results if isinstance(r, int))
        if total > 0:
            logger.debug(f"[Pipeline] Updated {total} tickers")
    
    async def _fetch_venue_tickers(self, venue_name: str, instruments: List) -> int:
        """Получает тикеры с одной биржи"""
        from ..domain.types import Venue
        
        try:
            venue = Venue(venue_name)
            provider = provider_registry.get(venue)
            if not provider:
                return 0
            
            count = 0
            batch = {}
            
            for inst in instruments[:50]:  # Limit per batch
                try:
                    ticker = await provider.get_ticker(inst.native_symbol)
                    
                    ticker_data = {
                        "ts": ticker.ts,
                        "instrument_id": ticker.instrument_id,
                        "last": ticker.last,
                        "bid": ticker.bid,
                        "ask": ticker.ask,
                        "change_24h": ticker.change_24h,
                        "high_24h": ticker.high_24h,
                        "low_24h": ticker.low_24h,
                        "volume_24h": ticker.volume_24h,
                        "trades_24h": ticker.trades_24h
                    }
                    
                    batch[inst.instrument_id] = ticker_data
                    count += 1
                except Exception:
                    pass
            
            # Batch write to Redis
            if batch:
                await redis_store.set_batch_tickers(batch)
                logger.info(f"[Pipeline] Wrote {len(batch)} tickers from {venue_name}")
            
            return count
        except Exception as e:
            logger.error(f"[Pipeline] Venue {venue_name} ticker fetch error: {e}")
            return 0
    
    # ═══════════════════════════════════════════════════════════════
    # FUNDING LOOP - Derivatives data
    # ═══════════════════════════════════════════════════════════════
    
    async def _funding_loop(self):
        """Loop для обновления funding rates"""
        logger.info("[Pipeline] Funding loop started")
        
        while self._running:
            try:
                await self._update_funding()
                await asyncio.sleep(self.FUNDING_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Pipeline] Funding loop error: {e}")
                await asyncio.sleep(30)
    
    async def _update_funding(self):
        """Обновляет funding rates и OI"""
        from ..domain.types import MarketType, Venue
        
        instruments = instrument_registry.list_instruments(market_type=MarketType.PERP)[:100]
        
        count = 0
        for inst in instruments:
            try:
                provider = provider_registry.get(inst.venue)
                if not provider:
                    continue
                
                caps = provider.capabilities()
                
                # Funding Rate
                if caps.has_funding:
                    try:
                        funding = await provider.get_funding(inst.native_symbol)
                        if funding:
                            funding_data = {
                                "ts": funding.ts,
                                "instrument_id": funding.instrument_id,
                                "funding_rate": funding.funding_rate,
                                "funding_time": funding.funding_time
                            }
                            await redis_store.set_funding(inst.instrument_id, funding_data)
                            count += 1
                    except Exception:
                        pass
                
                # Open Interest
                if caps.has_open_interest:
                    try:
                        oi = await provider.get_open_interest(inst.native_symbol)
                        if oi:
                            oi_data = {
                                "ts": oi.ts,
                                "instrument_id": oi.instrument_id,
                                "open_interest": oi.open_interest,
                                "open_interest_usd": oi.open_interest_usd
                            }
                            await redis_store.set_open_interest(inst.instrument_id, oi_data)
                    except Exception:
                        pass
                
            except Exception:
                pass
        
        if count > 0:
            logger.debug(f"[Pipeline] Updated {count} funding rates")
    
    # ═══════════════════════════════════════════════════════════════
    # ASSET SNAPSHOT LOOP - Aggregated data
    # ═══════════════════════════════════════════════════════════════
    
    async def _asset_snapshot_loop(self):
        """Loop для обновления asset snapshots"""
        logger.info("[Pipeline] Asset snapshot loop started")
        
        # Wait for initial data
        await asyncio.sleep(5)
        
        while self._running:
            try:
                await self._update_asset_snapshots()
                await asyncio.sleep(self.ASSET_SNAPSHOT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Pipeline] Asset snapshot loop error: {e}")
                await asyncio.sleep(10)
    
    async def _update_asset_snapshots(self):
        """Обновляет asset snapshots (aggregated)"""
        assets = instrument_registry.list_assets()[:100]  # Top 100
        
        count = 0
        for asset in assets:
            try:
                snapshot = await aggregation_engine.build_asset_snapshot(asset.asset_id)
                if snapshot:
                    await redis_store.set_asset_snapshot(asset.asset_id, snapshot.to_dict())
                    count += 1
            except Exception:
                pass
        
        if count > 0:
            logger.debug(f"[Pipeline] Updated {count} asset snapshots")
    
    # ═══════════════════════════════════════════════════════════════
    # GLOBAL SNAPSHOT LOOP
    # ═══════════════════════════════════════════════════════════════
    
    async def _global_snapshot_loop(self):
        """Loop для обновления global snapshot"""
        logger.info("[Pipeline] Global snapshot loop started")
        
        # Wait for initial data
        await asyncio.sleep(10)
        
        while self._running:
            try:
                snapshot = await aggregation_engine.build_global_snapshot()
                await redis_store.set_global_snapshot(snapshot.to_dict())
                logger.debug("[Pipeline] Updated global snapshot")
                await asyncio.sleep(self.GLOBAL_SNAPSHOT_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Pipeline] Global snapshot loop error: {e}")
                await asyncio.sleep(30)
    
    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API - Manual triggers
    # ═══════════════════════════════════════════════════════════════
    
    async def warm_cache(self):
        """Прогревает кеш при старте"""
        logger.info("[Pipeline] Warming cache...")
        
        try:
            await self._update_tickers()
            await self._update_funding()
            await self._update_asset_snapshots()
            
            global_snapshot = await aggregation_engine.build_global_snapshot()
            await redis_store.set_global_snapshot(global_snapshot.to_dict())
            
            logger.info("[Pipeline] Cache warmed")
        except Exception as e:
            logger.error(f"[Pipeline] Cache warm failed: {e}")
    
    async def status(self) -> dict:
        """Статус pipeline"""
        redis_health = await redis_store.health()
        redis_stats = await redis_store.stats() if redis_health["healthy"] else {}
        
        return {
            "running": self._running,
            "active_tasks": len([t for t in self._tasks if not t.done()]),
            "redis": redis_health,
            "redis_stats": redis_stats,
            "intervals": {
                "ticker_sec": self.TICKER_INTERVAL,
                "funding_sec": self.FUNDING_INTERVAL,
                "asset_snapshot_sec": self.ASSET_SNAPSHOT_INTERVAL,
                "global_snapshot_sec": self.GLOBAL_SNAPSHOT_INTERVAL
            }
        }


# Singleton
redis_pipeline = RedisPipeline()
