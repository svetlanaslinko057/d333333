"""
Market API Routes
Агрегированные данные для UI
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import time

from ..services.aggregator import aggregator
from ..services.instrument_registry import instrument_registry

router = APIRouter(prefix="/api/market", tags=["Market"])

def _now_ms() -> int:
    return int(time.time() * 1000)

# ═══════════════════════════════════════════════════════════════
# OVERVIEW
# ═══════════════════════════════════════════════════════════════

@router.get("/overview")
async def get_market_overview():
    """
    Market Overview для главной страницы.
    Возвращает: global metrics, benchmarks, top gainers/losers, activities
    """
    try:
        overview = await aggregator.get_market_overview()
        
        # Добавляем top gainers/losers
        gl = await aggregator.get_top_gainers_losers(5)
        
        return {
            "ts": overview.ts,
            "quote": overview.quote,
            "global": {
                "coverage_market_cap": overview.global_metrics.coverage_market_cap,
                "coverage_volume_24h": overview.global_metrics.coverage_volume_24h,
                "btc_dominance": overview.global_metrics.btc_dominance,
                "eth_dominance": overview.global_metrics.eth_dominance
            },
            "benchmarks": [b.model_dump() for b in overview.benchmarks],
            "sentiment": overview.sentiment.model_dump() if overview.sentiment else None,
            "top_gainers_24h": gl["gainers"],
            "top_losers_24h": gl["losers"],
            "new_activities": [a.model_dump() for a in overview.new_activities]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# ASSETS TABLE
# ═══════════════════════════════════════════════════════════════

@router.get("/assets")
async def get_market_assets(
    tab: str = Query("full", description="Tab: full, trending, new"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    sort: str = Query("volume_24h", description="Sort field"),
    dir: str = Query("desc", description="Sort direction: asc, desc"),
    quote: str = Query("USD", description="Quote currency"),
    search: Optional[str] = Query(None, description="Search query"),
    sparkline: str = Query("7d", description="Sparkline range")
):
    """
    Таблица активов (Full Market / Trending / New)
    """
    try:
        # Получаем активы
        items = await aggregator.get_market_assets(
            page=page,
            page_size=page_size,
            sort_by=sort,
            direction=dir
        )
        
        # Фильтруем по поиску
        if search:
            search_lower = search.lower()
            items = [
                i for i in items 
                if search_lower in i.asset_id or 
                   search_lower in i.symbol.lower() or
                   search_lower in i.name.lower()
            ]
        
        # Общее количество активов
        total = len(instrument_registry.list_assets())
        
        return {
            "ts": _now_ms(),
            "tab": tab,
            "quote": quote,
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [
                {
                    "asset_id": i.asset_id,
                    "rank": i.rank,
                    "symbol": i.symbol,
                    "name": i.name,
                    "icon_url": i.icon_url,
                    "price": i.price,
                    "change_1h": i.change_1h,
                    "change_24h": i.change_24h,
                    "change_7d": i.change_7d,
                    "market_cap": i.market_cap,
                    "fdv": i.fdv,
                    "volume_24h": i.volume_24h,
                    "circulating_supply": i.circulating_supply,
                    "max_supply": i.max_supply,
                    "sparkline": i.sparkline.model_dump() if i.sparkline else None,
                    "data_quality": i.data_quality.model_dump()
                }
                for i in items
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════

@router.get("/stats")
async def get_market_stats():
    """Статистика Market Data системы"""
    await instrument_registry.sync_all()
    
    return {
        "ts": _now_ms(),
        "registry": instrument_registry.stats(),
        "providers": provider_registry.list_venues()
    }

# Import provider_registry
from ..providers.registry import provider_registry
