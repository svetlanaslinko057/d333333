"""
Source Manager - Manages data sources
Controls source status, priority, health monitoring
"""

import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class SourceManager:
    """
    Manages all data sources.
    - Source registration
    - Status control (active/paused/disabled)
    - Priority management
    - Health monitoring
    """
    
    def __init__(self, db):
        self.db = db
        self.sources = db.data_sources
        self.health = db.data_source_health
    
    async def register_source(
        self,
        name: str,
        source_type: str = 'scraper',
        endpoints: List[str] = None,
        rate_limit: int = 2,
        priority: int = 1,
        interval_hours: int = 6
    ):
        """Register a new data source."""
        doc = {
            'name': name,
            'type': source_type,
            'status': 'active',
            'priority': priority,
            'interval_hours': interval_hours,
            'endpoints': endpoints or [],
            'rate_limit': rate_limit,
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
        
        await self.sources.update_one(
            {'name': name},
            {'$set': doc},
            upsert=True
        )
        
        logger.info(f"[SourceManager] Registered source: {name}")
    
    async def get_source(self, name: str) -> Optional[Dict]:
        """Get source by name."""
        return await self.sources.find_one({'name': name}, {'_id': 0})
    
    async def list_sources(self, status: Optional[str] = None) -> List[Dict]:
        """List all sources."""
        query = {}
        if status:
            query['status'] = status
        
        cursor = self.sources.find(query, {'_id': 0})
        return await cursor.sort('priority', 1).to_list(100)
    
    async def set_status(self, name: str, status: str):
        """Set source status: active, paused, disabled."""
        await self.sources.update_one(
            {'name': name},
            {
                '$set': {
                    'status': status,
                    'updated_at': datetime.now(timezone.utc)
                }
            }
        )
        logger.info(f"[SourceManager] {name} status -> {status}")
    
    async def is_active(self, name: str) -> bool:
        """Check if source is active."""
        source = await self.get_source(name)
        return source and source.get('status') == 'active'
    
    async def update_health(
        self,
        name: str,
        status: str,
        fetched: int = 0,
        saved: int = 0,
        duration: float = 0,
        error: Optional[str] = None
    ):
        """Update source health status."""
        doc = {
            'source': name,
            'last_run': datetime.now(timezone.utc),
            'status': status,
            'fetched': fetched,
            'saved': saved,
            'duration': duration,
            'error': error
        }
        
        await self.health.update_one(
            {'source': name},
            {'$set': doc},
            upsert=True
        )
    
    async def get_health(self, name: str) -> Optional[Dict]:
        """Get source health."""
        return await self.health.find_one({'source': name}, {'_id': 0})
    
    async def get_all_health(self) -> List[Dict]:
        """Get health for all sources."""
        cursor = self.health.find({}, {'_id': 0})
        return await cursor.to_list(100)
    
    async def get_unhealthy_sources(self, max_age_hours: int = 12) -> List[Dict]:
        """Get sources that haven't run recently or have errors."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        
        cursor = self.health.find({
            '$or': [
                {'status': {'$ne': 'ok'}},
                {'last_run': {'$lt': cutoff}}
            ]
        }, {'_id': 0})
        
        return await cursor.to_list(100)
    
    async def get_priority_for_entity(self, entity_type: str) -> List[str]:
        """
        Get sources in priority order for an entity type.
        Used for data conflict resolution.
        """
        sources = await self.list_sources(status='active')
        
        # Filter by endpoint support
        relevant = [
            s for s in sources
            if entity_type in s.get('endpoints', []) or not s.get('endpoints')
        ]
        
        # Sort by priority
        relevant.sort(key=lambda x: x.get('priority', 99))
        
        return [s['name'] for s in relevant]


# Factory
def create_source_manager(db):
    return SourceManager(db)
