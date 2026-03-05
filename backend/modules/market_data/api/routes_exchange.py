"""
Exchange API Routes
Сырые биржевые данные
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import time

from ..domain.types import Venue, MarketType
from ..providers.registry import provider_registry
from ..services.instrument_registry import instrument_registry

router = APIRouter(prefix="/api/exchange", tags=["Exchange"])

def _now_ms() -> int:
    return int(time.time() * 1000)

# ═══════════════════════════════════════════════════════════════
# INSTRUMENTS
# ═══════════════════════════════════════════════════════════════

@router.get("/instruments")
async def get_instruments(
    venue: Optional[str] = Query(None, description="Filter by venue"),
    market_type: Optional[str] = Query("perp", description="Filter by market type")
):
    """Список торговых инструментов"""
    await instrument_registry.sync_all()
    
    venue_filter = Venue(venue) if venue else None
    mt_filter = MarketType(market_type) if market_type else None
    
    instruments = instrument_registry.list_instruments(venue_filter, mt_filter)
    
    return {
        "ts": _now_ms(),
        "venue": venue,
        "market_type": market_type,
        "items": [
            {
                "instrument_id": i.instrument_id,
                "native_symbol": i.native_symbol,
                "base": i.base,
                "quote": i.quote,
                "status": i.status,
                "tick_size": i.tick_size,
                "lot_size": i.lot_size,
                "contract_type": i.contract_type.value if i.contract_type else None,
                "settle_asset": i.settle_asset
            }
            for i in instruments
        ]
    }

# ═══════════════════════════════════════════════════════════════
# TICKER
# ═══════════════════════════════════════════════════════════════

@router.get("/ticker")
async def get_ticker(
    instrument_id: Optional[str] = Query(None, description="Instrument ID (e.g., binance:perp:BTCUSDT)"),
    venue: Optional[str] = Query(None, description="Venue (e.g., binance)"),
    symbol: Optional[str] = Query(None, description="Native symbol (e.g., BTCUSDT)")
):
    """Текущий тикер инструмента"""
    if not instrument_id and not (venue and symbol):
        raise HTTPException(status_code=400, detail="Provide instrument_id OR venue+symbol")
    
    if instrument_id:
        # Parse instrument_id
        parts = instrument_id.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid instrument_id format")
        venue, _, symbol = parts
    
    # Validate venue
    try:
        venue_enum = Venue(venue)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid venue: {venue}. Valid venues: {[v.value for v in Venue]}")
    
    provider = provider_registry.get(venue_enum)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found or disabled")
    
    try:
        ticker = await provider.get_ticker(symbol)
        return {
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# ORDERBOOK
# ═══════════════════════════════════════════════════════════════

@router.get("/orderbook")
async def get_orderbook(
    instrument_id: Optional[str] = Query(None),
    venue: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    depth: int = Query(20, ge=1, le=1000)
):
    """Order book (L2)"""
    if not instrument_id and not (venue and symbol):
        raise HTTPException(status_code=400, detail="Provide instrument_id OR venue+symbol")
    
    if instrument_id:
        parts = instrument_id.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid instrument_id format")
        venue, _, symbol = parts
    
    provider = provider_registry.get(Venue(venue))
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    try:
        ob = await provider.get_orderbook(symbol, depth)
        return {
            "ts": ob.ts,
            "instrument_id": ob.instrument_id,
            "depth": ob.depth,
            "seq": ob.seq,
            "bids": ob.bids,
            "asks": ob.asks
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# TRADES
# ═══════════════════════════════════════════════════════════════

@router.get("/trades")
async def get_trades(
    instrument_id: Optional[str] = Query(None),
    venue: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """Последние сделки"""
    if not instrument_id and not (venue and symbol):
        raise HTTPException(status_code=400, detail="Provide instrument_id OR venue+symbol")
    
    if instrument_id:
        parts = instrument_id.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid instrument_id format")
        venue, _, symbol = parts
    
    provider = provider_registry.get(Venue(venue))
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    try:
        trades = await provider.get_trades(symbol, limit)
        return {
            "ts": _now_ms(),
            "instrument_id": f"{venue}:perp:{symbol}",
            "items": [
                {
                    "trade_id": t.trade_id,
                    "t": t.ts,
                    "price": t.price,
                    "qty": t.qty,
                    "side": t.side
                }
                for t in trades
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# CANDLES
# ═══════════════════════════════════════════════════════════════

@router.get("/candles")
async def get_candles(
    instrument_id: Optional[str] = Query(None),
    venue: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    granularity: str = Query("1h", description="Candle interval"),
    start: Optional[int] = Query(None, description="Start time (ms)"),
    end: Optional[int] = Query(None, description="End time (ms)"),
    limit: int = Query(100, ge=1, le=1000)
):
    """OHLCV свечи"""
    if not instrument_id and not (venue and symbol):
        raise HTTPException(status_code=400, detail="Provide instrument_id OR venue+symbol")
    
    if instrument_id:
        parts = instrument_id.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid instrument_id format")
        venue, _, symbol = parts
    
    provider = provider_registry.get(Venue(venue))
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    try:
        candles = await provider.get_candles(symbol, granularity, start, end, limit)
        return {
            "ts": _now_ms(),
            "instrument_id": f"{venue}:perp:{symbol}",
            "granularity": granularity,
            "candles": [
                {"t": c.t, "o": c.o, "h": c.h, "l": c.l, "c": c.c, "v": c.v}
                for c in candles
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# DERIVATIVES
# ═══════════════════════════════════════════════════════════════

@router.get("/funding")
async def get_funding(
    instrument_id: Optional[str] = Query(None),
    venue: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None)
):
    """Текущий funding rate"""
    if not instrument_id and not (venue and symbol):
        raise HTTPException(status_code=400, detail="Provide instrument_id OR venue+symbol")
    
    if instrument_id:
        parts = instrument_id.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid instrument_id format")
        venue, _, symbol = parts
    
    provider = provider_registry.get(Venue(venue))
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    if not provider.capabilities().has_funding:
        raise HTTPException(status_code=400, detail=f"Provider {venue} doesn't support funding")
    
    try:
        funding = await provider.get_funding(symbol)
        return {
            "ts": funding.ts,
            "instrument_id": funding.instrument_id,
            "funding_rate": funding.funding_rate,
            "funding_time": funding.funding_time
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/funding/history")
async def get_funding_history(
    instrument_id: Optional[str] = Query(None),
    venue: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    start: Optional[int] = Query(None),
    end: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500)
):
    """История funding rate"""
    if not instrument_id and not (venue and symbol):
        raise HTTPException(status_code=400, detail="Provide instrument_id OR venue+symbol")
    
    if instrument_id:
        parts = instrument_id.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid instrument_id format")
        venue, _, symbol = parts
    
    provider = provider_registry.get(Venue(venue))
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    if not provider.capabilities().has_funding_history:
        raise HTTPException(status_code=400, detail=f"Provider {venue} doesn't support funding history")
    
    try:
        history = await provider.get_funding_history(symbol, start, end, limit)
        return {
            "ts": _now_ms(),
            "instrument_id": f"{venue}:perp:{symbol}",
            "items": [
                {"funding_time": h.funding_time, "funding_rate": h.funding_rate}
                for h in history
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/open-interest")
async def get_open_interest(
    instrument_id: Optional[str] = Query(None),
    venue: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None)
):
    """Open Interest"""
    if not instrument_id and not (venue and symbol):
        raise HTTPException(status_code=400, detail="Provide instrument_id OR venue+symbol")
    
    if instrument_id:
        parts = instrument_id.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid instrument_id format")
        venue, _, symbol = parts
    
    provider = provider_registry.get(Venue(venue))
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    if not provider.capabilities().has_open_interest:
        raise HTTPException(status_code=400, detail=f"Provider {venue} doesn't support OI")
    
    try:
        oi = await provider.get_open_interest(symbol)
        return {
            "ts": oi.ts,
            "instrument_id": oi.instrument_id,
            "open_interest": oi.open_interest,
            "open_interest_usd": oi.open_interest_usd
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/long-short-ratio")
async def get_long_short_ratio(
    instrument_id: Optional[str] = Query(None),
    venue: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None)
):
    """Long/Short Ratio"""
    if not instrument_id and not (venue and symbol):
        raise HTTPException(status_code=400, detail="Provide instrument_id OR venue+symbol")
    
    if instrument_id:
        parts = instrument_id.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid instrument_id format")
        venue, _, symbol = parts
    
    provider = provider_registry.get(Venue(venue))
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    if not provider.capabilities().has_long_short_ratio:
        raise HTTPException(status_code=400, detail=f"Provider {venue} doesn't support L/S ratio")
    
    try:
        lsr = await provider.get_long_short_ratio(symbol)
        if not lsr:
            raise HTTPException(status_code=404, detail="L/S ratio not available")
        
        return {
            "ts": lsr.ts,
            "instrument_id": lsr.instrument_id,
            "long_ratio": lsr.long_ratio,
            "short_ratio": lsr.short_ratio,
            "long_short_ratio": lsr.long_short_ratio
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mark-price")
async def get_mark_price(
    instrument_id: Optional[str] = Query(None),
    venue: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None)
):
    """Mark Price + Index Price"""
    if not instrument_id and not (venue and symbol):
        raise HTTPException(status_code=400, detail="Provide instrument_id OR venue+symbol")
    
    if instrument_id:
        parts = instrument_id.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid instrument_id format")
        venue, _, symbol = parts
    
    provider = provider_registry.get(Venue(venue))
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    if not provider.capabilities().has_mark_price:
        raise HTTPException(status_code=400, detail=f"Provider {venue} doesn't support mark price")
    
    try:
        mark = await provider.get_mark_price(symbol)
        return mark
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# PROVIDERS
# ═══════════════════════════════════════════════════════════════

@router.get("/providers")
async def list_providers():
    """Список провайдеров"""
    return {
        "ts": _now_ms(),
        "providers": provider_registry.list_venues()
    }

@router.get("/providers/health")
async def providers_health():
    """Здоровье всех провайдеров"""
    health = await provider_registry.health_check_all()
    return {
        "ts": _now_ms(),
        "providers": health
    }
