"""
Redis Store - Realtime Market Data Cache
Production-grade Redis layer для Market Data Engine
"""

import redis.asyncio as redis
import json
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
import os
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# REDIS KEYS
# ═══════════════════════════════════════════════════════════════

class RedisKeys:
    """Ключи Redis для market data"""
    
    # Instrument Layer (raw exchange data)
    @staticmethod
    def ticker(instrument_id: str) -> str:
        return f"ticker:{instrument_id}"
    
    @staticmethod
    def orderbook(instrument_id: str) -> str:
        return f"orderbook:{instrument_id}"
    
    @staticmethod
    def trades(instrument_id: str) -> str:
        return f"trades:{instrument_id}"
    
    # Derivatives Layer
    @staticmethod
    def funding(instrument_id: str) -> str:
        return f"funding:{instrument_id}"
    
    @staticmethod
    def open_interest(instrument_id: str) -> str:
        return f"oi:{instrument_id}"
    
    @staticmethod
    def liquidations() -> str:
        return "liquidations:stream"
    
    # Asset Layer (aggregated data)
    @staticmethod
    def asset_snapshot(asset_id: str) -> str:
        return f"asset:snap:{asset_id}"
    
    @staticmethod
    def asset_markets(asset_id: str) -> str:
        return f"asset:markets:{asset_id}"
    
    # Global Layer
    @staticmethod
    def global_snapshot() -> str:
        return "global:snapshot"
    
    # PubSub channels
    PUBSUB_MARKET_UPDATES = "market_updates"
    PUBSUB_TICKER = "pubsub:ticker"
    PUBSUB_TRADES = "pubsub:trades"
    PUBSUB_FUNDING = "pubsub:funding"
    PUBSUB_LIQUIDATIONS = "pubsub:liquidations"

# ═══════════════════════════════════════════════════════════════
# TTL POLICY
# ═══════════════════════════════════════════════════════════════

class TTL:
    """TTL в секундах для разных типов данных"""
    TICKER = 20  # Increased from 10 to handle slow pipeline fetches
    ORDERBOOK = 10
    TRADES = 30
    FUNDING = 120
    OPEN_INTEREST = 120
    ASSET_SNAPSHOT = 30
    GLOBAL_SNAPSHOT = 60

# ═══════════════════════════════════════════════════════════════
# REDIS STORE
# ═══════════════════════════════════════════════════════════════

class RedisStore:
    """
    Redis Store для market data.
    Реализует snapshot model с TTL и PubSub.
    """
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.environ.get('REDIS_URL', 'redis://localhost:6379')
        self._pool: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._connected = False
    
    async def connect(self):
        """Подключение к Redis"""
        if self._connected:
            return
        
        try:
            self._pool = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50
            )
            await self._pool.ping()
            self._connected = True
            logger.info(f"[Redis] Connected to {self.redis_url}")
        except Exception as e:
            logger.error(f"[Redis] Connection failed: {e}")
            self._connected = False
            raise
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self._pool:
            await self._pool.close()
            self._connected = False
            logger.info("[Redis] Disconnected")
    
    async def ensure_connected(self):
        """Проверяет подключение и переподключается при необходимости"""
        if not self._connected:
            await self.connect()
    
    # ═══════════════════════════════════════════════════════════════
    # INSTRUMENT LAYER - Write
    # ═══════════════════════════════════════════════════════════════
    
    async def set_ticker(self, instrument_id: str, ticker_data: dict):
        """Записывает ticker snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.ticker(instrument_id)
        data = json.dumps(ticker_data)
        
        # Set with TTL
        await self._pool.setex(key, TTL.TICKER, data)
        
        # Publish update
        await self._publish_update("ticker", instrument_id, ticker_data)
    
    async def set_orderbook(self, instrument_id: str, orderbook_data: dict):
        """Записывает orderbook snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.orderbook(instrument_id)
        data = json.dumps(orderbook_data)
        
        await self._pool.setex(key, TTL.ORDERBOOK, data)
        await self._publish_update("orderbook", instrument_id, orderbook_data)
    
    async def add_trade(self, instrument_id: str, trade_data: dict):
        """Добавляет trade в stream"""
        await self.ensure_connected()
        
        key = RedisKeys.trades(instrument_id)
        
        # Add to stream with MAXLEN
        await self._pool.xadd(
            key,
            {"data": json.dumps(trade_data)},
            maxlen=1000
        )
        
        await self._publish_update("trade", instrument_id, trade_data)
    
    async def set_funding(self, instrument_id: str, funding_data: dict):
        """Записывает funding snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.funding(instrument_id)
        data = json.dumps(funding_data)
        
        await self._pool.setex(key, TTL.FUNDING, data)
        await self._publish_update("funding", instrument_id, funding_data)
    
    async def set_open_interest(self, instrument_id: str, oi_data: dict):
        """Записывает OI snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.open_interest(instrument_id)
        data = json.dumps(oi_data)
        
        await self._pool.setex(key, TTL.OPEN_INTEREST, data)
        await self._publish_update("open_interest", instrument_id, oi_data)
    
    async def add_liquidation(self, liquidation_data: dict):
        """Добавляет liquidation в stream"""
        await self.ensure_connected()
        
        key = RedisKeys.liquidations()
        await self._pool.xadd(
            key,
            {"data": json.dumps(liquidation_data)},
            maxlen=10000
        )
        
        await self._publish_update("liquidation", None, liquidation_data)
    
    # ═══════════════════════════════════════════════════════════════
    # INSTRUMENT LAYER - Read
    # ═══════════════════════════════════════════════════════════════
    
    async def get_ticker(self, instrument_id: str) -> Optional[dict]:
        """Читает ticker snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.ticker(instrument_id)
        data = await self._pool.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def get_orderbook(self, instrument_id: str) -> Optional[dict]:
        """Читает orderbook snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.orderbook(instrument_id)
        data = await self._pool.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def get_trades(self, instrument_id: str, limit: int = 100) -> List[dict]:
        """Читает последние trades из stream"""
        await self.ensure_connected()
        
        key = RedisKeys.trades(instrument_id)
        
        # Read last N entries
        entries = await self._pool.xrevrange(key, count=limit)
        
        trades = []
        for entry_id, fields in entries:
            if "data" in fields:
                trades.append(json.loads(fields["data"]))
        
        return trades
    
    async def get_funding(self, instrument_id: str) -> Optional[dict]:
        """Читает funding snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.funding(instrument_id)
        data = await self._pool.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def get_open_interest(self, instrument_id: str) -> Optional[dict]:
        """Читает OI snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.open_interest(instrument_id)
        data = await self._pool.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def get_liquidations(self, limit: int = 100) -> List[dict]:
        """Читает последние liquidations"""
        await self.ensure_connected()
        
        key = RedisKeys.liquidations()
        entries = await self._pool.xrevrange(key, count=limit)
        
        liquidations = []
        for entry_id, fields in entries:
            if "data" in fields:
                liquidations.append(json.loads(fields["data"]))
        
        return liquidations
    
    # ═══════════════════════════════════════════════════════════════
    # ASSET LAYER - Write
    # ═══════════════════════════════════════════════════════════════
    
    async def set_asset_snapshot(self, asset_id: str, snapshot_data: dict):
        """Записывает asset snapshot (aggregated)"""
        await self.ensure_connected()
        
        key = RedisKeys.asset_snapshot(asset_id)
        data = json.dumps(snapshot_data)
        
        await self._pool.setex(key, TTL.ASSET_SNAPSHOT, data)
    
    async def set_asset_markets(self, asset_id: str, markets_data: List[dict]):
        """Записывает market pairs для asset"""
        await self.ensure_connected()
        
        key = RedisKeys.asset_markets(asset_id)
        data = json.dumps(markets_data)
        
        await self._pool.setex(key, TTL.ASSET_SNAPSHOT, data)
    
    # ═══════════════════════════════════════════════════════════════
    # ASSET LAYER - Read
    # ═══════════════════════════════════════════════════════════════
    
    async def get_asset_snapshot(self, asset_id: str) -> Optional[dict]:
        """Читает asset snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.asset_snapshot(asset_id)
        data = await self._pool.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def get_asset_markets(self, asset_id: str) -> Optional[List[dict]]:
        """Читает market pairs для asset"""
        await self.ensure_connected()
        
        key = RedisKeys.asset_markets(asset_id)
        data = await self._pool.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # GLOBAL LAYER
    # ═══════════════════════════════════════════════════════════════
    
    async def set_global_snapshot(self, snapshot_data: dict):
        """Записывает global snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.global_snapshot()
        data = json.dumps(snapshot_data)
        
        await self._pool.setex(key, TTL.GLOBAL_SNAPSHOT, data)
    
    async def get_global_snapshot(self) -> Optional[dict]:
        """Читает global snapshot"""
        await self.ensure_connected()
        
        key = RedisKeys.global_snapshot()
        data = await self._pool.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # PUBSUB
    # ═══════════════════════════════════════════════════════════════
    
    async def _publish_update(self, update_type: str, instrument_id: Optional[str], data: dict):
        """Публикует обновление в PubSub"""
        message = {
            "type": update_type,
            "instrument": instrument_id,
            "data": data,
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000)
        }
        
        await self._pool.publish(
            RedisKeys.PUBSUB_MARKET_UPDATES,
            json.dumps(message)
        )
    
    async def subscribe(self, channel: str = None):
        """Подписка на PubSub канал"""
        await self.ensure_connected()
        
        if not self._pubsub:
            self._pubsub = self._pool.pubsub()
        
        channel = channel or RedisKeys.PUBSUB_MARKET_UPDATES
        await self._pubsub.subscribe(channel)
        logger.info(f"[Redis] Subscribed to {channel}")
    
    async def get_message(self) -> Optional[dict]:
        """Получает сообщение из PubSub"""
        if not self._pubsub:
            return None
        
        message = await self._pubsub.get_message(ignore_subscribe_messages=True)
        
        if message and message["type"] == "message":
            return json.loads(message["data"])
        
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # BATCH OPERATIONS
    # ═══════════════════════════════════════════════════════════════
    
    async def get_all_tickers(self, instrument_ids: List[str]) -> Dict[str, dict]:
        """Batch get tickers"""
        await self.ensure_connected()
        
        if not instrument_ids:
            return {}
        
        keys = [RedisKeys.ticker(iid) for iid in instrument_ids]
        values = await self._pool.mget(keys)
        
        result = {}
        for iid, val in zip(instrument_ids, values):
            if val:
                result[iid] = json.loads(val)
        
        return result
    
    async def set_batch_tickers(self, tickers: Dict[str, dict]):
        """Batch set tickers"""
        await self.ensure_connected()
        
        if not tickers:
            return
        
        pipe = self._pool.pipeline()
        
        for instrument_id, ticker_data in tickers.items():
            key = RedisKeys.ticker(instrument_id)
            pipe.setex(key, TTL.TICKER, json.dumps(ticker_data))
        
        await pipe.execute()
    
    # ═══════════════════════════════════════════════════════════════
    # STATS & HEALTH
    # ═══════════════════════════════════════════════════════════════
    
    async def stats(self) -> dict:
        """Статистика Redis"""
        await self.ensure_connected()
        
        info = await self._pool.info()
        
        # Count keys by pattern
        ticker_count = len(await self._pool.keys("ticker:*"))
        orderbook_count = len(await self._pool.keys("orderbook:*"))
        funding_count = len(await self._pool.keys("funding:*"))
        oi_count = len(await self._pool.keys("oi:*"))
        asset_count = len(await self._pool.keys("asset:snap:*"))
        
        return {
            "connected": self._connected,
            "redis_version": info.get("redis_version"),
            "used_memory_human": info.get("used_memory_human"),
            "connected_clients": info.get("connected_clients"),
            "keys": {
                "tickers": ticker_count,
                "orderbooks": orderbook_count,
                "funding": funding_count,
                "open_interest": oi_count,
                "assets": asset_count
            }
        }
    
    async def health(self) -> dict:
        """Health check"""
        try:
            await self.ensure_connected()
            latency_start = datetime.now(timezone.utc)
            await self._pool.ping()
            latency = (datetime.now(timezone.utc) - latency_start).total_seconds() * 1000
            
            return {
                "healthy": True,
                "latency_ms": round(latency, 2),
                "connected": self._connected
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "connected": False
            }


# Singleton instance
redis_store = RedisStore()
