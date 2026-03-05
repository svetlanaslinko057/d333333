"""
CryptoRank Sync Service
Processes JSON data from CryptoRank (scraped via browser or manual fetch).

This is a SCRAPER service - it receives JSON data and stores it.
No automatic API fetching - data is provided externally.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from .parsers import (
    parse_categories,
    parse_funding,
    parse_top_investors,
    parse_unlocks,
    parse_tge_unlocks,
    parse_launchpads,
    parse_market
)
from ...common.storage import upsert_with_diff, push_to_moderation

logger = logging.getLogger(__name__)


class CryptoRankSync:
    """
    Sync service for CryptoRank data.
    Receives JSON data and stores it in MongoDB.
    
    Usage:
        sync = CryptoRankSync(db)
        await sync.ingest_funding(json_data)
        await sync.ingest_investors(json_data)
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def ingest_categories(self, json_data: List[Dict]) -> Dict[str, Any]:
        """
        Ingest categories data.
        
        Expected format:
        [
            {"id": 54, "name": "DeFi", "slug": "defi", ...},
            ...
        ]
        """
        logger.info("[CryptoRank] Ingesting categories...")
        
        data = json_data if isinstance(json_data, list) else json_data.get('data', [])
        docs = parse_categories(data)
        
        collection = self.db.intel_categories
        changed = 0
        
        for doc in docs:
            result = await upsert_with_diff(collection, doc)
            if result['changed']:
                changed += 1
        
        logger.info(f"[CryptoRank] Categories: {len(docs)} total, {changed} changed")
        return {'total': len(docs), 'changed': changed}
    
    async def ingest_funding(self, json_data: Dict) -> Dict[str, Any]:
        """
        Ingest funding rounds data.
        
        Expected format:
        {
            "total": 10851,
            "data": [
                {
                    "key": "cyclops",
                    "name": "Cyclops",
                    "raise": 8000000,
                    "stage": "STRATEGIC",
                    "date": "2026-03-04",
                    "funds": [...]
                },
                ...
            ]
        }
        """
        logger.info("[CryptoRank] Ingesting funding rounds...")
        
        data = json_data.get('data', []) if isinstance(json_data, dict) else json_data
        docs = parse_funding(data)
        
        collection = self.db.intel_fundraising
        changed = 0
        
        for doc in docs:
            result = await upsert_with_diff(collection, doc)
            if result['changed'] and result['change_type']:
                changed += 1
                await push_to_moderation(
                    self.db, 'cryptorank', 'fundraising',
                    doc['key'], doc, result['change_type']
                )
        
        logger.info(f"[CryptoRank] Funding: {len(docs)} total, {changed} changed")
        return {'total': len(docs), 'changed': changed}
    
    async def ingest_investors(self, json_data: List[Dict]) -> Dict[str, Any]:
        """
        Ingest investors data.
        
        Expected format:
        [
            {"slug": "coinbase-ventures", "name": "Coinbase Ventures", "count": 38, ...},
            ...
        ]
        """
        logger.info("[CryptoRank] Ingesting investors...")
        
        data = json_data if isinstance(json_data, list) else json_data.get('data', [])
        docs = parse_top_investors(data)
        
        collection = self.db.intel_investors
        changed = 0
        
        for doc in docs:
            result = await upsert_with_diff(collection, doc)
            if result['changed'] and result['change_type']:
                changed += 1
                await push_to_moderation(
                    self.db, 'cryptorank', 'investor',
                    doc['key'], doc, result['change_type']
                )
        
        logger.info(f"[CryptoRank] Investors: {len(docs)} total, {changed} changed")
        return {'total': len(docs), 'changed': changed}
    
    async def ingest_unlocks(self, json_data: List[Dict], unlock_type: str = 'vesting') -> Dict[str, Any]:
        """
        Ingest token unlocks data.
        
        Expected format:
        [
            {
                "key": "movement-labs",
                "symbol": "MOVE",
                "unlockUsd": 3695283,
                "tokensPercent": 4.8,
                "unlockDate": "2026-03-09"
            },
            ...
        ]
        
        Args:
            json_data: List of unlock events
            unlock_type: 'vesting' or 'tge'
        """
        logger.info(f"[CryptoRank] Ingesting {unlock_type} unlocks...")
        
        data = json_data if isinstance(json_data, list) else json_data.get('data', [])
        
        if unlock_type == 'tge':
            docs = parse_tge_unlocks(data)
        else:
            docs = parse_unlocks(data)
        
        collection = self.db.intel_unlocks
        changed = 0
        
        for doc in docs:
            result = await upsert_with_diff(collection, doc)
            if result['changed'] and result['change_type']:
                changed += 1
                await push_to_moderation(
                    self.db, 'cryptorank', 'unlock',
                    doc['key'], doc, result['change_type']
                )
        
        logger.info(f"[CryptoRank] Unlocks ({unlock_type}): {len(docs)} total, {changed} changed")
        return {'total': len(docs), 'changed': changed}
    
    async def ingest_unlock_totals(self, json_data: List[Dict]) -> Dict[str, Any]:
        """
        Ingest market-wide unlock totals.
        
        Expected format:
        [
            {"usdUnlock": 88113695, "timePoint": "2026-03-01"},
            ...
        ]
        """
        logger.info("[CryptoRank] Ingesting unlock totals...")
        
        data = json_data if isinstance(json_data, list) else json_data.get('data', [])
        
        collection = self.db.market_unlocks
        changed = 0
        
        for item in data:
            date = item.get('timePoint')
            unlock_usd = item.get('usdUnlock', 0)
            
            if not date:
                continue
            
            doc = {
                'key': f"cryptorank:market_unlock:{date}",
                'date': date,
                'unlock_usd': unlock_usd,
                'source': 'cryptorank'
            }
            
            result = await upsert_with_diff(collection, doc)
            if result['changed']:
                changed += 1
        
        logger.info(f"[CryptoRank] Unlock totals: {len(data)} total, {changed} changed")
        return {'total': len(data), 'changed': changed}
    
    async def ingest_launchpads(self, json_data: List[Dict]) -> Dict[str, Any]:
        """
        Ingest launchpads data.
        
        Expected format:
        [
            {"id": 46, "key": "seedify", "name": "Seedify", "type": "IDO", ...},
            ...
        ]
        """
        logger.info("[CryptoRank] Ingesting launchpads...")
        
        data = json_data if isinstance(json_data, list) else json_data.get('data', [])
        docs = parse_launchpads(data)
        
        collection = self.db.intel_launchpads
        changed = 0
        
        for doc in docs:
            result = await upsert_with_diff(collection, doc)
            if result['changed']:
                changed += 1
        
        logger.info(f"[CryptoRank] Launchpads: {len(docs)} total, {changed} changed")
        return {'total': len(docs), 'changed': changed}
    
    async def ingest_market(self, json_data: Dict) -> Dict[str, Any]:
        """
        Ingest market overview data.
        
        Expected format:
        {
            "btcDominance": 56.97,
            "ethDominance": 10.08,
            "totalMarketCap": 2563526299439,
            "totalVolume24h": ...,
            "gas": {...}
        }
        """
        logger.info("[CryptoRank] Ingesting market data...")
        
        doc = parse_market(json_data)
        
        collection = self.db.intel_market
        
        # Use timestamp as key for historical tracking
        doc['key'] = f"cryptorank:market:{doc['timestamp']}"
        
        result = await upsert_with_diff(collection, doc)
        
        logger.info(f"[CryptoRank] Market: 1 record, {'changed' if result['changed'] else 'unchanged'}")
        return {'total': 1, 'changed': 1 if result['changed'] else 0}
    
    async def ingest_all(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingest all data types at once.
        
        Expected format:
        {
            "categories": [...],
            "funding": {...},
            "investors": [...],
            "unlocks": [...],
            "tge_unlocks": [...],
            "unlock_totals": [...],
            "launchpads": [...],
            "market": {...}
        }
        """
        logger.info("[CryptoRank] Starting full ingest...")
        
        results = {
            'source': 'cryptorank',
            'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
            'ingests': {}
        }
        
        ingest_map = {
            'categories': self.ingest_categories,
            'funding': self.ingest_funding,
            'investors': self.ingest_investors,
            'unlocks': self.ingest_unlocks,
            'unlock_totals': self.ingest_unlock_totals,
            'launchpads': self.ingest_launchpads,
            'market': self.ingest_market,
        }
        
        for key, ingest_func in ingest_map.items():
            if key in data and data[key]:
                try:
                    results['ingests'][key] = await ingest_func(data[key])
                except Exception as e:
                    logger.error(f"[CryptoRank] {key} ingest failed: {e}")
                    results['ingests'][key] = {'error': str(e)}
        
        # Handle TGE unlocks separately
        if 'tge_unlocks' in data and data['tge_unlocks']:
            try:
                results['ingests']['tge_unlocks'] = await self.ingest_unlocks(data['tge_unlocks'], 'tge')
            except Exception as e:
                logger.error(f"[CryptoRank] tge_unlocks ingest failed: {e}")
                results['ingests']['tge_unlocks'] = {'error': str(e)}
        
        logger.info(f"[CryptoRank] Full ingest complete")
        return results


    # ═══════════════════════════════════════════════════════════════
    # PAGINATION HELPERS
    # ═══════════════════════════════════════════════════════════════
    
    async def ingest_funding_page(self, page_data: Dict, page_num: int = 0) -> Dict[str, Any]:
        """
        Ingest a single page of funding data.
        Useful for incremental sync.
        
        Args:
            page_data: Single page response from CryptoRank
            page_num: Page number for logging
        
        Returns:
            {total, changed, page}
        """
        result = await self.ingest_funding(page_data)
        result['page'] = page_num
        return result
    
    async def ingest_funding_batch(self, pages: List[Dict]) -> Dict[str, Any]:
        """
        Ingest multiple pages of funding data.
        
        Args:
            pages: List of page responses, each with {"total": N, "data": [...]}
        
        Returns:
            {total, changed, pages_processed}
        """
        logger.info(f"[CryptoRank] Batch ingesting {len(pages)} funding pages...")
        
        total_docs = 0
        total_changed = 0
        
        for i, page_data in enumerate(pages):
            result = await self.ingest_funding(page_data)
            total_docs += result.get('total', 0)
            total_changed += result.get('changed', 0)
            logger.debug(f"[CryptoRank] Page {i+1}: {result.get('total', 0)} items")
        
        logger.info(f"[CryptoRank] Batch complete: {total_docs} total, {total_changed} changed")
        return {
            'total': total_docs,
            'changed': total_changed,
            'pages_processed': len(pages)
        }
    
    async def get_sync_stats(self) -> Dict[str, Any]:
        """
        Get sync statistics for CryptoRank data.
        """
        stats = {
            'source': 'cryptorank',
            'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
            'collections': {}
        }
        
        # Count documents by source
        collections = [
            ('funding', 'intel_fundraising'),
            ('investors', 'intel_investors'),
            ('unlocks', 'intel_unlocks'),
            ('launchpads', 'intel_launchpads'),
            ('categories', 'intel_categories'),
            ('market', 'intel_market'),
            ('unlock_totals', 'market_unlocks'),
        ]
        
        for name, coll_name in collections:
            coll = self.db[coll_name]
            count = await coll.count_documents({'source': 'cryptorank'})
            stats['collections'][name] = count
        
        return stats
