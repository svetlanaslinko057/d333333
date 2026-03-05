"""
Entity Resolver - Normalizes entities across sources

Merges different names into canonical entities:
- ARB, Arbitrum, Arbitrum Token -> entity_arbitrum
"""

import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
import re

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Resolves and normalizes entities from different sources.
    Creates canonical entities with aliases.
    """
    
    def __init__(self, db):
        self.db = db
        self.entities = db.entities
    
    async def resolve_project(
        self,
        symbol: str,
        name: str,
        source: str,
        source_id: Optional[str] = None
    ) -> str:
        """
        Resolve project to canonical entity.
        Returns entity_id.
        """
        symbol = symbol.upper().strip() if symbol else ''
        name = name.strip() if name else symbol
        
        # Try to find existing entity
        entity = await self._find_entity('project', symbol, name)
        
        if entity:
            # Update source mapping
            await self._add_source_mapping(entity['_id'], source, source_id or symbol.lower())
            return str(entity['_id'])
        
        # Create new entity
        entity_id = await self._create_entity(
            entity_type='project',
            symbol=symbol,
            name=name,
            source=source,
            source_id=source_id
        )
        
        return entity_id
    
    async def resolve_investor(
        self,
        name: str,
        source: str,
        source_id: Optional[str] = None
    ) -> str:
        """
        Resolve investor/fund to canonical entity.
        """
        name = name.strip() if name else ''
        slug = self._slugify(name)
        
        # Try to find existing
        entity = await self.entities.find_one({
            'type': 'investor',
            '$or': [
                {'slug': slug},
                {'aliases': {'$in': [name, slug]}}
            ]
        })
        
        if entity:
            await self._add_source_mapping(entity['_id'], source, source_id or slug)
            return str(entity['_id'])
        
        # Create new
        entity_id = await self._create_entity(
            entity_type='investor',
            symbol=None,
            name=name,
            source=source,
            source_id=source_id
        )
        
        return entity_id
    
    async def _find_entity(
        self,
        entity_type: str,
        symbol: str,
        name: str
    ) -> Optional[Dict]:
        """Find existing entity by symbol or name."""
        query = {
            'type': entity_type,
            '$or': [
                {'symbol': symbol},
                {'name': name},
                {'aliases': {'$in': [symbol, name, name.lower()]}}
            ]
        }
        
        return await self.entities.find_one(query)
    
    async def _create_entity(
        self,
        entity_type: str,
        symbol: Optional[str],
        name: str,
        source: str,
        source_id: Optional[str]
    ) -> str:
        """Create new canonical entity."""
        slug = self._slugify(symbol or name)
        
        doc = {
            'type': entity_type,
            'symbol': symbol,
            'name': name,
            'slug': slug,
            'aliases': [name],
            'sources': {source: source_id or slug},
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
        
        if symbol and symbol != name:
            doc['aliases'].append(symbol)
        
        result = await self.entities.insert_one(doc)
        
        logger.info(f"[Resolver] Created entity: {entity_type}/{slug}")
        
        return str(result.inserted_id)
    
    async def _add_source_mapping(
        self,
        entity_id,
        source: str,
        source_id: str
    ):
        """Add source mapping to entity."""
        await self.entities.update_one(
            {'_id': entity_id},
            {
                '$set': {
                    f'sources.{source}': source_id,
                    'updated_at': datetime.now(timezone.utc)
                }
            }
        )
    
    async def add_alias(self, entity_id: str, alias: str):
        """Add alias to entity."""
        from bson import ObjectId
        await self.entities.update_one(
            {'_id': ObjectId(entity_id)},
            {'$addToSet': {'aliases': alias}}
        )
    
    async def get_entity(self, entity_id: str) -> Optional[Dict]:
        """Get entity by ID."""
        from bson import ObjectId
        doc = await self.entities.find_one({'_id': ObjectId(entity_id)})
        if doc:
            doc['_id'] = str(doc['_id'])
        return doc
    
    async def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """Search entities by name/symbol."""
        filter_query = {
            '$or': [
                {'symbol': {'$regex': query, '$options': 'i'}},
                {'name': {'$regex': query, '$options': 'i'}},
                {'aliases': {'$regex': query, '$options': 'i'}}
            ]
        }
        
        if entity_type:
            filter_query['type'] = entity_type
        
        cursor = self.entities.find(filter_query, {'_id': 0}).limit(limit)
        return await cursor.to_list(limit)
    
    def _slugify(self, text: str) -> str:
        """Convert text to slug."""
        if not text:
            return ''
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9]+', '-', text)
        return text.strip('-')


# Factory
def create_resolver(db):
    return EntityResolver(db)
