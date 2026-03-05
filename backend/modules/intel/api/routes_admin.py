"""
Admin API Routes
Source management, data control, configuration
"""

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_db():
    """Dependency to get database"""
    from server import db
    return db


def get_source_manager():
    """Dependency to get source manager"""
    from server import db
    from modules.intel.engine.source_manager import create_source_manager
    return create_source_manager(db)


def get_coingecko_sync():
    """Dependency to get CoinGecko sync service"""
    from server import db
    from modules.intel.sources.coingecko.sync import CoinGeckoSync
    return CoinGeckoSync(db)


def get_coingecko_pool():
    """Get CoinGecko pool"""
    from modules.intel.sources.coingecko.client import coingecko_pool
    return coingecko_pool


# ═══════════════════════════════════════════════════════════════
# SOURCE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@router.get("/sources")
async def list_all_sources(
    status: Optional[str] = Query(None, description="Filter by status: active, paused, disabled"),
    sm = Depends(get_source_manager)
):
    """List all data sources with their status"""
    sources = await sm.list_sources(status)
    health = await sm.get_all_health()
    
    # Merge health data
    health_map = {h['source']: h for h in health}
    for source in sources:
        source['health'] = health_map.get(source['name'], {})
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'total': len(sources),
        'sources': sources
    }


@router.post("/sources/register")
async def register_source(
    request: Request,
    sm = Depends(get_source_manager)
):
    """
    Register a new data source
    
    Body:
    {
        "name": "coingecko",
        "type": "api",
        "endpoints": ["market", "categories", "trending"],
        "rate_limit": 30,
        "priority": 3,
        "interval_hours": 1
    }
    """
    data = await request.json()
    
    await sm.register_source(
        name=data['name'],
        source_type=data.get('type', 'api'),
        endpoints=data.get('endpoints', []),
        rate_limit=data.get('rate_limit', 10),
        priority=data.get('priority', 5),
        interval_hours=data.get('interval_hours', 6)
    )
    
    return {'ok': True, 'source': data['name'], 'status': 'registered'}


@router.post("/sources/{name}/status")
async def set_source_status(
    name: str,
    status: str = Query(..., description="Status: active, paused, disabled"),
    sm = Depends(get_source_manager)
):
    """Set source status"""
    if status not in ['active', 'paused', 'disabled']:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    await sm.set_status(name, status)
    return {'ok': True, 'source': name, 'status': status}


@router.post("/sources/{name}/priority")
async def set_source_priority(
    name: str,
    priority: int = Query(..., ge=1, le=10, description="Priority 1-10 (1=highest)"),
    db = Depends(get_db)
):
    """Set source priority"""
    result = await db.data_sources.update_one(
        {'name': name},
        {'$set': {'priority': priority, 'updated_at': datetime.now(timezone.utc)}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Source not found")
    
    return {'ok': True, 'source': name, 'priority': priority}


@router.get("/sources/priority/{entity}")
async def get_sources_for_entity(
    entity: str,
    sm = Depends(get_source_manager)
):
    """Get sources in priority order for an entity type"""
    sources = await sm.get_priority_for_entity(entity)
    return {
        'entity': entity,
        'sources': sources
    }


# ═══════════════════════════════════════════════════════════════
# DROPSTAB SSR SCRAPER STATUS
# ═══════════════════════════════════════════════════════════════

@router.get("/dropstab/status")
async def get_dropstab_status():
    """Check Dropstab SSR scraper status"""
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'method': 'ssr_scrape',
        'requires_api_key': False,
        'description': 'Extracts data from Next.js __NEXT_DATA__ (coinsBody.coins)',
        'pages_scraped': [
            '/ - market data (100 coins)',
            '/vesting - token unlocks',
            '/categories - category list',
            '/top-performance - gainers/losers',
            '/investors - VC list',
            '/latest-fundraising-rounds - funding rounds',
            '/activities - listings, events'
        ],
        'note': 'SSR gives ~100 coins per page. BFF API (extra-bff.dropstab.com) requires session/cookies.'
    }


@router.post("/dropstab/test")
async def test_dropstab_scraper():
    """Test Dropstab SSR scraping"""
    from modules.intel.dropstab.scraper import dropstab_scraper
    
    coins = await dropstab_scraper.scrape_coins()
    
    if coins:
        return {
            'ok': True,
            'method': 'ssr_scrape',
            'message': f'Successfully scraped {len(coins)} coins from __NEXT_DATA__',
            'sample': coins[:2] if len(coins) > 2 else coins
        }
    else:
        return {
            'ok': False,
            'method': 'ssr_scrape',
            'message': 'No data found - page structure may have changed',
            'tip': 'Check if dropstab.com loads correctly'
        }


# ═══════════════════════════════════════════════════════════════
# COINGECKO POOL MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@router.get("/coingecko/pool")
async def get_coingecko_pool_status(pool = Depends(get_coingecko_pool)):
    """Get CoinGecko API pool status"""
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        **pool.get_status()
    }


@router.post("/coingecko/pool/add")
async def add_coingecko_instance(
    name: str = Query(..., description="Instance name"),
    api_key: Optional[str] = Query(None, description="Pro API key (optional)"),
    rate_limit: int = Query(10, description="Rate limit per minute"),
    pool = Depends(get_coingecko_pool)
):
    """Add new CoinGecko API instance to pool"""
    pool.add_instance(name, api_key, rate_limit)
    return {
        'ok': True,
        'instance': name,
        'rate_limit': rate_limit,
        'has_api_key': bool(api_key),
        'pool_status': pool.get_status()
    }


@router.post("/coingecko/pool/reset")
async def reset_coingecko_instances(pool = Depends(get_coingecko_pool)):
    """Reset unhealthy instances for retry"""
    pool.reset_unhealthy()
    return {
        'ok': True,
        'pool_status': pool.get_status()
    }


@router.post("/coingecko/sync")
async def sync_coingecko_all(sync = Depends(get_coingecko_sync)):
    """Run full CoinGecko sync"""
    result = await sync.sync_all()
    return result


@router.post("/coingecko/sync/{entity}")
async def sync_coingecko_entity(
    entity: str,
    sync = Depends(get_coingecko_sync)
):
    """Sync specific entity from CoinGecko"""
    if entity == 'global':
        result = await sync.sync_global_market()
    elif entity == 'categories':
        result = await sync.sync_categories()
    elif entity == 'trending':
        result = await sync.sync_trending()
    elif entity == 'top_coins':
        result = await sync.sync_top_coins()
    else:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown entity: {entity}. Available: global, categories, trending, top_coins"
        )
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': 'coingecko',
        'entity': entity,
        **result
    }


@router.post("/coingecko/sync/coin/{coin_id}")
async def sync_coingecko_coin(
    coin_id: str,
    sync = Depends(get_coingecko_sync)
):
    """Sync specific coin from CoinGecko"""
    result = await sync.sync_coin(coin_id)
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': 'coingecko',
        **result
    }


# ═══════════════════════════════════════════════════════════════
# DATA MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@router.get("/data/overview")
async def get_data_overview(db = Depends(get_db)):
    """Get overview of all data in system"""
    collections = {
        'intel_investors': await db.intel_investors.count_documents({}),
        'intel_unlocks': await db.intel_unlocks.count_documents({}),
        'intel_fundraising': await db.intel_fundraising.count_documents({}),
        'intel_projects': await db.intel_projects.count_documents({}),
        'intel_activity': await db.intel_activity.count_documents({}),
        'intel_launchpads': await db.intel_launchpads.count_documents({}),
        'intel_categories': await db.intel_categories.count_documents({}),
        'intel_market': await db.intel_market.count_documents({}),
        'market_unlocks': await db.market_unlocks.count_documents({}),
        'moderation_queue': await db.moderation_queue.count_documents({})
    }
    
    # By source
    sources = {}
    for coll_name in ['intel_projects', 'intel_investors', 'intel_fundraising']:
        coll = db[coll_name]
        pipeline = [
            {'$group': {'_id': '$source', 'count': {'$sum': 1}}}
        ]
        async for doc in coll.aggregate(pipeline):
            source = doc['_id'] or 'unknown'
            if source not in sources:
                sources[source] = {}
            sources[source][coll_name] = doc['count']
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'collections': collections,
        'by_source': sources,
        'total_records': sum(collections.values())
    }


@router.get("/data/sources/{source}")
async def get_data_by_source(
    source: str,
    db = Depends(get_db)
):
    """Get data counts by source"""
    collections = [
        'intel_investors', 'intel_unlocks', 'intel_fundraising',
        'intel_projects', 'intel_activity', 'intel_launchpads',
        'intel_categories', 'intel_market'
    ]
    
    counts = {}
    for coll_name in collections:
        coll = db[coll_name]
        count = await coll.count_documents({'source': source})
        counts[coll_name] = count
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': source,
        'counts': counts,
        'total': sum(counts.values())
    }


@router.delete("/data/source/{source}")
async def delete_data_by_source(
    source: str,
    confirm: bool = Query(False, description="Confirm deletion"),
    db = Depends(get_db)
):
    """Delete all data from a specific source"""
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="Set confirm=true to delete data"
        )
    
    collections = [
        'intel_investors', 'intel_unlocks', 'intel_fundraising',
        'intel_projects', 'intel_activity', 'intel_launchpads',
        'intel_categories', 'intel_market'
    ]
    
    deleted = {}
    for coll_name in collections:
        coll = db[coll_name]
        result = await coll.delete_many({'source': source})
        deleted[coll_name] = result.deleted_count
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': source,
        'deleted': deleted,
        'total_deleted': sum(deleted.values())
    }


# ═══════════════════════════════════════════════════════════════
# DATA FIELD CONFIG
# ═══════════════════════════════════════════════════════════════

@router.get("/config/fields")
async def get_field_config(db = Depends(get_db)):
    """Get field display configuration"""
    cursor = db.field_config.find({}, {'_id': 0})
    configs = await cursor.to_list(100)
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'configs': configs
    }


@router.post("/config/fields")
async def set_field_config(
    request: Request,
    db = Depends(get_db)
):
    """
    Set field display configuration
    
    Body:
    {
        "entity": "project",
        "fields": {
            "market_cap": {"show": true, "source_priority": ["dropstab", "coingecko"]},
            "fdv": {"show": true, "source_priority": ["coingecko", "dropstab"]},
            "circulating_supply": {"show": true, "source_priority": ["coingecko"]}
        }
    }
    """
    data = await request.json()
    
    doc = {
        'entity': data['entity'],
        'fields': data['fields'],
        'updated_at': datetime.now(timezone.utc)
    }
    
    await db.field_config.update_one(
        {'entity': data['entity']},
        {'$set': doc},
        upsert=True
    )
    
    return {'ok': True, 'entity': data['entity']}


# ═══════════════════════════════════════════════════════════════
# HEALTH & MONITORING
# ═══════════════════════════════════════════════════════════════

@router.get("/health/sources")
async def get_sources_health(sm = Depends(get_source_manager)):
    """Get health status of all sources"""
    health = await sm.get_all_health()
    unhealthy = await sm.get_unhealthy_sources()
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'all': health,
        'unhealthy': unhealthy
    }


@router.get("/logs/sync")
async def get_sync_logs(
    source: Optional[str] = None,
    limit: int = Query(50, le=200),
    db = Depends(get_db)
):
    """Get sync operation logs"""
    query = {}
    if source:
        query['source'] = source
    
    cursor = db.sync_logs.find(query, {'_id': 0})
    logs = await cursor.sort('timestamp', -1).limit(limit).to_list(limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'logs': logs
    }
