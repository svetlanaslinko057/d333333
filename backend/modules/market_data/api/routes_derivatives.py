"""
Derivatives API Routes
Funding, Open Interest, Liquidations, Long/Short Ratio
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import time

from ..domain.types import Venue
from ..providers.registry import provider_registry

router = APIRouter(prefix="/api/derivatives", tags=["Derivatives"])

def _now_ms() -> int:
    return int(time.time() * 1000)

def _validate_venue(venue: str) -> Venue:
    try:
        return Venue(venue)
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid venue: {venue}. Valid: {[v.value for v in Venue]}"
        )

# ═══════════════════════════════════════════════════════════════
# FUNDING
# ═══════════════════════════════════════════════════════════════

@router.get("/funding")
async def get_funding(
    venue: str = Query(..., description="Venue (binance, bybit, hyperliquid)"),
    symbol: str = Query(..., description="Symbol (BTCUSDT, BTC-PERP)")
):
    """Current funding rate"""
    venue_enum = _validate_venue(venue)
    provider = provider_registry.get(venue_enum)
    
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
            "funding_rate_annualized": funding.funding_rate * 3 * 365,  # 8h intervals
            "next_funding_time": funding.funding_time
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/funding/history")
async def get_funding_history(
    venue: str = Query(...),
    symbol: str = Query(...),
    start: Optional[int] = Query(None, description="Start time (ms)"),
    end: Optional[int] = Query(None, description="End time (ms)"),
    limit: int = Query(100, ge=1, le=500)
):
    """Funding rate history"""
    venue_enum = _validate_venue(venue)
    provider = provider_registry.get(venue_enum)
    
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    if not provider.capabilities().has_funding_history:
        raise HTTPException(status_code=400, detail=f"Provider {venue} doesn't support funding history")
    
    try:
        history = await provider.get_funding_history(symbol, start, end, limit)
        return {
            "ts": _now_ms(),
            "venue": venue,
            "symbol": symbol,
            "items": [
                {"funding_time": h.funding_time, "funding_rate": h.funding_rate}
                for h in history
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# OPEN INTEREST
# ═══════════════════════════════════════════════════════════════

@router.get("/open-interest")
async def get_open_interest(
    venue: str = Query(...),
    symbol: str = Query(...)
):
    """Current Open Interest"""
    venue_enum = _validate_venue(venue)
    provider = provider_registry.get(venue_enum)
    
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

@router.get("/open-interest/history")
async def get_open_interest_history(
    venue: str = Query(...),
    symbol: str = Query(...),
    period: str = Query("5m", description="Period: 5m, 15m, 30m, 1h, 4h, 1d"),
    limit: int = Query(100, ge=1, le=500)
):
    """Open Interest history (Binance only)"""
    venue_enum = _validate_venue(venue)
    
    if venue_enum != Venue.BINANCE:
        raise HTTPException(status_code=400, detail="OI history only available for Binance")
    
    provider = provider_registry.get(venue_enum)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    try:
        # Binance-specific method
        history = await provider.get_open_interest_history(symbol, period, limit)
        return {
            "ts": _now_ms(),
            "venue": venue,
            "symbol": symbol,
            "period": period,
            "items": history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# LIQUIDATIONS
# ═══════════════════════════════════════════════════════════════

@router.get("/liquidations")
async def get_liquidations(
    venue: str = Query(...),
    symbol: str = Query(...),
    limit: int = Query(100, ge=1, le=1000)
):
    """Recent liquidations"""
    venue_enum = _validate_venue(venue)
    provider = provider_registry.get(venue_enum)
    
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {venue} not found")
    
    if not provider.capabilities().has_liquidations:
        raise HTTPException(status_code=400, detail=f"Provider {venue} doesn't support liquidations")
    
    try:
        liqs = await provider.get_liquidations(symbol, limit)
        
        # Aggregate stats
        total_usd = sum(l.value_usd or 0 for l in liqs)
        long_liqs = [l for l in liqs if l.side == "sell"]  # Long liquidation = sell
        short_liqs = [l for l in liqs if l.side == "buy"]  # Short liquidation = buy
        
        return {
            "ts": _now_ms(),
            "venue": venue,
            "symbol": symbol,
            "count": len(liqs),
            "total_usd": total_usd,
            "long_liquidations": len(long_liqs),
            "short_liquidations": len(short_liqs),
            "items": [
                {
                    "t": l.t,
                    "side": l.side,
                    "price": l.price,
                    "qty": l.qty,
                    "value_usd": l.value_usd
                }
                for l in liqs
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# LONG/SHORT RATIO
# ═══════════════════════════════════════════════════════════════

@router.get("/long-short")
async def get_long_short_ratio(
    venue: str = Query(...),
    symbol: str = Query(...)
):
    """Long/Short account ratio"""
    venue_enum = _validate_venue(venue)
    provider = provider_registry.get(venue_enum)
    
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
            "long_short_ratio": lsr.long_short_ratio,
            "sentiment": "bullish" if lsr.long_short_ratio > 1 else "bearish" if lsr.long_short_ratio < 1 else "neutral"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# SENTIMENT (Binance-specific)
# ═══════════════════════════════════════════════════════════════

@router.get("/sentiment")
async def get_market_sentiment(
    symbol: str = Query(..., description="Symbol (BTCUSDT)")
):
    """
    Aggregated market sentiment from Binance.
    Includes: L/S ratio, top trader ratio, taker buy/sell
    """
    provider = provider_registry.get(Venue.BINANCE)
    if not provider:
        raise HTTPException(status_code=404, detail="Binance provider not available")
    
    try:
        # Global L/S ratio
        lsr = await provider.get_long_short_ratio(symbol)
        
        # Top trader ratio
        top_ratio = await provider.get_top_trader_long_short_ratio(symbol, "position")
        
        # Taker buy/sell
        taker = await provider.get_taker_buy_sell_ratio(symbol)
        
        return {
            "ts": _now_ms(),
            "symbol": symbol,
            "global_long_short": {
                "long_ratio": lsr.long_ratio if lsr else None,
                "short_ratio": lsr.short_ratio if lsr else None,
                "ratio": lsr.long_short_ratio if lsr else None
            } if lsr else None,
            "top_trader_position": {
                "long_ratio": top_ratio.long_ratio if top_ratio else None,
                "short_ratio": top_ratio.short_ratio if top_ratio else None,
                "ratio": top_ratio.long_short_ratio if top_ratio else None
            } if top_ratio else None,
            "taker_buy_sell": {
                "buy_sell_ratio": taker["buy_sell_ratio"] if taker else None,
                "buy_vol": taker["buy_vol"] if taker else None,
                "sell_vol": taker["sell_vol"] if taker else None
            } if taker else None,
            "overall_sentiment": _calculate_sentiment(lsr, top_ratio, taker)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _calculate_sentiment(lsr, top_ratio, taker) -> str:
    """Calculate overall sentiment from multiple indicators"""
    signals = []
    
    if lsr and lsr.long_short_ratio:
        if lsr.long_short_ratio > 1.1:
            signals.append(1)  # bullish
        elif lsr.long_short_ratio < 0.9:
            signals.append(-1)  # bearish
        else:
            signals.append(0)
    
    if top_ratio and top_ratio.long_short_ratio:
        if top_ratio.long_short_ratio > 1.1:
            signals.append(1)
        elif top_ratio.long_short_ratio < 0.9:
            signals.append(-1)
        else:
            signals.append(0)
    
    if taker and taker.get("buy_sell_ratio"):
        if taker["buy_sell_ratio"] > 1.1:
            signals.append(1)
        elif taker["buy_sell_ratio"] < 0.9:
            signals.append(-1)
        else:
            signals.append(0)
    
    if not signals:
        return "neutral"
    
    avg = sum(signals) / len(signals)
    if avg > 0.3:
        return "bullish"
    elif avg < -0.3:
        return "bearish"
    return "neutral"
