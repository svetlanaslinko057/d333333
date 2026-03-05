"""
Candle Ingestion Worker
Stage 7: Historical Data Pipeline

Fetches OHLCV candles from exchanges and stores in ClickHouse.
Supports backfill and sync modes.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from enum import Enum

from ..store.clickhouse_store import clickhouse_store
from ..store.redis_store import redis_store, RedisKeys
from ..providers.registry import provider_registry
from .instrument_registry import instrument_registry

logger = logging.getLogger(__name__)


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


# Timeframe to seconds mapping
TF_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}

# Default backfill depth per timeframe (in candles)
BACKFILL_DEPTH = {
    "1m": 10080,    # 7 days
    "5m": 8640,     # 30 days
    "15m": 17280,   # 180 days
    "1h": 8760,     # 1 year
    "4h": 10950,    # 5 years
    "1d": 3650,     # 10 years
    "1w": 520,      # 10 years
}

# Sync interval per timeframe (seconds)
SYNC_INTERVAL = {
    "1m": 60,
    "5m": 60,
    "15m": 60,
    "1h": 300,
    "4h": 300,
    "1d": 3600,
    "1w": 3600,
}


class CandleIngestor:
    """
    Candle Ingestion Worker.
    
    Responsibilities:
    1. Backfill historical candles on startup
    2. Sync new candles periodically
    3. Track ingestion status in Redis
    """
    
    def __init__(self):
        self._running = False
        self._tasks: List[asyncio.Task] = []
        
        # Priority symbols for initial backfill
        self.priority_symbols = [
            "BTC", "ETH", "SOL", "BNB", "XRP", 
            "DOGE", "ADA", "AVAX", "DOT", "LINK"
        ]
        
        # Timeframes to ingest
        self.timeframes = ["1m", "1h", "1d"]  # Start with these
        
    async def start(self):
        """Start the ingestion worker"""
        if self._running:
            logger.warning("[Ingestor] Already running")
            return
        
        logger.info("[Ingestor] Starting candle ingestion worker...")
        
        # Connect to stores
        try:
            clickhouse_store.connect()
            await redis_store.connect()
        except Exception as e:
            logger.error(f"[Ingestor] Store connection failed: {e}")
            return
        
        self._running = True
        
        # Launch tasks
        self._tasks = [
            asyncio.create_task(self._backfill_loop()),
            asyncio.create_task(self._sync_loop()),
        ]
        
        logger.info("[Ingestor] Worker started")
    
    async def stop(self):
        """Stop the ingestion worker"""
        self._running = False
        
        for task in self._tasks:
            task.cancel()
        
        logger.info("[Ingestor] Worker stopped")
    
    # ═══════════════════════════════════════════════════════════════
    # BACKFILL LOOP
    # ═══════════════════════════════════════════════════════════════
    
    async def _backfill_loop(self):
        """Initial backfill of historical data"""
        logger.info("[Ingestor] Backfill loop started")
        
        # Wait for registry to be populated
        await asyncio.sleep(5)
        
        try:
            # Get priority instruments
            instruments = self._get_priority_instruments()
            logger.info(f"[Ingestor] Backfilling {len(instruments)} instruments")
            
            for inst in instruments:
                if not self._running:
                    break
                
                for tf in self.timeframes:
                    if not self._running:
                        break
                    
                    try:
                        await self._backfill_instrument(inst, tf)
                        await asyncio.sleep(1)  # Rate limit
                    except Exception as e:
                        logger.error(f"[Ingestor] Backfill error {inst['instrument_id']} {tf}: {e}")
            
            logger.info("[Ingestor] Initial backfill complete")
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[Ingestor] Backfill loop error: {e}")
    
    async def _backfill_instrument(
        self,
        instrument: Dict[str, Any],
        tf: str,
        depth: Optional[int] = None
    ):
        """Backfill candles for a single instrument/timeframe"""
        exchange = instrument['venue']
        symbol = instrument['native_symbol']
        instrument_id = instrument['instrument_id']
        
        # Check if already backfilled
        status_key = f"ingest:backfill:{exchange}:{symbol}:{tf}"
        status = await redis_store._pool.get(status_key) if redis_store._connected else None
        
        if status == "done":
            logger.debug(f"[Ingestor] Already backfilled {symbol} {tf}")
            return
        
        depth = depth or BACKFILL_DEPTH.get(tf, 500)
        
        logger.info(f"[Ingestor] Backfilling {exchange}:{symbol} {tf} (depth={depth})")
        
        try:
            # Get provider
            from ..domain.types import Venue
            venue = Venue(exchange)
            provider = provider_registry.get(venue)
            
            if not provider:
                logger.warning(f"[Ingestor] No provider for {exchange}")
                return
            
            # Fetch candles
            candles = await provider.get_candles(
                native_symbol=symbol,
                granularity=tf,
                limit=min(depth, 1000)  # API limit
            )
            
            if not candles:
                logger.warning(f"[Ingestor] No candles returned for {symbol} {tf}")
                return
            
            # Prepare for insert
            rows = []
            for c in candles:
                rows.append({
                    'exchange': exchange,
                    'symbol': instrument_id,  # Use normalized ID
                    'tf': tf,
                    'ts': c.t / 1000 if c.t > 1e10 else c.t,  # Handle ms vs s
                    'open': c.o,
                    'high': c.h,
                    'low': c.l,
                    'close': c.c,
                    'volume': c.v
                })
            
            # Insert to ClickHouse
            count = clickhouse_store.insert_candles(rows)
            
            # Mark as done
            if redis_store._connected:
                await redis_store._pool.setex(status_key, 86400 * 7, "done")
            
            logger.info(f"[Ingestor] Backfilled {count} candles for {symbol} {tf}")
            
        except Exception as e:
            logger.error(f"[Ingestor] Backfill failed {symbol} {tf}: {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # SYNC LOOP
    # ═══════════════════════════════════════════════════════════════
    
    async def _sync_loop(self):
        """Continuous sync of new candles"""
        logger.info("[Ingestor] Sync loop started")
        
        # Wait for backfill to start
        await asyncio.sleep(30)
        
        while self._running:
            try:
                instruments = self._get_priority_instruments()
                
                for inst in instruments[:20]:  # Top 20 for sync
                    if not self._running:
                        break
                    
                    for tf in self.timeframes:
                        try:
                            await self._sync_instrument(inst, tf)
                        except Exception as e:
                            logger.debug(f"[Ingestor] Sync error {inst['instrument_id']} {tf}: {e}")
                
                # Wait before next sync cycle
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Ingestor] Sync loop error: {e}")
                await asyncio.sleep(30)
    
    async def _sync_instrument(
        self,
        instrument: Dict[str, Any],
        tf: str
    ):
        """Sync latest candles for an instrument"""
        exchange = instrument['venue']
        symbol = instrument['native_symbol']
        instrument_id = instrument['instrument_id']
        
        try:
            # Get latest ts from ClickHouse
            latest_ts = clickhouse_store.get_latest_candle_ts(exchange, instrument_id, tf)
            
            if not latest_ts:
                # No data - do backfill instead
                await self._backfill_instrument(instrument, tf, depth=100)
                return
            
            # Get provider
            from ..domain.types import Venue
            venue = Venue(exchange)
            provider = provider_registry.get(venue)
            
            if not provider:
                return
            
            # Fetch recent candles
            candles = await provider.get_candles(
                native_symbol=symbol,
                granularity=tf,
                limit=10  # Just recent ones
            )
            
            if not candles:
                return
            
            # Filter new candles
            rows = []
            for c in candles:
                ts = c.t / 1000 if c.t > 1e10 else c.t
                candle_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                
                if candle_dt > latest_ts.replace(tzinfo=timezone.utc):
                    rows.append({
                        'exchange': exchange,
                        'symbol': instrument_id,
                        'tf': tf,
                        'ts': ts,
                        'open': c.o,
                        'high': c.h,
                        'low': c.l,
                        'close': c.c,
                        'volume': c.v
                    })
            
            if rows:
                count = clickhouse_store.insert_candles(rows)
                logger.debug(f"[Ingestor] Synced {count} new candles for {symbol} {tf}")
                
                # Update Redis status
                if redis_store._connected:
                    status_key = f"ingest:last_sync:{exchange}:{instrument_id}:{tf}"
                    await redis_store._pool.setex(
                        status_key, 
                        3600, 
                        str(int(datetime.now(timezone.utc).timestamp()))
                    )
            
        except Exception as e:
            raise
    
    # ═══════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════
    
    def _get_priority_instruments(self) -> List[Dict[str, Any]]:
        """Get priority instruments for ingestion"""
        instruments = []
        
        # Get from registry
        all_instruments = instrument_registry.list_instruments()
        
        for inst in all_instruments:
            # Check if base asset is in priority list
            base = inst.base.upper() if inst.base else ""
            
            if base in self.priority_symbols:
                instruments.append({
                    'instrument_id': inst.instrument_id,
                    'venue': inst.venue.value,
                    'native_symbol': inst.native_symbol,
                    'base_asset': base,
                    'market_type': inst.market_type.value
                })
        
        # Sort by priority
        def priority_sort(x):
            try:
                return self.priority_symbols.index(x['base_asset'])
            except ValueError:
                return 999
        
        instruments.sort(key=priority_sort)
        
        return instruments
    
    async def status(self) -> Dict[str, Any]:
        """Get ingestion status"""
        ch_stats = clickhouse_store.stats()
        
        return {
            "running": self._running,
            "active_tasks": len([t for t in self._tasks if not t.done()]),
            "timeframes": self.timeframes,
            "priority_symbols": self.priority_symbols,
            "clickhouse": ch_stats
        }
    
    async def manual_backfill(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        depth: int = 500
    ) -> Dict[str, Any]:
        """Manual backfill trigger"""
        instrument = {
            'instrument_id': f"{exchange}:spot:{symbol}",
            'venue': exchange,
            'native_symbol': symbol,
            'base_asset': symbol.split('-')[0] if '-' in symbol else symbol
        }
        
        try:
            await self._backfill_instrument(instrument, tf, depth)
            return {"success": True, "message": f"Backfilled {symbol} {tf}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Singleton
candle_ingestor = CandleIngestor()
