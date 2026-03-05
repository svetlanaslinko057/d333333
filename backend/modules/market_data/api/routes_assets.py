"""
Assets API Routes
Данные по отдельному активу
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import time

from ..domain.types import MarketType
from ..services.aggregator import aggregator
from ..services.instrument_registry import instrument_registry
from ..providers.registry import provider_registry

router = APIRouter(prefix="/api/assets", tags=["Assets"])

def _now_ms() -> int:
    return int(time.time() * 1000)

# ═══════════════════════════════════════════════════════════════
# SEARCH (must be before /{asset_id})
# ═══════════════════════════════════════════════════════════════

@router.get("/search")
async def search_assets(
    q: Optional[str] = Query(None, description="Search query"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Поиск активов
    """
    await instrument_registry.sync_all()
    
    if q:
        assets = instrument_registry.search_assets(q, limit)
    else:
        assets = instrument_registry.list_assets()[:limit]
    
    return {
        "ts": _now_ms(),
        "query": q,
        "items": [
            {
                "asset_id": a.asset_id,
                "symbol": a.symbol,
                "name": a.name,
                "type": a.type,
                "icon_url": a.icon_url
            }
            for a in assets
        ]
    }

# ═══════════════════════════════════════════════════════════════
# ASSET PROFILE
# ═══════════════════════════════════════════════════════════════

@router.get("/{asset_id}")
async def get_asset(asset_id: str):
    """
    Профиль актива + ключевые метрики
    """
    await instrument_registry.sync_all()
    
    asset = instrument_registry.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    # Получаем тикер
    ticker = await aggregator.get_ticker_for_asset(asset_id)
    if not ticker:
        raise HTTPException(status_code=404, detail=f"No market data for {asset_id}")
    
    # Получаем venues
    venues = instrument_registry.get_venues_for_asset(asset_id)
    instruments = instrument_registry.get_asset_instruments(asset_id)
    
    return {
        "ts": _now_ms(),
        "asset": {
            "asset_id": asset.asset_id,
            "symbol": asset.symbol,
            "name": asset.name,
            "type": asset.type,
            "category": asset.category,
            "description": asset.description,
            "links": asset.links,
            "contracts": asset.contracts
        },
        "metrics": {
            "quote": "USD",
            "price": ticker.last,
            "change_24h": ticker.change_24h,
            "range_24h": {
                "low": ticker.low_24h,
                "high": ticker.high_24h
            },
            "volume_24h": ticker.volume_24h,
            "market_cap": None,  # Требует supply из Asset Intel
            "fdv": None,
            "dominance": None,
            "supplies": {
                "circulating": None,
                "total": None,
                "max": None
            },
            "ath": None,
            "atl": None
        },
        "coverage": {
            "venues": [v.value for v in venues],
            "instruments": len(instruments)
        }
    }

# ═══════════════════════════════════════════════════════════════
# PERFORMANCE
# ═══════════════════════════════════════════════════════════════

@router.get("/{asset_id}/performance")
async def get_asset_performance(asset_id: str):
    """
    Performance по периодам: 1h, 24h, 7d, 30d, 90d, 1y
    """
    await instrument_registry.sync_all()
    
    asset = instrument_registry.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    # Получаем свечи для расчета performance
    candles_1h = await aggregator.get_candles_for_asset(asset_id, "1h", 720)  # 30 дней
    candles_1d = await aggregator.get_candles_for_asset(asset_id, "1d", 365)  # 1 год
    
    if not candles_1h:
        raise HTTPException(status_code=404, detail=f"No candle data for {asset_id}")
    
    current_price = candles_1h[-1].c if candles_1h else 0
    
    def calc_change(candles, periods_back):
        if len(candles) > periods_back:
            old_price = candles[-periods_back - 1].o
            return (current_price - old_price) / old_price if old_price > 0 else None
        return None
    
    items = [
        {"range": "1h", "change": calc_change(candles_1h, 1)},
        {"range": "24h", "change": calc_change(candles_1h, 24)},
        {"range": "7d", "change": calc_change(candles_1h, 168)},
        {"range": "30d", "change": calc_change(candles_1d, 30) if candles_1d else None},
        {"range": "90d", "change": calc_change(candles_1d, 90) if candles_1d else None},
        {"range": "1y", "change": calc_change(candles_1d, 365) if candles_1d else None},
    ]
    
    return {
        "ts": _now_ms(),
        "asset_id": asset_id,
        "quote": "USD",
        "items": [i for i in items if i["change"] is not None]
    }

# ═══════════════════════════════════════════════════════════════
# CHART
# ═══════════════════════════════════════════════════════════════

@router.get("/{asset_id}/chart")
async def get_asset_chart(
    asset_id: str,
    series: str = Query("price", description="Series type: price, ohlcv"),
    range: str = Query("7d", description="Range: 24h, 7d, 30d, 90d, 1y, all"),
    granularity: str = Query("1h", description="Granularity: 1m, 5m, 15m, 1h, 4h, 1d"),
    quote: str = Query("USD")
):
    """
    Данные для графика
    """
    await instrument_registry.sync_all()
    
    asset = instrument_registry.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    # Определяем лимит по range
    range_limits = {
        "24h": 24 if granularity == "1h" else 1440,
        "7d": 168 if granularity == "1h" else 7,
        "30d": 720 if granularity == "1h" else 30,
        "90d": 90 if granularity == "1d" else 2160,
        "1y": 365 if granularity == "1d" else 8760,
        "all": 1000
    }
    limit = range_limits.get(range, 168)
    
    # Получаем свечи
    candles = await aggregator.get_candles_for_asset(asset_id, granularity, limit)
    
    if not candles:
        raise HTTPException(status_code=404, detail=f"No chart data for {asset_id}")
    
    response = {
        "ts": _now_ms(),
        "asset_id": asset_id,
        "quote": quote,
        "series": series,
        "range": range,
        "granularity": granularity
    }
    
    if series == "price":
        response["points"] = [{"t": c.t, "v": c.c} for c in candles]
    else:  # ohlcv
        response["candles"] = [
            {"t": c.t, "o": c.o, "h": c.h, "l": c.l, "c": c.c, "v": c.v}
            for c in candles
        ]
    
    return response

# ═══════════════════════════════════════════════════════════════
# VENUES
# ═══════════════════════════════════════════════════════════════

@router.get("/{asset_id}/venues")
async def get_asset_venues(
    asset_id: str,
    type: str = Query("all", description="Filter: all, spot, perp, derivative")
):
    """
    Список бирж где торгуется актив
    """
    await instrument_registry.sync_all()
    
    asset = instrument_registry.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    instruments = instrument_registry.get_asset_instruments(asset_id)
    
    # Фильтруем по типу
    if type != "all":
        mt = MarketType.PERP if type in ["perp", "derivative"] else MarketType.SPOT
        instruments = [i for i in instruments if i.market_type == mt]
    
    # Получаем данные для каждого инструмента
    items = []
    total_volume = 0
    
    for inst in instruments:
        provider = provider_registry.get(inst.venue)
        if not provider:
            continue
        
        try:
            ticker = await provider.get_ticker(inst.native_symbol)
            
            item = {
                "instrument_id": inst.instrument_id,
                "venue": inst.venue.value,
                "market_type": inst.market_type.value,
                "native_symbol": inst.native_symbol,
                "base": inst.base,
                "quote": inst.quote,
                "last_price": ticker.last,
                "volume_24h": ticker.volume_24h,
                "volume_share": None,  # Рассчитаем после
                "spread_bps": None
            }
            
            # Spread
            if ticker.bid and ticker.ask and ticker.bid > 0:
                spread = (ticker.ask - ticker.bid) / ticker.bid * 10000
                item["spread_bps"] = round(spread, 2)
            
            # Derivatives data
            if inst.market_type == MarketType.PERP and provider.capabilities().has_funding:
                try:
                    funding = await provider.get_funding(inst.native_symbol)
                    oi = await provider.get_open_interest(inst.native_symbol) if provider.capabilities().has_open_interest else None
                    mark = await provider.get_mark_price(inst.native_symbol) if provider.capabilities().has_mark_price else None
                    
                    item["derivatives"] = {
                        "mark_price": mark.mark_price if mark else None,
                        "index_price": mark.index_price if mark else None,
                        "funding_rate": funding.funding_rate if funding else None,
                        "open_interest": oi.open_interest if oi else None
                    }
                except:
                    pass
            
            items.append(item)
            total_volume += ticker.volume_24h or 0
            
        except Exception as e:
            print(f"[Assets API] Failed to get venue data for {inst.instrument_id}: {e}")
    
    # Рассчитываем volume share
    for item in items:
        if item["volume_24h"] and total_volume > 0:
            item["volume_share"] = round(item["volume_24h"] / total_volume, 4)
    
    return {
        "ts": _now_ms(),
        "asset_id": asset_id,
        "quote": "USD",
        "type": type,
        "items": items
    }

