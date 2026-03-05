"""
Hyperliquid Perp DEX Adapter
Полноценный провайдер с market data + whale tracking
"""

import httpx
from typing import List, Optional, Dict, Any
import time

from ..base import MarketDataProvider
from ...domain.types import (
    Venue, MarketType, ContractType, ProviderCapabilities,
    Ticker, OrderBook, Trade, Candle, Instrument,
    FundingRate, FundingHistoryPoint, OpenInterest
)

class HyperliquidAdapter(MarketDataProvider):
    """
    Hyperliquid Perp DEX Provider
    Base URL: https://api.hyperliquid.xyz
    """
    
    BASE_URL = "https://api.hyperliquid.xyz"
    TIMEOUT = 15
    
    # Известные whale адреса (можно расширять)
    WHALE_ADDRESSES = [
        "0x1234567890abcdef1234567890abcdef12345678",  # Placeholder - заменить реальными
    ]
    
    def __init__(self):
        self._healthy = True
        self._last_latency: Optional[float] = None
        self._last_error: Optional[str] = None
        self._meta_cache: Optional[Dict] = None
        self._meta_cache_ts: int = 0
    
    @property
    def venue(self) -> Venue:
        return Venue.HYPERLIQUID
    
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            venue=Venue.HYPERLIQUID,
            has_spot=False,
            has_perp=True,
            has_futures=False,
            has_orderbook=True,
            has_trades=True,
            has_candles=True,
            has_funding=True,
            has_funding_history=True,
            has_open_interest=True,
            has_long_short_ratio=False,
            has_liquidations=False,
            has_mark_price=True,
            has_index_price=False,
            has_top_trader_ratio=False,
            has_agg_trades=False,
            has_websocket=True
        )
    
    def _make_instrument_id(self, coin: str) -> str:
        return Instrument.make_id("hyperliquid", "perp", f"{coin}-PERP")
    
    def _now_ms(self) -> int:
        return int(time.time() * 1000)
    
    async def _post_info(self, request_type: str, **kwargs) -> Any:
        """POST запрос к /info endpoint"""
        start = time.time()
        payload = {"type": request_type, **kwargs}
        
        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            try:
                res = await client.post(f"{self.BASE_URL}/info", json=payload)
                res.raise_for_status()
                self._last_latency = (time.time() - start) * 1000
                self._healthy = True
                self._last_error = None
                return res.json()
            except Exception as e:
                self._last_error = str(e)
                self._healthy = False
                raise
    
    async def _get_meta(self) -> Dict:
        """Получает и кеширует мета-данные рынков"""
        now = self._now_ms()
        # Кеш на 5 минут
        if self._meta_cache and now - self._meta_cache_ts < 300000:
            return self._meta_cache
        
        self._meta_cache = await self._post_info("meta")
        self._meta_cache_ts = now
        return self._meta_cache
    
    async def _get_all_mids(self) -> Dict[str, float]:
        """Получает все mid prices"""
        data = await self._post_info("allMids")
        return {k: float(v) for k, v in data.items()}
    
    async def _get_meta_and_asset_ctxs(self) -> Dict:
        """Мета + контексты активов (OI, funding, volume)"""
        return await self._post_info("metaAndAssetCtxs")
    
    # ═══════════════════════════════════════════════════════════════
    # CORE MARKET DATA
    # ═══════════════════════════════════════════════════════════════
    
    async def list_instruments(self, market_type: str = "perp") -> List[Instrument]:
        meta = await self._get_meta()
        
        instruments = []
        for asset_info in meta.get("universe", []):
            coin = asset_info["name"]
            
            instruments.append(Instrument(
                instrument_id=self._make_instrument_id(coin),
                venue=Venue.HYPERLIQUID,
                market_type=MarketType.PERP,
                native_symbol=f"{coin}-PERP",
                base=coin,
                quote="USD",
                status="trading",
                tick_size=float(asset_info.get("szDecimals", 0)),
                lot_size=None,
                contract_type=ContractType.LINEAR_PERP,
                settle_asset="USD"
            ))
        
        return instruments
    
    async def get_ticker(self, native_symbol: str) -> Ticker:
        # native_symbol: "BTC-PERP" или "BTC"
        coin = native_symbol.replace("-PERP", "")
        
        # Получаем meta + asset contexts
        data = await self._get_meta_and_asset_ctxs()
        meta = data[0]  # meta
        asset_ctxs = data[1]  # asset contexts
        
        # Находим индекс актива
        universe = meta.get("universe", [])
        asset_idx = next((i for i, a in enumerate(universe) if a["name"] == coin), None)
        
        if asset_idx is None:
            raise Exception(f"Asset {coin} not found")
        
        ctx = asset_ctxs[asset_idx]
        
        # Получаем bid/ask из orderbook (первые уровни)
        bid = None
        ask = None
        try:
            ob_data = await self._post_info("l2Book", coin=coin)
            levels = ob_data.get("levels", [[], []])
            bids = levels[0] if len(levels) > 0 else []
            asks = levels[1] if len(levels) > 1 else []
            if bids:
                bid = float(bids[0]["px"])
            if asks:
                ask = float(asks[0]["px"])
        except:
            pass
        
        return Ticker(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(coin),
            last=float(ctx["markPx"]),
            bid=bid,
            ask=ask,
            change_24h=float(ctx.get("dayNtlVlm", 0)) / 100 if ctx.get("dayNtlVlm") else None,
            high_24h=None,
            low_24h=None,
            volume_24h=float(ctx.get("dayNtlVlm", 0)),
            trades_24h=None
        )
    
    async def get_orderbook(self, native_symbol: str, depth: int = 20) -> OrderBook:
        coin = native_symbol.replace("-PERP", "")
        
        data = await self._post_info("l2Book", coin=coin)
        
        levels = data.get("levels", [[], []])
        bids = levels[0] if len(levels) > 0 else []
        asks = levels[1] if len(levels) > 1 else []
        
        return OrderBook(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(coin),
            depth=depth,
            seq=None,
            bids=[[float(b["px"]), float(b["sz"])] for b in bids[:depth]],
            asks=[[float(a["px"]), float(a["sz"])] for a in asks[:depth]]
        )
    
    async def get_trades(self, native_symbol: str, limit: int = 100) -> List[Trade]:
        """
        Get recent trades for a coin.
        Note: Hyperliquid doesn't have a direct public trades endpoint,
        we use a workaround via userFills or return empty list.
        """
        coin = native_symbol.replace("-PERP", "")
        
        # Hyperliquid doesn't have public trades API
        # Return empty list - trades can be obtained via WebSocket
        return []
    
    async def get_candles(
        self,
        native_symbol: str,
        granularity: str = "1h",
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100
    ) -> List[Candle]:
        coin = native_symbol.replace("-PERP", "")
        
        # Конвертируем интервал
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
        interval = interval_map.get(granularity, "1h")
        
        params = {
            "coin": coin,
            "interval": interval,
            "startTime": start or (self._now_ms() - 86400000 * 7),  # Default 7 days
            "endTime": end or self._now_ms()
        }
        
        try:
            data = await self._post_info("candleSnapshot", **params)
        except:
            return []
        
        return [
            Candle(
                t=int(c["t"]),
                o=float(c["o"]),
                h=float(c["h"]),
                l=float(c["l"]),
                c=float(c["c"]),
                v=float(c["v"])
            )
            for c in data[:limit]
        ]
    
    # ═══════════════════════════════════════════════════════════════
    # DERIVATIVES
    # ═══════════════════════════════════════════════════════════════
    
    async def get_funding(self, native_symbol: str) -> FundingRate:
        coin = native_symbol.replace("-PERP", "")
        
        data = await self._get_meta_and_asset_ctxs()
        meta = data[0]
        asset_ctxs = data[1]
        
        universe = meta.get("universe", [])
        asset_idx = next((i for i, a in enumerate(universe) if a["name"] == coin), None)
        
        if asset_idx is None:
            raise Exception(f"Asset {coin} not found")
        
        ctx = asset_ctxs[asset_idx]
        
        return FundingRate(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(coin),
            funding_rate=float(ctx.get("funding", 0)),
            funding_time=self._now_ms() + 3600000  # +1h (funding каждый час)
        )
    
    async def get_funding_history(
        self,
        native_symbol: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 100
    ) -> List[FundingHistoryPoint]:
        coin = native_symbol.replace("-PERP", "")
        
        try:
            data = await self._post_info("fundingHistory", coin=coin, startTime=start or 0)
        except:
            return []
        
        return [
            FundingHistoryPoint(
                funding_time=int(f.get("time", 0)),
                funding_rate=float(f.get("fundingRate", 0))
            )
            for f in data[:limit]
        ]
    
    async def get_open_interest(self, native_symbol: str) -> OpenInterest:
        coin = native_symbol.replace("-PERP", "")
        
        data = await self._get_meta_and_asset_ctxs()
        meta = data[0]
        asset_ctxs = data[1]
        
        universe = meta.get("universe", [])
        asset_idx = next((i for i, a in enumerate(universe) if a["name"] == coin), None)
        
        if asset_idx is None:
            raise Exception(f"Asset {coin} not found")
        
        ctx = asset_ctxs[asset_idx]
        oi = float(ctx.get("openInterest", 0))
        mark_px = float(ctx.get("markPx", 0))
        
        return OpenInterest(
            ts=self._now_ms(),
            instrument_id=self._make_instrument_id(coin),
            open_interest=oi,
            open_interest_usd=oi * mark_px
        )
    
    async def get_mark_price(self, native_symbol: str) -> Optional[Dict]:
        coin = native_symbol.replace("-PERP", "")
        
        data = await self._get_meta_and_asset_ctxs()
        meta = data[0]
        asset_ctxs = data[1]
        
        universe = meta.get("universe", [])
        asset_idx = next((i for i, a in enumerate(universe) if a["name"] == coin), None)
        
        if asset_idx is None:
            return None
        
        ctx = asset_ctxs[asset_idx]
        
        return {
            "ts": self._now_ms(),
            "instrument_id": self._make_instrument_id(coin),
            "mark_price": float(ctx.get("markPx", 0)),
            "index_price": None  # Hyperliquid не предоставляет отдельно
        }
    
    # ═══════════════════════════════════════════════════════════════
    # WHALE TRACKING (уникальная фича Hyperliquid)
    # ═══════════════════════════════════════════════════════════════
    
    async def get_user_state(self, address: str) -> Dict:
        """Получает состояние аккаунта пользователя"""
        return await self._post_info("clearinghouseState", user=address)
    
    async def get_user_positions(self, address: str) -> List[Dict]:
        """Получает открытые позиции пользователя"""
        state = await self.get_user_state(address)
        positions = []
        
        for pos in state.get("assetPositions", []):
            position = pos.get("position", {})
            if position.get("szi") == 0:
                continue
            
            size = float(position["szi"])
            entry_px = float(position.get("entryPx", 0))
            
            positions.append({
                "coin": position["coin"],
                "side": "LONG" if size > 0 else "SHORT",
                "size": abs(size),
                "entry_price": entry_px,
                "value_usd": abs(size) * entry_px,
                "unrealized_pnl": float(position.get("unrealizedPnl", 0)),
                "leverage": float(position.get("leverage", {}).get("value", 1))
            })
        
        return positions
    
    async def get_whale_snapshots(self, addresses: List[str] = None) -> List[Dict]:
        """Получает позиции всех whale адресов"""
        if addresses is None:
            addresses = self.WHALE_ADDRESSES
        
        all_positions = []
        for addr in addresses:
            try:
                positions = await self.get_user_positions(addr)
                for pos in positions:
                    pos["address"] = addr
                    all_positions.append(pos)
            except:
                continue
        
        return all_positions
    
    async def get_leaderboard(self, window: str = "day") -> List[Dict]:
        """Топ трейдеры по PnL"""
        try:
            data = await self._post_info("leaderboard", window=window)
            return data.get("leaderboardRows", [])
        except:
            return []
    
    # ═══════════════════════════════════════════════════════════════
    # HEALTH
    # ═══════════════════════════════════════════════════════════════
    
    async def health_check(self) -> dict:
        try:
            start = time.time()
            await self._get_meta()
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
hyperliquid_adapter = HyperliquidAdapter()
