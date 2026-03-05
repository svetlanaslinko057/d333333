"""
Binance Futures USDT-M Adapter
Полная реализация с derivatives endpoints
"""

import httpx
from typing import List, Optional
from datetime import datetime, timezone
import time

from ..base import MarketDataProvider
from ...domain.types import (
    Venue, MarketType, ContractType, ProviderCapabilities,
    Ticker, OrderBook, Trade, Candle, Instrument,
    FundingRate, FundingHistoryPoint, OpenInterest,
    LongShortRatio, Liquidation, MarkPrice
)

class BinanceAdapter(MarketDataProvider):
    """
    Binance Futures USDT-M Provider
    Base URL: https://fapi.binance.com
    """
    
    BASE_URL = "https://fapi.binance.com"
    TIMEOUT = 10
    
    def __init__(self):
        self._healthy = True
        self._last_latency: Optional[float] = None
        self._last_error: Optional[str] = None
    
    @property
    def venue(self) -> Venue:
        return Venue.BINANCE
    
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            venue=Venue.BINANCE,
            has_spot=False,  # Этот адаптер для futures
            has_perp=True,
            has_futures=True,
            has_orderbook=True,
            has_trades=True,
            has_candles=True,
            has_funding=True,
            has_funding_history=True,
            has_open_interest=True,
            has_long_short_ratio=True,
            has_liquidations=True,
            has_mark_price=True,
            has_index_price=True,
            has_top_trader_ratio=True,
            has_agg_trades=True,
            has_websocket=True
        )
    
    def _make_instrument_id(self, native_symbol: str, market_type: str = "perp") -> str:
        return Instrument.make_id("binance", market_type, native_symbol)
    
    def _now_ms(self) -> int:
        return int(time.time() * 1000)
    
    async def _request(self, endpoint: str, params: dict = None) -> dict:
        """Выполняет HTTP запрос к Binance API"""
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
    
    async def list_instruments(self, market_type: str = "perp") -> List[Instrument]:
        data = await self._request("/fapi/v1/exchangeInfo")
        instruments = []
        
        for s in data["symbols"]:
            if s["status"] != "TRADING":
                continue
            
            # Фильтр по типу
            if market_type == "perp" and s["contractType"] != "PERPETUAL":
                continue
            
            instruments.append(Instrument(
                instrument_id=self._make_instrument_id(s["symbol"], market_type),
                venue=Venue.BINANCE,
                market_type=MarketType.PERP if s["contractType"] == "PERPETUAL" else MarketType.FUTURES,
                native_symbol=s["symbol"],
                base=s["baseAsset"],
                quote=s["quoteAsset"],
                status="trading",
                tick_size=float(next((f["tickSize"] for f in s["filters"] if f["filterType"] == "PRICE_FILTER"), 0.01)),
                lot_size=float(next((f["stepSize"] for f in s["filters"] if f["filterType"] == "LOT_SIZE"), 0.001)),
                contract_type=ContractType.LINEAR_PERP if s["contractType"] == "PERPETUAL" else ContractType.LINEAR_FUTURES,
                settle_asset=s["marginAsset"]
            ))
        
        return instruments
    
    async def get_ticker(self, native_symbol: str) -> Ticker:
        data = await self._request("/fapi/v1/ticker/24hr", {"symbol": native_symbol})
        
        return Ticker(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(native_symbol),
            last=float(data["lastPrice"]),
            bid=float(data.get("bidPrice", 0)),
            ask=float(data.get("askPrice", 0)),
            change_24h=float(data["priceChangePercent"]) / 100,
            high_24h=float(data["highPrice"]),
            low_24h=float(data["lowPrice"]),
            volume_24h=float(data["quoteVolume"]),
            trades_24h=int(data.get("count", 0))
        )
    
    async def get_orderbook(self, native_symbol: str, depth: int = 20) -> OrderBook:
        data = await self._request("/fapi/v1/depth", {"symbol": native_symbol, "limit": depth})
        
        return OrderBook(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(native_symbol),
            depth=depth,
            seq=data.get("lastUpdateId"),
            bids=[[float(b[0]), float(b[1])] for b in data["bids"]],
            asks=[[float(a[0]), float(a[1])] for a in data["asks"]]
        )
    
    async def get_trades(self, native_symbol: str, limit: int = 100) -> List[Trade]:
        data = await self._request("/fapi/v1/trades", {"symbol": native_symbol, "limit": limit})
        
        return [
            Trade(
                ts=int(t["time"]),
                instrument_id=self._make_instrument_id(native_symbol),
                trade_id=str(t["id"]),
                price=float(t["price"]),
                qty=float(t["qty"]),
                side="sell" if t["isBuyerMaker"] else "buy"
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
        params = {"symbol": native_symbol, "interval": granularity, "limit": limit}
        if start:
            params["startTime"] = start
        if end:
            params["endTime"] = end
        
        data = await self._request("/fapi/v1/klines", params)
        
        return [
            Candle(
                t=int(c[0]),
                o=float(c[1]),
                h=float(c[2]),
                l=float(c[3]),
                c=float(c[4]),
                v=float(c[5])
            )
            for c in data
        ]
    
    # ═══════════════════════════════════════════════════════════════
    # DERIVATIVES
    # ═══════════════════════════════════════════════════════════════
    
    async def get_funding(self, native_symbol: str) -> FundingRate:
        data = await self._request("/fapi/v1/premiumIndex", {"symbol": native_symbol})
        
        return FundingRate(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(native_symbol),
            funding_rate=float(data["lastFundingRate"]),
            funding_time=int(data["nextFundingTime"])
        )
    
    async def get_funding_history(
        self,
        native_symbol: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100
    ) -> List[FundingHistoryPoint]:
        params = {"symbol": native_symbol, "limit": limit}
        if start:
            params["startTime"] = start
        if end:
            params["endTime"] = end
        
        data = await self._request("/fapi/v1/fundingRate", params)
        
        return [
            FundingHistoryPoint(
                funding_time=int(f["fundingTime"]),
                funding_rate=float(f["fundingRate"])
            )
            for f in data
        ]
    
    async def get_open_interest(self, native_symbol: str) -> OpenInterest:
        data = await self._request("/fapi/v1/openInterest", {"symbol": native_symbol})
        
        # Получаем цену для расчета USD value
        ticker = await self.get_ticker(native_symbol)
        oi = float(data["openInterest"])
        
        return OpenInterest(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(native_symbol),
            open_interest=oi,
            open_interest_usd=oi * ticker.last
        )
    
    async def get_long_short_ratio(self, native_symbol: str) -> LongShortRatio:
        """Global Long/Short Account Ratio"""
        data = await self._request("/futures/data/globalLongShortAccountRatio", {
            "symbol": native_symbol,
            "period": "5m",
            "limit": 1
        })
        
        if not data:
            return None
        
        item = data[0]
        long_ratio = float(item["longAccount"])
        short_ratio = float(item["shortAccount"])
        
        return LongShortRatio(
            ts=int(item["timestamp"]),
            instrument_id=self._make_instrument_id(native_symbol),
            long_ratio=long_ratio,
            short_ratio=short_ratio,
            long_short_ratio=float(item["longShortRatio"])
        )
    
    async def get_mark_price(self, native_symbol: str) -> MarkPrice:
        data = await self._request("/fapi/v1/premiumIndex", {"symbol": native_symbol})
        
        return MarkPrice(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(native_symbol),
            mark_price=float(data["markPrice"]),
            index_price=float(data["indexPrice"])
        )
    
    async def get_agg_trades(self, native_symbol: str, limit: int = 100) -> List[Trade]:
        """Aggregated trades для CVD анализа"""
        data = await self._request("/fapi/v1/aggTrades", {"symbol": native_symbol, "limit": limit})
        
        return [
            Trade(
                ts=int(t["T"]),
                instrument_id=self._make_instrument_id(native_symbol),
                trade_id=str(t["a"]),
                price=float(t["p"]),
                qty=float(t["q"]),
                side="sell" if t["m"] else "buy"
            )
            for t in data
        ]
    
    async def get_top_trader_long_short_ratio(self, native_symbol: str, account_or_position: str = "position") -> LongShortRatio:
        """Top Trader Long/Short Ratio (accounts or positions)"""
        endpoint = f"/futures/data/topLongShortPositionRatio" if account_or_position == "position" else "/futures/data/topLongShortAccountRatio"
        
        data = await self._request(endpoint, {
            "symbol": native_symbol,
            "period": "5m",
            "limit": 1
        })
        
        if not data:
            return None
        
        item = data[0]
        return LongShortRatio(
            ts=int(item["timestamp"]),
            instrument_id=self._make_instrument_id(native_symbol),
            long_ratio=float(item["longAccount"]) if "longAccount" in item else float(item["longPosition"]),
            short_ratio=float(item["shortAccount"]) if "shortAccount" in item else float(item["shortPosition"]),
            long_short_ratio=float(item["longShortRatio"])
        )
    
    async def get_taker_buy_sell_ratio(self, native_symbol: str) -> dict:
        """Taker Buy/Sell Volume ratio"""
        data = await self._request("/futures/data/takerlongshortRatio", {
            "symbol": native_symbol,
            "period": "5m",
            "limit": 1
        })
        
        if not data:
            return None
        
        item = data[0]
        return {
            "ts": int(item["timestamp"]),
            "instrument_id": self._make_instrument_id(native_symbol),
            "buy_sell_ratio": float(item["buySellRatio"]),
            "buy_vol": float(item["buyVol"]),
            "sell_vol": float(item["sellVol"])
        }
    
    # ═══════════════════════════════════════════════════════════════
    # ADDITIONAL ENDPOINTS (P1)
    # ═══════════════════════════════════════════════════════════════
    
    async def get_book_ticker(self, native_symbol: str) -> dict:
        """Best bid/ask (fastest spread data)"""
        data = await self._request("/fapi/v1/ticker/bookTicker", {"symbol": native_symbol})
        
        return {
            "ts": self._now_ms(),
            "instrument_id": self._make_instrument_id(native_symbol),
            "bid": float(data["bidPrice"]),
            "bid_qty": float(data["bidQty"]),
            "ask": float(data["askPrice"]),
            "ask_qty": float(data["askQty"]),
            "spread_bps": (float(data["askPrice"]) - float(data["bidPrice"])) / float(data["bidPrice"]) * 10000
        }
    
    async def get_liquidations(self, native_symbol: str, limit: int = 100) -> List[Liquidation]:
        """Force liquidation orders"""
        try:
            data = await self._request("/fapi/v1/allForceOrders", {
                "symbol": native_symbol,
                "limit": limit
            })
            
            return [
                Liquidation(
                    t=int(liq["time"]),
                    side=liq["side"].lower(),
                    price=float(liq["price"]),
                    qty=float(liq["origQty"]),
                    value_usd=float(liq["price"]) * float(liq["origQty"])
                )
                for liq in data
            ]
        except:
            return []
    
    async def get_open_interest_history(
        self, 
        native_symbol: str,
        period: str = "5m",
        limit: int = 100
    ) -> List[dict]:
        """Open Interest historical data"""
        try:
            data = await self._request("/futures/data/openInterestHist", {
                "symbol": native_symbol,
                "period": period,
                "limit": limit
            })
            
            return [
                {
                    "ts": int(item["timestamp"]),
                    "sum_open_interest": float(item["sumOpenInterest"]),
                    "sum_open_interest_value": float(item["sumOpenInterestValue"])
                }
                for item in data
            ]
        except:
            return []
    
    async def get_continuous_klines(
        self,
        pair: str,
        contract_type: str = "PERPETUAL",
        interval: str = "1h",
        limit: int = 100
    ) -> List[Candle]:
        """Continuous contract klines (no gaps)"""
        try:
            data = await self._request("/fapi/v1/continuousKlines", {
                "pair": pair,
                "contractType": contract_type,
                "interval": interval,
                "limit": limit
            })
            
            return [
                Candle(
                    t=int(c[0]),
                    o=float(c[1]),
                    h=float(c[2]),
                    l=float(c[3]),
                    c=float(c[4]),
                    v=float(c[5])
                )
                for c in data
            ]
        except:
            return []
    
    async def get_index_price_klines(
        self,
        pair: str,
        interval: str = "1h",
        limit: int = 100
    ) -> List[Candle]:
        """Index price klines"""
        try:
            data = await self._request("/fapi/v1/indexPriceKlines", {
                "pair": pair,
                "interval": interval,
                "limit": limit
            })
            
            return [
                Candle(
                    t=int(c[0]),
                    o=float(c[1]),
                    h=float(c[2]),
                    l=float(c[3]),
                    c=float(c[4]),
                    v=0  # Index klines don't have volume
                )
                for c in data
            ]
        except:
            return []
    
    async def get_mark_price_klines(
        self,
        native_symbol: str,
        interval: str = "1h",
        limit: int = 100
    ) -> List[Candle]:
        """Mark price klines"""
        try:
            data = await self._request("/fapi/v1/markPriceKlines", {
                "symbol": native_symbol,
                "interval": interval,
                "limit": limit
            })
            
            return [
                Candle(
                    t=int(c[0]),
                    o=float(c[1]),
                    h=float(c[2]),
                    l=float(c[3]),
                    c=float(c[4]),
                    v=0  # Mark klines don't have volume
                )
                for c in data
            ]
        except:
            return []
    
    # ═══════════════════════════════════════════════════════════════
    # HEALTH
    # ═══════════════════════════════════════════════════════════════
    
    async def health_check(self) -> dict:
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=5) as client:
                await client.get(f"{self.BASE_URL}/fapi/v1/ping")
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
binance_adapter = BinanceAdapter()
