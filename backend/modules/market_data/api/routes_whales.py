"""
Whales API Routes
Hyperliquid Whale Tracking
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import time

from ..providers.hyperliquid.adapter import hyperliquid_adapter

router = APIRouter(prefix="/api/whales", tags=["Whales"])

def _now_ms() -> int:
    return int(time.time() * 1000)

# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

@router.get("/health")
async def whale_health():
    """Здоровье Hyperliquid whale provider"""
    health = await hyperliquid_adapter.health_check()
    
    return {
        "ok": health["healthy"],
        "provider": "hyperliquid",
        "health": health,
        "data_mode": "LIVE",
        "address_count": len(hyperliquid_adapter.WHALE_ADDRESSES)
    }

# ═══════════════════════════════════════════════════════════════
# SNAPSHOTS
# ═══════════════════════════════════════════════════════════════

@router.get("/snapshots")
async def get_whale_snapshots(
    symbols: Optional[str] = Query(None, description="Filter by symbols (comma-separated)"),
    limit: int = Query(10, ge=1, le=100)
):
    """
    Получает позиции всех отслеживаемых китов
    """
    start = time.time()
    
    try:
        addresses = hyperliquid_adapter.WHALE_ADDRESSES[:limit]
        snapshots = await hyperliquid_adapter.get_whale_snapshots(addresses)
        
        # Фильтр по символам
        if symbols:
            symbol_list = [s.strip().upper() for s in symbols.split(",")]
            snapshots = [s for s in snapshots if s["coin"].upper() in symbol_list]
        
        duration_ms = (time.time() - start) * 1000
        
        return {
            "ok": True,
            "ts": _now_ms(),
            "data_mode": "LIVE",
            "duration_ms": duration_ms,
            "count": len(snapshots),
            "snapshots": snapshots
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# USER STATE
# ═══════════════════════════════════════════════════════════════

@router.get("/user/{address}")
async def get_user_positions(address: str):
    """
    Получает позиции конкретного адреса
    """
    try:
        positions = await hyperliquid_adapter.get_user_positions(address)
        
        return {
            "ok": True,
            "ts": _now_ms(),
            "address": address,
            "positions": positions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# LEADERBOARD
# ═══════════════════════════════════════════════════════════════

@router.get("/leaderboard")
async def get_leaderboard(
    window: str = Query("day", description="Window: day, week, month, allTime")
):
    """
    Топ трейдеры по PnL
    """
    try:
        leaderboard = await hyperliquid_adapter.get_leaderboard(window)
        
        return {
            "ok": True,
            "ts": _now_ms(),
            "window": window,
            "traders": leaderboard[:50]  # Top 50
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# STATUS
# ═══════════════════════════════════════════════════════════════

@router.get("/status")
async def whale_status():
    """Статус whale tracking"""
    return {
        "ok": True,
        "ts": _now_ms(),
        "status": {
            "provider": "hyperliquid",
            "enabled": True,
            "healthy": hyperliquid_adapter._healthy,
            "data_mode": "LIVE",
            "whale_addresses": len(hyperliquid_adapter.WHALE_ADDRESSES),
            "last_latency_ms": hyperliquid_adapter._last_latency,
            "last_error": hyperliquid_adapter._last_error
        }
    }

# ═══════════════════════════════════════════════════════════════
# ADDRESSES MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@router.get("/addresses")
async def list_whale_addresses():
    """Список отслеживаемых адресов"""
    return {
        "ok": True,
        "ts": _now_ms(),
        "addresses": hyperliquid_adapter.WHALE_ADDRESSES
    }

@router.post("/addresses")
async def add_whale_address(address: str = Query(..., description="Ethereum address to track")):
    """Добавляет адрес для отслеживания"""
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(status_code=400, detail="Invalid Ethereum address")
    
    if address not in hyperliquid_adapter.WHALE_ADDRESSES:
        hyperliquid_adapter.WHALE_ADDRESSES.append(address)
    
    return {
        "ok": True,
        "ts": _now_ms(),
        "message": f"Address {address} added",
        "total_addresses": len(hyperliquid_adapter.WHALE_ADDRESSES)
    }
