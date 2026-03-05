"""
Coinbase Exchange Spot Adapter
"""

import httpx
from typing import List, Optional
import time
from datetime import datetime, timezone

from ..base import MarketDataProvider
from ...domain.types import (
    Venue, MarketType, ContractType, ProviderCapabilities,
    Ticker, OrderBook, Trade, Candle, Instrument
)

class CoinbaseAdapter(MarketDataProvider):
    """
    Coinbase Exchange Spot Provider
    Base URL: https://api.exchange.coinbase.com
    """
    
    BASE_URL = "https://api.exchange.coinbase.com"
    TIMEOUT = 10
    
    # Granularity mapping (seconds)
    GRANULARITY_MAP = {
        "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "1d": 86400
    }
    
    def __init__(self):
        self._healthy = True
        self._last_latency: Optional[float] = None
        self._last_error: Optional[str] = None
    
    @property
    def venue(self) -> Venue:
        return Venue.COINBASE
    
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            venue=Venue.COINBASE,
            has_spot=True,
            has_perp=False,
            has_futures=False,
            has_orderbook=True,
            has_trades=True,
            has_candles=True,
            has_funding=False,
            has_funding_history=False,
            has_open_interest=False,
            has_long_short_ratio=False,
            has_liquidations=False,
            has_mark_price=False,
            has_index_price=False,
            has_top_trader_ratio=False,
            has_agg_trades=False,
            has_websocket=True
        )
    
    def _make_instrument_id(self, native_symbol: str) -> str:
        return Instrument.make_id("coinbase", "spot", native_symbol)
    
    def _map_symbol(self, symbol: str) -> str:
        """Конвертирует BTCUSDT -> BTC-USD"""
        if symbol.endswith("USDT"):
            base = symbol.replace("USDT", "")
            return f"{base}-USD"
        if "-" not in symbol:
            return f"{symbol}-USD"
        return symbol
    
    def _unmap_symbol(self, pair: str) -> str:
        """Конвертирует BTC-USD -> BTCUSDT"""
        if "-USD" in pair:
            return pair.replace("-USD", "USDT")
        return pair
    
    def _now_ms(self) -> int:
        return int(time.time() * 1000)
    
    async def _request(self, endpoint: str, params: dict = None) -> dict:
        """Выполняет HTTP запрос к Coinbase API"""
        start = time.time()
        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            try:
                res = await client.get(f"{self.BASE_URL}{endpoint}", params=params)
                res.raise_for_status()
                self._last_latency = (time.time() - start) * 1000
                self._healthy = True
                self._last_error = None
                return res.json()
            except Exception as e:
                self._last_error = str(e)
                self._healthy = False
                raise
    
    # ═══════════════════════════════════════════════════════════════
    # CORE MARKET DATA
    # ═══════════════════════════════════════════════════════════════
    
    async def list_instruments(self, market_type: str = "spot") -> List[Instrument]:
        data = await self._request("/products")
        
        instruments = []
        for p in data:
            # Фильтруем только USD пары и активные
            if p["quote_currency"] != "USD" or p["status"] != "online":
                continue
            
            instruments.append(Instrument(
                instrument_id=self._make_instrument_id(p["id"]),
                venue=Venue.COINBASE,
                market_type=MarketType.SPOT,
                native_symbol=p["id"],  # BTC-USD
                base=p["base_currency"],
                quote=p["quote_currency"],
                status="trading",
                tick_size=float(p.get("quote_increment", 0.01)),
                lot_size=float(p.get("base_increment", 0.00000001)),
                contract_type=ContractType.SPOT,
                settle_asset=None
            ))
        
        return instruments
    
    async def get_ticker(self, native_symbol: str) -> Ticker:
        pair = self._map_symbol(native_symbol)
        data = await self._request(f"/products/{pair}/ticker")
        
        # Получаем 24h stats отдельно
        try:
            stats = await self._request(f"/products/{pair}/stats")
            volume_24h = float(stats.get("volume", 0)) * float(data["price"])
            high_24h = float(stats.get("high", 0))
            low_24h = float(stats.get("low", 0))
            open_24h = float(stats.get("open", data["price"]))
            change_24h = (float(data["price"]) - open_24h) / open_24h if open_24h > 0 else 0
        except:
            volume_24h = float(data.get("volume", 0)) * float(data["price"])
            high_24h = None
            low_24h = None
            change_24h = None
        
        return Ticker(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(pair),
            last=float(data["price"]),
            bid=float(data.get("bid", 0)),
            ask=float(data.get("ask", 0)),
            change_24h=change_24h,
            high_24h=high_24h,
            low_24h=low_24h,
            volume_24h=volume_24h,
            trades_24h=None
        )
    
    async def get_orderbook(self, native_symbol: str, depth: int = 20) -> OrderBook:
        pair = self._map_symbol(native_symbol)
        
        # Coinbase levels: 1 (best), 2 (top 50), 3 (full)
        level = 2 if depth <= 50 else 3
        data = await self._request(f"/products/{pair}/book", {"level": level})
        
        return OrderBook(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(pair),
            depth=depth,
            seq=int(data.get("sequence", 0)),
            bids=[[float(b[0]), float(b[1])] for b in data["bids"][:depth]],
            asks=[[float(a[0]), float(a[1])] for a in data["asks"][:depth]]
        )
    
    async def get_trades(self, native_symbol: str, limit: int = 100) -> List[Trade]:
        pair = self._map_symbol(native_symbol)
        data = await self._request(f"/products/{pair}/trades", {"limit": limit})
        
        return [
            Trade(
                ts=int(datetime.fromisoformat(t["time"].replace("Z", "+00:00")).timestamp() * 1000),
                instrument_id=self._make_instrument_id(pair),
                trade_id=str(t["trade_id"]),
                price=float(t["price"]),
                qty=float(t["size"]),
                side=t["side"]
            )
            for t in data
        ]
    
    async def get_candles(
        self,
        native_symbol: str,
        granularity: str = "1h",
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100
    ) -> List[Candle]:
        pair = self._map_symbol(native_symbol)
        granularity_sec = self.GRANULARITY_MAP.get(granularity, 3600)
        
        params = {"granularity": granularity_sec}
        if start:
            params["start"] = datetime.fromtimestamp(start / 1000, tz=timezone.utc).isoformat()
        if end:
            params["end"] = datetime.fromtimestamp(end / 1000, tz=timezone.utc).isoformat()
        
        data = await self._request(f"/products/{pair}/candles", params)
        
        # Coinbase возвращает [time, low, high, open, close, volume]
        # И в обратном хронологическом порядке
        candles = data[:limit] if len(data) > limit else data
        
        return [
            Candle(
                t=int(c[0]) * 1000,  # convert to ms
                o=float(c[3]),
                h=float(c[2]),
                l=float(c[1]),
                c=float(c[4]),
                v=float(c[5])
            )
            for c in reversed(candles)
        ]
    
    # ═══════════════════════════════════════════════════════════════
    # HEALTH
    # ═══════════════════════════════════════════════════════════════
    
    async def health_check(self) -> dict:
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(f"{self.BASE_URL}/time")
                res.raise_for_status()
            latency = (time.time() - start) * 1000
            
            return {
                "venue": self.venue.value,
                "healthy": True,
                "latency_ms": latency,
                "error": None
            }
        except Exception as e:
            return {
                "venue": self.venue.value,
                "healthy": False,
                "latency_ms": None,
                "error": str(e)
            }


# Singleton instance
coinbase_adapter = CoinbaseAdapter()
