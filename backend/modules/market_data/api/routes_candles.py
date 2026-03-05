"""
Candle API Routes
Stage 7: Historical Candle Storage

Endpoints for reading candles from ClickHouse.
TA Engine consumes candles ONLY through these endpoints.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timezone
import logging

from ..store.clickhouse_store import clickhouse_store
from ..services.candle_ingestor import candle_ingestor, TF_SECONDS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/candles", tags=["candles"])


# ═══════════════════════════════════════════════════════════════
# CANDLE DATA
# ═══════════════════════════════════════════════════════════════

@router.get("")
async def get_candles(
    exchange: str = Query(..., description="Exchange name (coinbase, hyperliquid)"),
    symbol: str = Query(..., description="Symbol (e.g., coinbase:spot:BTC-USD)"),
    tf: str = Query("1h", description="Timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1w)"),
    from_ts: Optional[int] = Query(None, description="From timestamp (unix seconds)"),
    to_ts: Optional[int] = Query(None, description="To timestamp (unix seconds)"),
    limit: int = Query(500, ge=1, le=5000, description="Max candles to return")
):
    """
    Get OHLCV candles from historical storage.
    
    This is the ONLY endpoint TA Engine should use for candle data.
    Never call exchanges directly from TA.
    """
    try:
        from_dt = datetime.fromtimestamp(from_ts, tz=timezone.utc) if from_ts else None
        to_dt = datetime.fromtimestamp(to_ts, tz=timezone.utc) if to_ts else None
        
        candles = clickhouse_store.get_candles(
            exchange=exchange,
            symbol=symbol,
            tf=tf,
            from_ts=from_dt,
            to_ts=to_dt,
            limit=limit
        )
        
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "exchange": exchange,
            "symbol": symbol,
            "tf": tf,
            "count": len(candles),
            "candles": candles
        }
    except Exception as e:
        logger.error(f"[Candles API] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def get_latest_candles(
    exchange: str = Query(...),
    symbol: str = Query(...),
    tf: str = Query("1h"),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get the most recent candles"""
    try:
        candles = clickhouse_store.get_candles(
            exchange=exchange,
            symbol=symbol,
            tf=tf,
            limit=limit
        )
        
        # Return in reverse order (newest first)
        candles.reverse()
        
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "exchange": exchange,
            "symbol": symbol,
            "tf": tf,
            "count": len(candles),
            "candles": candles
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# HEALTH & INTEGRITY
# ═══════════════════════════════════════════════════════════════

@router.get("/health")
async def candle_health(
    exchange: str = Query(...),
    symbol: str = Query(...),
    tf: str = Query("1h"),
    min_candles: int = Query(100, description="Minimum required candles"),
    max_staleness: int = Query(300, description="Max staleness in seconds")
):
    """
    Health check for candle data quality.
    
    TA Engine should call this before processing to ensure data quality.
    Returns:
    - healthy: bool - whether data is usable
    - reason: str - if unhealthy, the reason (NO_DATA, INSUFFICIENT_DATA, STALE_DATA)
    """
    try:
        health = clickhouse_store.health_check(
            exchange=exchange,
            symbol=symbol,
            tf=tf,
            min_candles=min_candles,
            max_staleness_seconds=max_staleness
        )
        
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "exchange": exchange,
            "symbol": symbol,
            "tf": tf,
            **health
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/continuity")
async def check_continuity(
    exchange: str = Query(...),
    symbol: str = Query(...),
    tf: str = Query("1h")
):
    """
    Check candle continuity (no gaps).
    
    Returns gap information if any gaps exist.
    """
    try:
        interval_seconds = TF_SECONDS.get(tf, 3600)
        
        result = clickhouse_store.check_continuity(
            exchange=exchange,
            symbol=symbol,
            tf=tf,
            expected_interval_seconds=interval_seconds
        )
        
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "exchange": exchange,
            "symbol": symbol,
            "tf": tf,
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# INGESTION MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@router.get("/ingestion/status")
async def ingestion_status():
    """Get candle ingestion worker status"""
    try:
        status = await candle_ingestor.status()
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            **status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingestion/backfill")
async def manual_backfill(
    exchange: str = Query(...),
    symbol: str = Query(..., description="Native symbol (e.g., BTC-USD)"),
    tf: str = Query("1h"),
    depth: int = Query(500, ge=10, le=5000)
):
    """
    Manually trigger backfill for a specific symbol.
    
    Use this to fill gaps or add new symbols.
    """
    try:
        result = await candle_ingestor.manual_backfill(
            exchange=exchange,
            symbol=symbol,
            tf=tf,
            depth=depth
        )
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════

@router.get("/stats")
async def candle_stats():
    """Get overall candle storage statistics"""
    try:
        ch_health = clickhouse_store.health()
        ch_stats = clickhouse_store.stats() if ch_health.get('healthy') else {}
        
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "clickhouse": ch_health,
            "stats": ch_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols")
async def list_available_symbols():
    """List all symbols with candle data"""
    try:
        clickhouse_store.ensure_connected()
        
        result = clickhouse_store._client.execute(
            """
            SELECT 
                exchange,
                symbol,
                groupArray(tf) as timeframes,
                count() as candle_count,
                min(ts) as earliest,
                max(ts) as latest
            FROM fomo.candles_ohlcv
            GROUP BY exchange, symbol
            ORDER BY candle_count DESC
            LIMIT 100
            """
        )
        
        symbols = []
        for row in result:
            symbols.append({
                "exchange": row[0],
                "symbol": row[1],
                "timeframes": row[2],
                "candle_count": row[3],
                "earliest": row[4].isoformat() if row[4] else None,
                "latest": row[5].isoformat() if row[5] else None
            })
        
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "count": len(symbols),
            "symbols": symbols
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
