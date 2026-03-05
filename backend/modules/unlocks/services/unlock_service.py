"""
Unlock Service
Layer 2: Business logic for token unlocks
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid

from ..domain import Project, TokenUnlock, UnlockCategory, UnlockSummary

logger = logging.getLogger(__name__)


class UnlockService:
    """Service for managing projects and token unlocks"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.projects = db.projects
        self.unlocks = db.token_unlocks
    
    # ═══════════════════════════════════════════════════════════════
    # PROJECTS
    # ═══════════════════════════════════════════════════════════════
    
    async def create_project(self, project: Project) -> str:
        """Create or update project"""
        doc = project.dict()
        doc['updated_at'] = datetime.now(timezone.utc)
        
        await self.projects.update_one(
            {'id': project.id},
            {'$set': doc},
            upsert=True
        )
        return project.id
    
    async def get_project(self, project_id: str) -> Optional[Dict]:
        """Get project by ID"""
        doc = await self.projects.find_one({'id': project_id}, {'_id': 0})
        return doc
    
    async def get_project_by_symbol(self, symbol: str) -> Optional[Dict]:
        """Get project by symbol"""
        doc = await self.projects.find_one(
            {'symbol': symbol.upper()}, 
            {'_id': 0}
        )
        return doc
    
    async def list_projects(
        self,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None
    ) -> List[Dict]:
        """List all projects"""
        query = {}
        if search:
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'symbol': {'$regex': search, '$options': 'i'}}
            ]
        
        cursor = self.projects.find(query, {'_id': 0})
        cursor = cursor.sort('symbol', 1).skip(offset).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def count_projects(self) -> int:
        """Count total projects"""
        return await self.projects.count_documents({})
    
    # ═══════════════════════════════════════════════════════════════
    # UNLOCKS
    # ═══════════════════════════════════════════════════════════════
    
    async def create_unlock(self, unlock: TokenUnlock) -> str:
        """Create or update unlock"""
        doc = unlock.dict()
        doc['updated_at'] = datetime.now(timezone.utc)
        
        await self.unlocks.update_one(
            {'id': unlock.id},
            {'$set': doc},
            upsert=True
        )
        return unlock.id
    
    async def bulk_upsert_unlocks(self, unlocks: List[TokenUnlock]) -> int:
        """Bulk upsert unlocks"""
        if not unlocks:
            return 0
        
        from pymongo import UpdateOne
        
        operations = []
        for unlock in unlocks:
            doc = unlock.dict()
            doc['updated_at'] = datetime.now(timezone.utc)
            operations.append(
                UpdateOne(
                    {'id': unlock.id},
                    {'$set': doc},
                    upsert=True
                )
            )
        
        result = await self.unlocks.bulk_write(operations)
        return result.upserted_count + result.modified_count
    
    async def get_unlock(self, unlock_id: str) -> Optional[Dict]:
        """Get unlock by ID"""
        doc = await self.unlocks.find_one({'id': unlock_id}, {'_id': 0})
        return doc
    
    async def list_unlocks(
        self,
        project_id: Optional[str] = None,
        category: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """List unlocks with filters"""
        query = {}
        
        if project_id:
            query['project_id'] = project_id
        
        if category:
            query['category'] = category
        
        if from_date:
            query['unlock_date'] = {'$gte': from_date}
        
        if to_date:
            if 'unlock_date' in query:
                query['unlock_date']['$lte'] = to_date
            else:
                query['unlock_date'] = {'$lte': to_date}
        
        cursor = self.unlocks.find(query, {'_id': 0})
        cursor = cursor.sort('unlock_date', 1).skip(offset).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def get_upcoming_unlocks(
        self,
        days: int = 30,
        min_value_usd: Optional[float] = None,
        min_percent: Optional[float] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Get upcoming unlocks in next N days"""
        now = datetime.now(timezone.utc)
        end_date = now + timedelta(days=days)
        
        query = {
            'unlock_date': {
                '$gte': now,
                '$lte': end_date
            }
        }
        
        if min_value_usd:
            query['unlock_value_usd'] = {'$gte': min_value_usd}
        
        if min_percent:
            query['unlock_percent'] = {'$gte': min_percent}
        
        cursor = self.unlocks.find(query, {'_id': 0})
        cursor = cursor.sort('unlock_date', 1).limit(limit)
        
        unlocks = await cursor.to_list(length=limit)
        
        # Add days_until
        for u in unlocks:
            unlock_date = u['unlock_date']
            if isinstance(unlock_date, str):
                unlock_date = datetime.fromisoformat(unlock_date.replace('Z', '+00:00'))
            if unlock_date.tzinfo is None:
                unlock_date = unlock_date.replace(tzinfo=timezone.utc)
            u['days_until'] = (unlock_date - now).days
        
        return unlocks
    
    async def get_project_unlocks(
        self,
        project_id: str,
        include_past: bool = False,
        limit: int = 50
    ) -> List[Dict]:
        """Get all unlocks for a project"""
        query = {'project_id': project_id}
        
        if not include_past:
            query['unlock_date'] = {'$gte': datetime.now(timezone.utc)}
        
        cursor = self.unlocks.find(query, {'_id': 0})
        cursor = cursor.sort('unlock_date', 1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def get_project_summary(self, project_id: str) -> Optional[Dict]:
        """Get unlock summary for a project"""
        project = await self.get_project(project_id)
        if not project:
            return None
        
        now = datetime.now(timezone.utc)
        
        # Total unlocks
        total = await self.unlocks.count_documents({'project_id': project_id})
        
        # Next unlock
        next_unlock = await self.unlocks.find_one(
            {'project_id': project_id, 'unlock_date': {'$gte': now}},
            {'_id': 0},
            sort=[('unlock_date', 1)]
        )
        
        # 30-day totals
        end_30d = now + timedelta(days=30)
        pipeline = [
            {
                '$match': {
                    'project_id': project_id,
                    'unlock_date': {'$gte': now, '$lte': end_30d}
                }
            },
            {
                '$group': {
                    '_id': None,
                    'total_value': {'$sum': '$unlock_value_usd'},
                    'total_percent': {'$sum': '$unlock_percent'}
                }
            }
        ]
        
        agg_result = await self.unlocks.aggregate(pipeline).to_list(1)
        totals_30d = agg_result[0] if agg_result else {}
        
        return {
            'project_id': project_id,
            'project_symbol': project.get('symbol'),
            'project_name': project.get('name'),
            'total_unlocks': total,
            'next_unlock': next_unlock,
            'total_unlock_value_30d': totals_30d.get('total_value'),
            'total_unlock_percent_30d': totals_30d.get('total_percent')
        }
    
    async def count_unlocks(self, project_id: Optional[str] = None) -> int:
        """Count unlocks"""
        query = {}
        if project_id:
            query['project_id'] = project_id
        return await self.unlocks.count_documents(query)
    
    # ═══════════════════════════════════════════════════════════════
    # STATS
    # ═══════════════════════════════════════════════════════════════
    
    async def stats(self) -> Dict:
        """Get overall statistics"""
        now = datetime.now(timezone.utc)
        
        return {
            'total_projects': await self.count_projects(),
            'total_unlocks': await self.count_unlocks(),
            'upcoming_7d': await self.unlocks.count_documents({
                'unlock_date': {
                    '$gte': now,
                    '$lte': now + timedelta(days=7)
                }
            }),
            'upcoming_30d': await self.unlocks.count_documents({
                'unlock_date': {
                    '$gte': now,
                    '$lte': now + timedelta(days=30)
                }
            })
        }
