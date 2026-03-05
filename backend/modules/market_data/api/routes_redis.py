"""
Redis API Routes
Статус и управление Redis layer + Cache-based data endpoints
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import time

from ..store.redis_store import redis_store
from ..services.redis_pipeline import redis_pipeline
from ..services.instrument_registry import instrument_registry

router = APIRouter(prefix="/api/redis", tags=["Redis"])


def _now_ms() -> int:
    return int(time.time() * 1000)


# ═══════════════════════════════════════════════════════════════
# HEALTH & STATS
# ═══════════════════════════════════════════════════════════════

@router.get("/health")
async def redis_health():
    """Redis health check"""
    health = await redis_store.health()
    return {
        "ts": _now_ms(),
        **health
    }


@router.get("/stats")
async def redis_stats():
    """Redis statistics"""
    try:
        stats = await redis_store.stats()
        return {
            "ts": _now_ms(),
            **stats
        }
    except Exception as e:
        return {
            "ts": _now_ms(),
            "error": str(e),
            "connected": False
        }


@router.get("/pipeline/status")
async def pipeline_status():
    """Pipeline status"""
    status = await redis_pipeline.status()
    return {
        "ts": _now_ms(),
        **status
    }


@router.post("/pipeline/warm")
async def warm_cache():
    """Manually warm the cache"""
    await redis_pipeline.warm_cache()
    stats = await redis_store.stats()
    return {
        "ts": _now_ms(),
        "status": "warmed",
        "keys": stats.get("keys", {})
    }


# ═══════════════════════════════════════════════════════════════
# CACHE DATA ENDPOINTS - Read from Redis (fast!)
# ═══════════════════════════════════════════════════════════════

@router.get("/cache/ticker")
async def get_cached_ticker(
    instrument_id: str = Query(..., description="Instrument ID (e.g., coinbase:spot:BTC-USD)")
):
    """
    Get ticker from Redis cache.
    Ultra-fast (<10ms) - reads from pre-populated cache.
    """
    ticker = await redis_store.get_ticker(instrument_id)
    
    if not ticker:
        raise HTTPException(
            status_code=404, 
            detail=f"Ticker not found in cache for {instrument_id}. It may not be cached yet."
        )
    
    return {
        "ts": _now_ms(),
        "source": "cache",
        **ticker
    }


@router.get("/cache/tickers")
async def get_cached_tickers(
    instrument_ids: str = Query(..., description="Comma-separated instrument IDs")
):
    """
    Get multiple tickers from Redis cache (batch).
    """
    ids = [id.strip() for id in instrument_ids.split(",")]
    tickers = await redis_store.get_all_tickers(ids)
    
    return {
        "ts": _now_ms(),
        "source": "cache",
        "requested": len(ids),
        "found": len(tickers),
        "items": tickers
    }


@router.get("/cache/funding")
async def get_cached_funding(
    instrument_id: str = Query(..., description="Instrument ID")
):
    """Get funding rate from Redis cache."""
    funding = await redis_store.get_funding(instrument_id)
    
    if not funding:
        raise HTTPException(status_code=404, detail=f"Funding not found for {instrument_id}")
    
    return {
        "ts": _now_ms(),
        "source": "cache",
        **funding
    }


@router.get("/cache/open-interest")
async def get_cached_open_interest(
    instrument_id: str = Query(..., description="Instrument ID")
):
    """Get open interest from Redis cache."""
    oi = await redis_store.get_open_interest(instrument_id)
    
    if not oi:
        raise HTTPException(status_code=404, detail=f"OI not found for {instrument_id}")
    
    return {
        "ts": _now_ms(),
        "source": "cache",
        **oi
    }


@router.get("/cache/asset")
async def get_cached_asset(
    asset_id: str = Query(..., description="Asset ID (e.g., btc, eth)")
):
    """
    Get aggregated asset snapshot from Redis cache.
    Contains: price, volume breakdown, funding, OI, confidence.
    """
    snapshot = await redis_store.get_asset_snapshot(asset_id.lower())
    
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Asset snapshot not found for {asset_id}")
    
    return {
        "ts": _now_ms(),
        "source": "cache",
        **snapshot
    }


@router.get("/cache/global")
async def get_cached_global():
    """
    Get global market snapshot from Redis cache.
    Contains: total volume, dominance, active assets.
    """
    snapshot = await redis_store.get_global_snapshot()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="Global snapshot not found")
    
    return {
        "ts": _now_ms(),
        "source": "cache",
        **snapshot
    }


@router.get("/cache/liquidations")
async def get_cached_liquidations(
    limit: int = Query(100, ge=1, le=1000)
):
    """Get recent liquidations from Redis stream."""
    liquidations = await redis_store.get_liquidations(limit)
    
    return {
        "ts": _now_ms(),
        "source": "cache",
        "count": len(liquidations),
        "items": liquidations
    }


@router.get("/cache/trades")
async def get_cached_trades(
    instrument_id: str = Query(..., description="Instrument ID"),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get recent trades from Redis stream."""
    trades = await redis_store.get_trades(instrument_id, limit)
    
    return {
        "ts": _now_ms(),
        "source": "cache",
        "instrument_id": instrument_id,
        "count": len(trades),
        "items": trades
    }
