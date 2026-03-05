"""
Base Scraper - Universal scraper template
"""

import time
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Abstract base class for all scrapers.
    Provides: retry, rate limiting, error handling, metrics.
    """
    
    # Override in subclass
    name: str = "base"
    source: str = "unknown"
    entity_type: str = "unknown"  # project, unlock, fundraising, investor, activity
    interval_hours: int = 6
    priority: int = 1
    
    def __init__(self, db):
        self.db = db
        self._last_run = 0
        self._errors = 0
    
    @abstractmethod
    async def fetch(self) -> List[Dict]:
        """Fetch raw data from source. Override in subclass."""
        pass
    
    @abstractmethod
    def parse(self, raw: List[Dict]) -> List[Dict]:
        """Parse and normalize data. Override in subclass."""
        pass
    
    async def save(self, data: List[Dict]) -> int:
        """Save parsed data to MongoDB with deduplication."""
        if not data:
            return 0
        
        collection = self.db[f"intel_{self.entity_type}s"]
        saved = 0
        
        for doc in data:
            key = doc.get('key')
            if not key:
                continue
            
            # Check for changes
            existing = await collection.find_one({'key': key})
            
            if not existing:
                doc['created_at'] = datetime.now(timezone.utc)
                doc['updated_at'] = datetime.now(timezone.utc)
                await collection.insert_one(doc)
                saved += 1
                
                # Add to moderation queue
                await self._add_to_moderation(doc, 'new')
            else:
                # Update if changed
                doc['updated_at'] = datetime.now(timezone.utc)
                await collection.update_one({'key': key}, {'$set': doc})
        
        return saved
    
    async def _add_to_moderation(self, doc: Dict, change_type: str):
        """Add item to moderation queue."""
        await self.db.moderation_queue.insert_one({
            'source': self.source,
            'entity': self.entity_type,
            'key': doc.get('key'),
            'payload': doc,
            'change_type': change_type,
            'status': 'pending',
            'created_at': datetime.now(timezone.utc)
        })
    
    async def run(self) -> Dict[str, Any]:
        """Execute full scraper pipeline."""
        start = time.time()
        result = {
            'scraper': self.name,
            'source': self.source,
            'entity': self.entity_type,
            'status': 'ok',
            'fetched': 0,
            'saved': 0,
            'duration': 0,
            'errors': []
        }
        
        try:
            # Fetch
            raw = await self.fetch()
            result['fetched'] = len(raw) if raw else 0
            
            if not raw:
                result['status'] = 'empty'
                return result
            
            # Parse
            parsed = self.parse(raw)
            
            # Save
            saved = await self.save(parsed)
            result['saved'] = saved
            
            # Update health
            await self._update_health(result)
            
        except Exception as e:
            result['status'] = 'error'
            result['errors'].append(str(e))
            logger.error(f"[{self.name}] Error: {e}")
            await self._log_error(str(e))
        
        result['duration'] = round(time.time() - start, 2)
        self._last_run = time.time()
        
        logger.info(f"[{self.name}] {result['status']}: fetched={result['fetched']}, saved={result['saved']}, duration={result['duration']}s")
        
        return result
    
    async def _update_health(self, result: Dict):
        """Update scraper health status."""
        await self.db.scraper_health.update_one(
            {'scraper': self.name},
            {'$set': {
                'scraper': self.name,
                'source': self.source,
                'entity': self.entity_type,
                'last_run': datetime.now(timezone.utc),
                'status': result['status'],
                'fetched': result['fetched'],
                'saved': result['saved'],
                'duration': result['duration']
            }},
            upsert=True
        )
    
    async def _log_error(self, error: str):
        """Log scraper error."""
        await self.db.scraper_errors.insert_one({
            'scraper': self.name,
            'source': self.source,
            'error': error,
            'timestamp': datetime.now(timezone.utc)
        })
