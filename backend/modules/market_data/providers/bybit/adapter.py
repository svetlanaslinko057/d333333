"""
Bybit V5 USDT Perpetual Adapter
"""

import httpx
from typing import List, Optional
import time

from ..base import MarketDataProvider
from ...domain.types import (
    Venue, MarketType, ContractType, ProviderCapabilities,
    Ticker, OrderBook, Trade, Candle, Instrument,
    FundingRate, FundingHistoryPoint, OpenInterest,
    LongShortRatio, MarkPrice
)

class BybitAdapter(MarketDataProvider):
    """
    Bybit V5 USDT Perpetual Provider
    Base URL: https://api.bybit.com
    """
    
    BASE_URL = "https://api.bybit.com"
    TIMEOUT = 10
    
    # Interval mapping
    INTERVAL_MAP = {
        "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
        "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
        "1d": "D", "1w": "W", "1M": "M"
    }
    
    def __init__(self):
        self._healthy = True
        self._last_latency: Optional[float] = None
        self._last_error: Optional[str] = None
    
    @property
    def venue(self) -> Venue:
        return Venue.BYBIT
    
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            venue=Venue.BYBIT,
            has_spot=True,
            has_perp=True,
            has_futures=False,
            has_orderbook=True,
            has_trades=True,
            has_candles=True,
            has_funding=True,
            has_funding_history=True,
            has_open_interest=True,
            has_long_short_ratio=True,
            has_liquidations=False,  # Требует WS
            has_mark_price=True,
            has_index_price=True,
            has_top_trader_ratio=False,
            has_agg_trades=False,
            has_websocket=True
        )
    
    def _make_instrument_id(self, native_symbol: str, market_type: str = "perp") -> str:
        return Instrument.make_id("bybit", market_type, native_symbol)
    
    def _now_ms(self) -> int:
        return int(time.time() * 1000)
    
    async def _request(self, endpoint: str, params: dict = None) -> dict:
        """Выполняет HTTP запрос к Bybit API"""
        start = time.time()
        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            try:
                res = await client.get(f"{self.BASE_URL}{endpoint}", params=params)
                res.raise_for_status()
                data = res.json()
                
                if data.get("retCode") != 0:
                    raise Exception(data.get("retMsg", "Unknown Bybit error"))
                
                self._last_latency = (time.time() - start) * 1000
                self._healthy = True
                self._last_error = None
                return data["result"]
            except Exception as e:
                self._last_error = str(e)
                self._healthy = False
                raise
    
    # ═══════════════════════════════════════════════════════════════
    # CORE MARKET DATA
    # ═══════════════════════════════════════════════════════════════
    
    async def list_instruments(self, market_type: str = "perp") -> List[Instrument]:
        category = "linear" if market_type == "perp" else "spot"
        data = await self._request("/v5/market/instruments-info", {"category": category})
        
        instruments = []
        for s in data["list"]:
            if s["status"] != "Trading":
                continue
            
            # Для perp фильтруем только USDT
            if market_type == "perp" and s.get("quoteCoin") != "USDT":
                continue
            
            instruments.append(Instrument(
                instrument_id=self._make_instrument_id(s["symbol"], market_type),
                venue=Venue.BYBIT,
                market_type=MarketType.PERP if market_type == "perp" else MarketType.SPOT,
                native_symbol=s["symbol"],
                base=s["baseCoin"],
                quote=s["quoteCoin"],
                status="trading",
                tick_size=float(s.get("priceFilter", {}).get("tickSize", 0.01)),
                lot_size=float(s.get("lotSizeFilter", {}).get("qtyStep", 0.001)),
                contract_type=ContractType.LINEAR_PERP if market_type == "perp" else ContractType.SPOT,
                settle_asset=s.get("settleCoin")
            ))
        
        return instruments
    
    async def get_ticker(self, native_symbol: str) -> Ticker:
        data = await self._request("/v5/market/tickers", {"category": "linear", "symbol": native_symbol})
        
        if not data["list"]:
            raise Exception(f"Ticker not found for {native_symbol}")
        
        t = data["list"][0]
        return Ticker(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(native_symbol),
            last=float(t["lastPrice"]),
            bid=float(t.get("bid1Price", 0)),
            ask=float(t.get("ask1Price", 0)),
            change_24h=float(t["price24hPcnt"]),
            high_24h=float(t["highPrice24h"]),
            low_24h=float(t["lowPrice24h"]),
            volume_24h=float(t["turnover24h"]),
            trades_24h=None
        )
    
    async def get_orderbook(self, native_symbol: str, depth: int = 20) -> OrderBook:
        # Bybit поддерживает depth до 1000!
        data = await self._request("/v5/market/orderbook", {
            "category": "linear",
            "symbol": native_symbol,
            "limit": min(depth, 1000)
        })
        
        return OrderBook(
            ts=int(data["ts"]),
            instrument_id=self._make_instrument_id(native_symbol),
            depth=depth,
            seq=int(data.get("u", 0)),
            bids=[[float(b[0]), float(b[1])] for b in data["b"]],
            asks=[[float(a[0]), float(a[1])] for a in data["a"]]
        )
    
    async def get_trades(self, native_symbol: str, limit: int = 100) -> List[Trade]:
        data = await self._request("/v5/market/recent-trade", {
            "category": "linear",
            "symbol": native_symbol,
            "limit": limit
        })
        
        return [
            Trade(
                ts=int(t["time"]),
                instrument_id=self._make_instrument_id(native_symbol),
                trade_id=t["execId"],
                price=float(t["price"]),
                qty=float(t["size"]),
                side=t["side"].lower()
            )
            for t in data["list"]
        ]
    
    async def get_candles(
        self,
        native_symbol: str,
        granularity: str = "1h",
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100
    ) -> List[Candle]:
        # Конвертируем интервал
        bybit_interval = self.INTERVAL_MAP.get(granularity, granularity)
        
        params = {
            "category": "linear",
            "symbol": native_symbol,
            "interval": bybit_interval,
            "limit": limit
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        
        data = await self._request("/v5/market/kline", params)
        
        # Bybit возвращает в обратном порядке
        return [
            Candle(
                t=int(c[0]),
                o=float(c[1]),
                h=float(c[2]),
                l=float(c[3]),
                c=float(c[4]),
                v=float(c[5])
            )
            for c in reversed(data["list"])
        ]
    
    # ═══════════════════════════════════════════════════════════════
    # DERIVATIVES
    # ═══════════════════════════════════════════════════════════════
    
    async def get_funding(self, native_symbol: str) -> FundingRate:
        data = await self._request("/v5/market/tickers", {"category": "linear", "symbol": native_symbol})
        
        if not data["list"]:
            raise Exception(f"Ticker not found for {native_symbol}")
        
        t = data["list"][0]
        return FundingRate(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(native_symbol),
            funding_rate=float(t.get("fundingRate", 0)),
            funding_time=int(t.get("nextFundingTime", 0))
        )
    
    async def get_funding_history(
        self,
        native_symbol: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100
    ) -> List[FundingHistoryPoint]:
        params = {
            "category": "linear",
            "symbol": native_symbol,
            "limit": limit
        }
        if start:
            params["startTime"] = start
        if end:
            params["endTime"] = end
        
        data = await self._request("/v5/market/funding/history", params)
        
        return [
            FundingHistoryPoint(
                funding_time=int(f["fundingRateTimestamp"]),
                funding_rate=float(f["fundingRate"])
            )
            for f in data["list"]
        ]
    
    async def get_open_interest(self, native_symbol: str) -> OpenInterest:
        data = await self._request("/v5/market/open-interest", {
            "category": "linear",
            "symbol": native_symbol,
            "intervalTime": "5min",
            "limit": 1
        })
        
        if not data["list"]:
            raise Exception(f"OI not found for {native_symbol}")
        
        oi_data = data["list"][0]
        oi = float(oi_data["openInterest"])
        
        # Получаем цену для USD value
        ticker = await self.get_ticker(native_symbol)
        
        return OpenInterest(
            ts=int(oi_data["timestamp"]),
            instrument_id=self._make_instrument_id(native_symbol),
            open_interest=oi,
            open_interest_usd=oi * ticker.last
        )
    
    async def get_long_short_ratio(self, native_symbol: str) -> LongShortRatio:
        """Long/Short ratio (требует /v5/market/account-ratio)"""
        # Bybit имеет это через другой endpoint
        try:
            data = await self._request("/v5/market/account-ratio", {
                "category": "linear",
                "symbol": native_symbol,
                "period": "5min",
                "limit": 1
            })
            
            if not data["list"]:
                return None
            
            item = data["list"][0]
            buy_ratio = float(item["buyRatio"])
            sell_ratio = float(item["sellRatio"])
            
            return LongShortRatio(
                ts=int(item["timestamp"]),
                instrument_id=self._make_instrument_id(native_symbol),
                long_ratio=buy_ratio,
                short_ratio=sell_ratio,
                long_short_ratio=buy_ratio / sell_ratio if sell_ratio > 0 else 0
            )
        except:
            return None
    
    async def get_mark_price(self, native_symbol: str) -> MarkPrice:
        data = await self._request("/v5/market/tickers", {"category": "linear", "symbol": native_symbol})
        
        if not data["list"]:
            raise Exception(f"Ticker not found for {native_symbol}")
        
        t = data["list"][0]
        return MarkPrice(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(native_symbol),
            mark_price=float(t.get("markPrice", t["lastPrice"])),
            index_price=float(t.get("indexPrice", t["lastPrice"]))
        )
    
    # ═══════════════════════════════════════════════════════════════
    # HEALTH
    # ═══════════════════════════════════════════════════════════════
    
    async def health_check(self) -> dict:
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(f"{self.BASE_URL}/v5/market/time")
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
bybit_adapter = BybitAdapter()
