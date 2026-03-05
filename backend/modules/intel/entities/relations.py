"""
Relationship Builder - Creates entity relationships

Relationship types:
- invested: fund -> project
- founded: person -> project  
- advised: person -> project
- partner: project -> project
"""

import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class RelationshipBuilder:
    """
    Builds and queries relationships between entities.
    """
    
    def __init__(self, db):
        self.db = db
        self.relations = db.entity_relations
    
    async def create_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        source: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Create or update relationship between entities.
        """
        key = f"{from_entity}:{relation_type}:{to_entity}"
        
        doc = {
            'key': key,
            'from_entity': from_entity,
            'to_entity': to_entity,
            'type': relation_type,
            'source': source,
            'metadata': metadata or {},
            'updated_at': datetime.now(timezone.utc)
        }
        
        result = await self.relations.update_one(
            {'key': key},
            {
                '$set': doc,
                '$setOnInsert': {'created_at': datetime.now(timezone.utc)}
            },
            upsert=True
        )
        
        return key
    
    async def add_investment(
        self,
        investor_entity: str,
        project_entity: str,
        amount: Optional[float] = None,
        round_name: Optional[str] = None,
        date: Optional[int] = None,
        source: str = 'unknown'
    ) -> str:
        """
        Create investment relationship.
        """
        return await self.create_relation(
            from_entity=investor_entity,
            to_entity=project_entity,
            relation_type='invested',
            source=source,
            metadata={
                'amount': amount,
                'round': round_name,
                'date': date
            }
        )
    
    async def get_relations(
        self,
        entity_id: str,
        direction: str = 'both',  # 'from', 'to', 'both'
        relation_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Get all relations for an entity.
        """
        query = {}
        
        if direction == 'from':
            query['from_entity'] = entity_id
        elif direction == 'to':
            query['to_entity'] = entity_id
        else:
            query['$or'] = [
                {'from_entity': entity_id},
                {'to_entity': entity_id}
            ]
        
        if relation_type:
            query['type'] = relation_type
        
        cursor = self.relations.find(query, {'_id': 0})
        return await cursor.to_list(100)
    
    async def get_investors(self, project_entity: str) -> List[Dict]:
        """Get all investors of a project."""
        return await self.get_relations(
            entity_id=project_entity,
            direction='to',
            relation_type='invested'
        )
    
    async def get_portfolio(self, investor_entity: str) -> List[Dict]:
        """Get all investments of an investor."""
        return await self.get_relations(
            entity_id=investor_entity,
            direction='from',
            relation_type='invested'
        )


# Factory
def create_relationship_builder(db):
    return RelationshipBuilder(db)
