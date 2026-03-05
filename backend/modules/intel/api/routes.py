"""
Intel API Routes
Endpoints for crypto intelligence data
"""

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/intel", tags=["intel"])


def get_db():
    """Dependency to get database"""
    from server import db
    return db


def get_dropstab_sync():
    """Dependency to get Dropstab sync service (SSR scraping)"""
    from server import db
    from ..dropstab.sync import DropstabSync
    return DropstabSync(db)


def get_cryptorank_sync():
    """Dependency to get CryptoRank sync service"""
    from server import db
    from ..sources.cryptorank.sync import CryptoRankSync
    return CryptoRankSync(db)


# ═══════════════════════════════════════════════════════════════
# SYNC ENDPOINTS - DROPSTAB
# ═══════════════════════════════════════════════════════════════

@router.post("/sync/dropstab")
async def sync_dropstab_all(sync = Depends(get_dropstab_sync)):
    """
    Run full Dropstab sync (all endpoints)
    Uses api.dropstab.com - no API key required
    """
    result = await sync.sync_all()
    return result


@router.post("/sync/dropstab/v2")
async def sync_dropstab_v2():
    """
    Run production Dropstab scraper v2.
    Dynamic dataset finder - resilient to structure changes.
    
    Returns: coins, unlocks, funding, investors
    """
    from ..dropstab.scraper_v2 import dropstab_scraper_v2
    result = await dropstab_scraper_v2.scrape_all()
    # Remove raw data from response to keep it small
    summary = {
        "ts": result["ts"],
        "source": result["source"],
        "elapsed_sec": result["elapsed_sec"],
        "summary": result["summary"]
    }
    return summary


@router.post("/sync/dropstab/v2/{entity}")
async def sync_dropstab_v2_entity(entity: str):
    """
    Scrape specific entity using v2 scraper.
    
    Entities: coins, unlocks, funding, investors
    """
    from ..dropstab.scraper_v2 import dropstab_scraper_v2
    
    if entity == "coins":
        data = await dropstab_scraper_v2.scrape_coins()
    elif entity == "unlocks":
        data = await dropstab_scraper_v2.scrape_unlocks()
    elif entity == "funding":
        data = await dropstab_scraper_v2.scrape_funding()
    elif entity == "investors":
        data = await dropstab_scraper_v2.scrape_investors()
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown entity: {entity}. Available: coins, unlocks, funding, investors"
        )
    
    return {
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        "source": "dropstab_v2",
        "entity": entity,
        "count": len(data),
        "data": data[:10] if data else []  # Sample only
    }


@router.post("/sync/dropstab/{entity}")
async def sync_dropstab_entity(
    entity: str,
    limit: int = Query(100, ge=1, le=500),
    max_pages: int = Query(10, ge=1, le=200),
    sync = Depends(get_dropstab_sync)
):
    """
    Sync specific entity from Dropstab
    
    Entities:
    - markets: price, mcap, fdv, volume (every 10 min)
    - markets_full: ALL coins with pagination (~15000+, daily)
    - projects: all projects ~15k (daily)
    - unlocks: token unlock events (hourly)
    - categories: AI, DePIN, GameFi, etc (daily)
    - narratives: market narratives (daily)
    - ecosystems: Ethereum, Solana, etc (daily)
    - trending: trending tokens (every 5 min)
    - gainers: top gainers (every 5 min)
    - losers: top losers (every 5 min)
    - listings: exchange listings (hourly)
    - market_overview: global market data (every 10 min)
    """
    if entity == 'markets':
        result = await sync.sync_markets(limit=limit, max_pages=max_pages)
    elif entity == 'markets_full':
        # Full market sync - all coins with pagination
        result = await sync.sync_markets_full(max_pages=200)
    elif entity == 'projects':
        result = await sync.sync_projects(limit=limit, max_pages=max_pages)
    elif entity == 'unlocks':
        result = await sync.sync_unlock_events(limit=limit, max_pages=max_pages)
    elif entity == 'categories':
        result = await sync.sync_categories()
    elif entity == 'narratives':
        result = await sync.sync_narratives()
    elif entity == 'ecosystems':
        result = await sync.sync_ecosystems()
    elif entity == 'trending':
        result = await sync.sync_trending()
    elif entity == 'gainers':
        result = await sync.sync_gainers()
    elif entity == 'losers':
        result = await sync.sync_losers()
    elif entity == 'listings':
        result = await sync.sync_listings(limit=limit, max_pages=max_pages)
    elif entity == 'market_overview':
        result = await sync.sync_market_overview()
    else:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown entity: {entity}. Available: markets, projects, unlocks, categories, narratives, ecosystems, trending, gainers, losers, listings, market_overview"
        )
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': 'dropstab',
        'entity': entity,
        **result
    }


# ═══════════════════════════════════════════════════════════════
# COINGECKO SYNC ENDPOINTS
# ═══════════════════════════════════════════════════════════════

def get_coingecko_sync():
    """Dependency to get CoinGecko sync service"""
    from server import db
    from ..sources.coingecko.sync import CoinGeckoSync
    return CoinGeckoSync(db)


@router.post("/sync/coingecko")
async def sync_coingecko_all(sync = Depends(get_coingecko_sync)):
    """
    Run full CoinGecko sync (global, categories, trending, top coins)
    """
    result = await sync.sync_all()
    return result


@router.post("/sync/coingecko/{entity}")
async def sync_coingecko_entity(
    entity: str,
    limit: int = Query(100, ge=1, le=250),
    page: int = Query(1, ge=1),
    max_pages: int = Query(10, ge=1, le=100),
    sync = Depends(get_coingecko_sync)
):
    """
    Sync specific entity from CoinGecko
    
    Entities:
    - global: Global market data (BTC dominance, total mcap)
    - categories: All categories with market data
    - trending: Trending coins
    - top_coins: Top coins by market cap (single page)
    - markets: Markets with pagination (limit per page)
    - markets_full: FULL market sync (~15000 coins, slow!)
    """
    if entity == 'global':
        result = await sync.sync_global_market()
    elif entity == 'categories':
        result = await sync.sync_categories()
    elif entity == 'trending':
        result = await sync.sync_trending()
    elif entity == 'top_coins':
        result = await sync.sync_top_coins(limit=limit)
    elif entity == 'markets':
        result = await sync.sync_top_coins(limit=limit)
    elif entity == 'markets_full':
        # Full market sync - all coins (~15000)
        result = await sync.sync_markets_full(max_pages=max_pages)
    else:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown entity: {entity}. Available: global, categories, trending, top_coins, markets, markets_full"
        )
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': 'coingecko',
        'entity': entity,
        **result
    }


@router.get("/sync/coingecko/status")
async def coingecko_status(sync = Depends(get_coingecko_sync)):
    """Check CoinGecko API pool status"""
    pool_status = sync.get_pool_status()
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': 'coingecko',
        'type': 'api',
        'ready': True,
        'pool': pool_status
    }



# ═══════════════════════════════════════════════════════════════
# CRYPTORANK STATUS
# ═══════════════════════════════════════════════════════════════

@router.get("/sync/cryptorank/status")
async def cryptorank_status():
    """
    Check CryptoRank scraper status.
    CryptoRank is a scraper source - POST JSON data to /ingest/cryptorank/{entity}
    """
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': 'cryptorank',
        'type': 'scraper',
        'ready': True,
        'message': 'CryptoRank is a scraper source. Use POST /api/intel/ingest/cryptorank/{entity} to ingest data.',
        'endpoints': {
            'ingest_all': 'POST /api/intel/ingest/cryptorank',
            'ingest_entity': 'POST /api/intel/ingest/cryptorank/{entity}',
            'status': 'GET /api/intel/ingest/cryptorank/status'
        }
    }


# ═══════════════════════════════════════════════════════════════
# CRYPTORANK INGEST ENDPOINTS (POST JSON data)
# ═══════════════════════════════════════════════════════════════

@router.post("/ingest/cryptorank")
async def ingest_cryptorank_all(
    request: Request,
    sync = Depends(get_cryptorank_sync)
):
    """
    Ingest all CryptoRank data at once.
    
    Body format:
    {
        "categories": [...],
        "funding": {"total": ..., "data": [...]},
        "investors": [...],
        "unlocks": [...],
        "tge_unlocks": [...],
        "unlock_totals": [...],
        "launchpads": [...],
        "market": {...}
    }
    """
    data = await request.json()
    result = await sync.ingest_all(data)
    return result


@router.post("/ingest/cryptorank/{entity}")
async def ingest_cryptorank_entity(
    entity: str,
    request: Request,
    sync = Depends(get_cryptorank_sync)
):
    """
    Ingest specific entity data from CryptoRank.
    
    POST JSON data for the entity type.
    """
    data = await request.json()
    
    if entity == 'funding' or entity == 'fundraising':
        result = await sync.ingest_funding(data)
    elif entity == 'investors':
        result = await sync.ingest_investors(data)
    elif entity == 'unlocks':
        result = await sync.ingest_unlocks(data, 'vesting')
    elif entity == 'tge_unlocks':
        result = await sync.ingest_unlocks(data, 'tge')
    elif entity == 'unlock_totals':
        result = await sync.ingest_unlock_totals(data)
    elif entity == 'launchpads':
        result = await sync.ingest_launchpads(data)
    elif entity == 'categories':
        result = await sync.ingest_categories(data)
    elif entity == 'market':
        result = await sync.ingest_market(data)
    else:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown entity: {entity}. Available: funding, investors, unlocks, tge_unlocks, unlock_totals, launchpads, categories, market"
        )
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': 'cryptorank',
        'entity': entity,
        **result
    }


@router.get("/ingest/cryptorank/status")
async def cryptorank_ingest_status():
    """
    Check CryptoRank ingest status.
    """
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': 'cryptorank',
        'type': 'scraper',
        'ready': True,
        'message': 'CryptoRank ingest ready. POST JSON data to /ingest/cryptorank/{entity}',
        'entities': [
            'funding', 'investors', 'unlocks', 'tge_unlocks', 
            'unlock_totals', 'launchpads', 'categories', 'market'
        ]
    }


@router.get("/ingest/cryptorank/stats")
async def cryptorank_stats(sync = Depends(get_cryptorank_sync)):
    """
    Get CryptoRank sync statistics.
    Shows how many records from CryptoRank are in each collection.
    """
    return await sync.get_sync_stats()


@router.post("/ingest/cryptorank/funding/batch")
async def ingest_funding_batch(
    request: Request,
    sync = Depends(get_cryptorank_sync)
):
    """
    Ingest multiple pages of funding data at once.
    
    Body format:
    {
        "pages": [
            {"total": 10851, "data": [...]},
            {"total": 10851, "data": [...]},
            ...
        ]
    }
    
    Useful for incremental sync of multiple pages.
    """
    data = await request.json()
    pages = data.get('pages', [])
    
    if not pages:
        raise HTTPException(status_code=400, detail="No pages provided")
    
    result = await sync.ingest_funding_batch(pages)
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'source': 'cryptorank',
        **result
    }


# ═══════════════════════════════════════════════════════════════
# INVESTORS
# ═══════════════════════════════════════════════════════════════

@router.get("/investors")
async def list_investors(
    search: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db = Depends(get_db)
):
    """List investors/VCs"""
    query = {}
    if search:
        query['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'slug': {'$regex': search, '$options': 'i'}}
        ]
    if tier:
        query['tier'] = tier
    
    cursor = db.intel_investors.find(query, {'_id': 0, 'raw': 0})
    items = await cursor.sort('investments_count', -1).skip(offset).limit(limit).to_list(limit)
    total = await db.intel_investors.count_documents(query)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'total': total,
        'items': items
    }


# ═══════════════════════════════════════════════════════════════
# UNLOCKS
# ═══════════════════════════════════════════════════════════════

@router.get("/unlocks")
async def list_unlocks(
    symbol: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db = Depends(get_db)
):
    """List token unlocks"""
    query = {}
    if symbol:
        query['symbol'] = symbol.upper()
    if category:
        query['category'] = category.lower()
    
    cursor = db.intel_unlocks.find(query, {'_id': 0, 'raw': 0})
    items = await cursor.sort('unlock_date', 1).limit(limit).to_list(limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(items),
        'items': items
    }


@router.get("/unlocks/upcoming")
async def upcoming_unlocks(
    days: int = Query(30, ge=1, le=180),
    min_percent: Optional[float] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db = Depends(get_db)
):
    """Get upcoming token unlocks"""
    now = int(datetime.now(timezone.utc).timestamp())
    end = now + (days * 86400)
    
    query = {
        'unlock_date': {'$gte': now, '$lte': end}
    }
    if min_percent:
        query['unlock_percent'] = {'$gte': min_percent}
    
    cursor = db.intel_unlocks.find(query, {'_id': 0, 'raw': 0})
    items = await cursor.sort('unlock_date', 1).limit(limit).to_list(limit)
    
    # Add days_until
    for item in items:
        item['days_until'] = (item['unlock_date'] - now) // 86400
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'days': days,
        'count': len(items),
        'items': items
    }


# ═══════════════════════════════════════════════════════════════
# FUNDRAISING
# ═══════════════════════════════════════════════════════════════

@router.get("/fundraising")
async def list_fundraising(
    symbol: Optional[str] = Query(None),
    round: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db = Depends(get_db)
):
    """List funding rounds"""
    query = {}
    if symbol:
        query['symbol'] = symbol.upper()
    if round:
        query['round'] = {'$regex': round, '$options': 'i'}
    
    cursor = db.intel_fundraising.find(query, {'_id': 0, 'raw': 0})
    items = await cursor.sort('date', -1).limit(limit).to_list(limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(items),
        'items': items
    }


@router.get("/fundraising/recent")
async def recent_fundraising(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    db = Depends(get_db)
):
    """Get recent funding rounds"""
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    
    query = {'date': {'$gte': cutoff}}
    
    cursor = db.intel_fundraising.find(query, {'_id': 0, 'raw': 0})
    items = await cursor.sort('date', -1).limit(limit).to_list(limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'days': days,
        'count': len(items),
        'items': items
    }


# ═══════════════════════════════════════════════════════════════
# PROJECTS
# ═══════════════════════════════════════════════════════════════

@router.get("/projects")
async def list_projects(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db = Depends(get_db)
):
    """List projects"""
    query = {}
    if search:
        query['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'symbol': {'$regex': search, '$options': 'i'}}
        ]
    if category:
        query['category'] = {'$regex': category, '$options': 'i'}
    
    cursor = db.intel_projects.find(query, {'_id': 0, 'raw': 0})
    items = await cursor.sort('symbol', 1).skip(offset).limit(limit).to_list(limit)
    total = await db.intel_projects.count_documents(query)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'total': total,
        'items': items
    }


@router.get("/projects/discovered")
async def discovered_projects(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    db = Depends(get_db)
):
    """Get recently discovered/launched projects"""
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    
    query = {
        '$or': [
            {'ico_date': {'$gte': cutoff}},
            {'listing_date': {'$gte': cutoff}}
        ]
    }
    
    cursor = db.intel_projects.find(query, {'_id': 0, 'raw': 0})
    items = await cursor.limit(limit).to_list(limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'days': days,
        'count': len(items),
        'items': items
    }


# ═══════════════════════════════════════════════════════════════
# ACTIVITY
# ═══════════════════════════════════════════════════════════════

@router.get("/activity")
async def list_activity(
    activity_type: Optional[str] = Query(None, alias='type'),
    project: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db = Depends(get_db)
):
    """List activity/news feed"""
    query = {}
    if activity_type:
        query['type'] = activity_type.lower()
    if project:
        query['projects'] = {'$in': [project.upper()]}
    
    cursor = db.intel_activity.find(query, {'_id': 0, 'raw': 0})
    items = await cursor.sort('date', -1).limit(limit).to_list(limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(items),
        'items': items
    }


# ═══════════════════════════════════════════════════════════════
# MODERATION QUEUE
# ═══════════════════════════════════════════════════════════════

@router.get("/moderation")
async def get_moderation_queue(
    entity: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    status: str = Query('pending'),
    limit: int = Query(100, ge=1, le=500),
    db = Depends(get_db)
):
    """Get moderation queue items"""
    query = {'status': status}
    if entity:
        query['entity'] = entity
    if source:
        query['source'] = source
    
    cursor = db.moderation_queue.find(query, {'_id': 0})
    items = await cursor.sort('created_at', -1).limit(limit).to_list(limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(items),
        'items': items
    }


@router.post("/moderation/{key}/approve")
async def approve_moderation(
    key: str,
    db = Depends(get_db)
):
    """Approve moderation item"""
    result = await db.moderation_queue.update_one(
        {'key': key},
        {'$set': {'status': 'approved', 'updated_at': datetime.now(timezone.utc)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {'ok': True, 'key': key, 'status': 'approved'}


@router.post("/moderation/{key}/reject")
async def reject_moderation(
    key: str,
    db = Depends(get_db)
):
    """Reject moderation item"""
    result = await db.moderation_queue.update_one(
        {'key': key},
        {'$set': {'status': 'rejected', 'updated_at': datetime.now(timezone.utc)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {'ok': True, 'key': key, 'status': 'rejected'}


# ═══════════════════════════════════════════════════════════════
# LAUNCHPADS
# ═══════════════════════════════════════════════════════════════

@router.get("/launchpads")
async def list_launchpads(
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db = Depends(get_db)
):
    """List launchpad platforms"""
    query = {}
    if search:
        query['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'slug': {'$regex': search, '$options': 'i'}}
        ]
    
    cursor = db.intel_launchpads.find(query, {'_id': 0, 'raw': 0})
    items = await cursor.sort('projects_count', -1).limit(limit).to_list(limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(items),
        'items': items
    }


# ═══════════════════════════════════════════════════════════════
# CATEGORIES
# ═══════════════════════════════════════════════════════════════

@router.get("/categories")
async def list_categories(
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db = Depends(get_db)
):
    """List crypto categories"""
    query = {}
    if search:
        query['name'] = {'$regex': search, '$options': 'i'}
    
    cursor = db.intel_categories.find(query, {'_id': 0, 'raw': 0})
    items = await cursor.sort('coins_count', -1).limit(limit).to_list(limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(items),
        'items': items
    }


# ═══════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════

@router.get("/stats")
async def intel_stats(db = Depends(get_db)):
    """Get intel layer statistics"""
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'collections': {
            'investors': await db.intel_investors.count_documents({}),
            'unlocks': await db.intel_unlocks.count_documents({}),
            'fundraising': await db.intel_fundraising.count_documents({}),
            'projects': await db.intel_projects.count_documents({}),
            'activity': await db.intel_activity.count_documents({}),
            'launchpads': await db.intel_launchpads.count_documents({}),
            'categories': await db.intel_categories.count_documents({}),
        },
        'moderation_pending': await db.moderation_queue.count_documents({'status': 'pending'})
    }



# ═══════════════════════════════════════════════════════════════
# ENTITIES
# ═══════════════════════════════════════════════════════════════

@router.get("/entities")
async def list_entities(
    entity_type: Optional[str] = Query(None, alias='type'),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db = Depends(get_db)
):
    """List canonical entities"""
    query = {}
    if entity_type:
        query['type'] = entity_type
    if search:
        query['$or'] = [
            {'symbol': {'$regex': search, '$options': 'i'}},
            {'name': {'$regex': search, '$options': 'i'}},
            {'aliases': {'$regex': search, '$options': 'i'}}
        ]
    
    cursor = db.entities.find(query, {'_id': 0})
    items = await cursor.limit(limit).to_list(limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(items),
        'items': items
    }


@router.get("/entities/{entity_id}/relations")
async def get_entity_relations(
    entity_id: str,
    relation_type: Optional[str] = Query(None, alias='type'),
    db = Depends(get_db)
):
    """Get relations for an entity"""
    query = {
        '$or': [
            {'from_entity': entity_id},
            {'to_entity': entity_id}
        ]
    }
    if relation_type:
        query['type'] = relation_type
    
    cursor = db.entity_relations.find(query, {'_id': 0})
    items = await cursor.to_list(100)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'entity_id': entity_id,
        'count': len(items),
        'relations': items
    }


# ═══════════════════════════════════════════════════════════════
# DATA SOURCES & HEALTH
# ═══════════════════════════════════════════════════════════════

@router.get("/sources")
async def list_sources(
    status: Optional[str] = Query(None),
    db = Depends(get_db)
):
    """List all data sources"""
    query = {}
    if status:
        query['status'] = status
    
    cursor = db.data_sources.find(query, {'_id': 0})
    sources = await cursor.sort('priority', 1).to_list(100)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(sources),
        'sources': sources
    }


@router.post("/sources/{name}/status")
async def set_source_status(
    name: str,
    status: str = Query(..., description="active, paused, disabled"),
    db = Depends(get_db)
):
    """Set source status"""
    result = await db.data_sources.update_one(
        {'name': name},
        {'$set': {'status': status, 'updated_at': datetime.now(timezone.utc)}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Source not found")
    
    return {'ok': True, 'source': name, 'status': status}


# ═══════════════════════════════════════════════════════════════
# AGGREGATED DATA (Multi-source merge)
# ═══════════════════════════════════════════════════════════════

def get_aggregator():
    """Dependency to get data aggregator"""
    from server import db
    from ..services.data_aggregator import create_data_aggregator
    return create_data_aggregator(db)


@router.get("/aggregated/project/{symbol}")
async def get_aggregated_project(
    symbol: str,
    aggregator = Depends(get_aggregator)
):
    """
    Get project data aggregated from all sources.
    Merges Dropstab, CryptoRank, CoinGecko based on field priority.
    """
    project = await aggregator.get_project(symbol)
    
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {symbol}")
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'project': project
    }


@router.get("/aggregated/investor/{slug}")
async def get_aggregated_investor(
    slug: str,
    aggregator = Depends(get_aggregator)
):
    """Get investor data aggregated from all sources"""
    investor = await aggregator.get_investor(slug)
    
    if not investor:
        raise HTTPException(status_code=404, detail=f"Investor not found: {slug}")
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'investor': investor
    }


@router.get("/aggregated/market")
async def get_aggregated_market(aggregator = Depends(get_aggregator)):
    """Get global market data aggregated from all sources"""
    market = await aggregator.get_global_market()
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'market': market
    }


@router.get("/aggregated/search")
async def search_aggregated_projects(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    aggregator = Depends(get_aggregator)
):
    """Search and return aggregated project data"""
    results = await aggregator.search_projects(q, limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'query': q,
        'count': len(results),
        'results': results
    }


@router.get("/health")
async def get_system_health(db = Depends(get_db)):
    """Get overall system health"""
    # Scraper health
    scraper_health = await db.scraper_health.find({}, {'_id': 0}).to_list(100)
    
    # Source health
    source_health = await db.data_source_health.find({}, {'_id': 0}).to_list(100)
    
    # Recent errors
    recent_errors = await db.scraper_errors.find(
        {},
        {'_id': 0}
    ).sort('timestamp', -1).limit(10).to_list(10)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'scrapers': scraper_health,
        'sources': source_health,
        'recent_errors': recent_errors
    }


@router.get("/health/scrapers")
async def get_scraper_health(db = Depends(get_db)):
    """Get scraper health status"""
    cursor = db.scraper_health.find({}, {'_id': 0})
    items = await cursor.to_list(100)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'scrapers': items
    }


# ═══════════════════════════════════════════════════════════════
# FOMO MOMENTUM INDEX (FMI) - Branded Trend Detection
# ═══════════════════════════════════════════════════════════════

def get_fmi_calculator():
    """Dependency to get FMI calculator"""
    from server import db
    from ..services.fomo_momentum import create_fmi_calculator
    return create_fmi_calculator(db)


@router.get("/fomo-momentum")
async def get_fmi_list(
    state: Optional[str] = Query(None, description="Filter by state: CALM, BUILDING, TRENDING, FOMO"),
    min_fmi: Optional[float] = Query(None, ge=0, le=100, description="Minimum FMI score"),
    sector: Optional[str] = Query(None, description="Filter by sector"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    calculator = Depends(get_fmi_calculator)
):
    """
    Get FOMO Momentum Index for all tokens
    
    FMI States:
    - CALM (0-40): Low momentum
    - BUILDING (40-60): Building momentum  
    - TRENDING (60-80): Trending
    - FOMO (80-100): FOMO Zone 🔥
    
    Returns pre-computed FMI scores (updated every 5 min)
    """
    items = await calculator.get_all_fmi(
        state=state,
        min_fmi=min_fmi,
        sector=sector,
        limit=limit,
        offset=offset
    )
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(items),
        'data': items
    }


@router.get("/fomo-momentum/trending")
async def get_fmi_trending(
    limit: int = Query(20, ge=1, le=100),
    calculator = Depends(get_fmi_calculator)
):
    """
    Get trending tokens (FMI >= 60)
    
    Quick endpoint for tokens currently trending
    """
    items = await calculator.get_trending(limit=limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(items),
        'data': items
    }


@router.get("/fomo-momentum/fomo-zone")
async def get_fmi_fomo_zone(
    limit: int = Query(10, ge=1, le=50),
    calculator = Depends(get_fmi_calculator)
):
    """
    Get tokens in FOMO Zone (FMI >= 80) 🔥
    
    These are the hottest tokens right now
    """
    items = await calculator.get_fomo_zone(limit=limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'count': len(items),
        'data': items
    }


@router.get("/fomo-momentum/stats")
async def get_fmi_stats(calculator = Depends(get_fmi_calculator)):
    """
    Get FMI statistics
    
    - Total tokens computed
    - Distribution by state
    - Top sectors by average FMI
    """
    stats = await calculator.get_stats()
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        **stats
    }


@router.get("/fomo-momentum/{symbol}")
async def get_fmi_single(
    symbol: str,
    calculator = Depends(get_fmi_calculator)
):
    """
    Get FOMO Momentum Index for specific token
    
    Full response with all components:
    - Volume Spike (40% weight)
    - Liquidity Inflow (30% weight)
    - Narrative Growth (20% weight)
    - Listing Signal (10% weight)
    
    Plus signals array: VOLUME_ANOMALY, LIQUIDITY_SURGE, SECTOR_MOMENTUM, CEX_LISTING
    """
    fmi = await calculator.get_fmi(symbol)
    
    if not fmi:
        # Try to calculate on-the-fly
        fmi = await calculator.calculate_fmi(symbol)
        
        if not fmi:
            raise HTTPException(
                status_code=404, 
                detail=f"FMI not found for {symbol.upper()}. Project may not exist or have insufficient data."
            )
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        **fmi
    }


@router.post("/fomo-momentum/compute")
async def compute_fmi(
    limit: int = Query(500, ge=1, le=5000, description="Max projects to compute"),
    calculator = Depends(get_fmi_calculator)
):
    """
    Trigger FMI pre-computation
    
    Computes FMI for all projects with volume data.
    Usually run via scheduler every 5 minutes.
    """
    result = await calculator.compute_all(limit=limit)
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'ok': True,
        **result
    }


@router.post("/fomo-momentum/{symbol}/calculate")
async def calculate_fmi_single(
    symbol: str,
    calculator = Depends(get_fmi_calculator)
):
    """
    Calculate and store FMI for specific token
    
    Forces fresh calculation regardless of cache
    """
    fmi = await calculator.calculate_fmi(symbol)
    
    if not fmi:
        raise HTTPException(
            status_code=404,
            detail=f"Cannot calculate FMI for {symbol.upper()}. Project not found or insufficient data."
        )
    
    # Store result
    from server import db
    await db.fomo_momentum.update_one(
        {'symbol': symbol.upper()},
        {'$set': fmi},
        upsert=True
    )
    
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'ok': True,
        **fmi
    }



# ═══════════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════════════════════════

def get_scheduler():
    """Get scheduler instance"""
    from server import db
    from ..engine.intel_scheduler import get_intel_scheduler
    return get_intel_scheduler(db)


@router.get("/scheduler/status")
async def scheduler_status():
    """Get scheduler status"""
    scheduler = get_scheduler()
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        **scheduler.status()
    }


@router.post("/scheduler/start")
async def start_scheduler(
    enable_dropstab: bool = Query(True),
    enable_cryptorank: bool = Query(True)
):
    """Start the Intel sync scheduler"""
    scheduler = get_scheduler()
    await scheduler.start(enable_dropstab, enable_cryptorank)
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'ok': True,
        **scheduler.status()
    }


@router.post("/scheduler/stop")
async def stop_scheduler():
    """Stop the Intel sync scheduler"""
    scheduler = get_scheduler()
    await scheduler.stop()
    return {
        'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
        'ok': True,
        **scheduler.status()
    }
