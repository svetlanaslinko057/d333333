"""
Data Normalization & Deduplication Engine

Pipeline:
RAW JSON → Parser → Normalized Tables → Dedup → Curated Intel Tables

This module handles:
1. Storing parsed data to normalized collections
2. Merging duplicates from multiple sources
3. Building the Event Index for fast queries
4. Creating curated final tables for API
"""

import logging
from typing import List, Dict, Any, Optional, Type
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from .models import (
    IntelUnlock,
    IntelFunding,
    IntelInvestor,
    IntelSale,
    IntelEvent
)

logger = logging.getLogger(__name__)

# Source weights for confidence calculation
SOURCE_WEIGHTS = {
    "cryptorank": 0.9,
    "dropstab": 0.85,
    "coingecko": 0.8,
    "manual": 1.0
}


class NormalizationEngine:
    """
    Handles data normalization and deduplication.
    
    Collections:
    - normalized_unlocks / normalized_funding / etc - parsed data
    - intel_unlocks / intel_funding / etc - deduplicated curated data
    - intel_events - unified event index
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    # ═══════════════════════════════════════════════════════════════
    # STORE NORMALIZED DATA
    # ═══════════════════════════════════════════════════════════════
    
    async def store_unlocks(self, unlocks: List[IntelUnlock]) -> Dict[str, Any]:
        """Store parsed unlocks to normalized collection"""
        if not unlocks:
            return {"stored": 0, "updated": 0}
        
        stored = 0
        updated = 0
        
        for unlock in unlocks:
            doc = unlock.to_mongo()
            
            # Upsert by unique ID
            result = await self.db.normalized_unlocks.update_one(
                {"id": unlock.id},
                {"$set": doc},
                upsert=True
            )
            
            if result.upserted_id:
                stored += 1
            elif result.modified_count > 0:
                updated += 1
        
        logger.info(f"[Normalize] Stored {stored} new, updated {updated} unlocks")
        return {"stored": stored, "updated": updated}
    
    async def store_funding(self, rounds: List[IntelFunding]) -> Dict[str, Any]:
        """Store parsed funding rounds to normalized collection"""
        if not rounds:
            return {"stored": 0, "updated": 0}
        
        stored = 0
        updated = 0
        
        for funding in rounds:
            doc = funding.to_mongo()
            
            result = await self.db.normalized_funding.update_one(
                {"id": funding.id},
                {"$set": doc},
                upsert=True
            )
            
            if result.upserted_id:
                stored += 1
            elif result.modified_count > 0:
                updated += 1
        
        logger.info(f"[Normalize] Stored {stored} new, updated {updated} funding rounds")
        return {"stored": stored, "updated": updated}
    
    async def store_investors(self, investors: List[IntelInvestor]) -> Dict[str, Any]:
        """Store parsed investors to normalized collection"""
        if not investors:
            return {"stored": 0, "updated": 0}
        
        stored = 0
        updated = 0
        
        for investor in investors:
            doc = investor.to_mongo()
            
            result = await self.db.normalized_investors.update_one(
                {"id": investor.id},
                {"$set": doc},
                upsert=True
            )
            
            if result.upserted_id:
                stored += 1
            elif result.modified_count > 0:
                updated += 1
        
        logger.info(f"[Normalize] Stored {stored} new, updated {updated} investors")
        return {"stored": stored, "updated": updated}
    
    async def store_sales(self, sales: List[IntelSale]) -> Dict[str, Any]:
        """Store parsed sales to normalized collection"""
        if not sales:
            return {"stored": 0, "updated": 0}
        
        stored = 0
        updated = 0
        
        for sale in sales:
            doc = sale.to_mongo()
            
            result = await self.db.normalized_sales.update_one(
                {"id": sale.id},
                {"$set": doc},
                upsert=True
            )
            
            if result.upserted_id:
                stored += 1
            elif result.modified_count > 0:
                updated += 1
        
        logger.info(f"[Normalize] Stored {stored} new, updated {updated} sales")
        return {"stored": stored, "updated": updated}
    
    # ═══════════════════════════════════════════════════════════════
    # DEDUPLICATION
    # ═══════════════════════════════════════════════════════════════
    
    async def dedupe_unlocks(self) -> Dict[str, Any]:
        """
        Deduplicate unlocks from normalized to curated table.
        
        Dedup key: symbol + unlock_date (within 1 day tolerance)
        Merge: sources, amounts (prefer higher values)
        """
        # Get all normalized unlocks
        cursor = self.db.normalized_unlocks.find({}, {"_id": 0})
        all_unlocks = await cursor.to_list(None)
        
        if not all_unlocks:
            return {"deduped": 0, "total_sources": 0}
        
        # Group by dedup key
        groups: Dict[str, List[Dict]] = {}
        
        for unlock in all_unlocks:
            symbol = unlock.get("symbol", "").upper()
            date = unlock.get("unlock_date", 0)
            
            if not symbol or not date:
                continue
            
            # Round date to day for grouping
            day = date // 86400
            key = f"{symbol}:{day}"
            
            if key not in groups:
                groups[key] = []
            groups[key].append(unlock)
        
        # Merge each group
        merged = 0
        
        for key, group in groups.items():
            if not group:
                continue
            
            # Merge into single record
            primary = group[0]
            sources = list(set(u.get("source") for u in group if u.get("source")))
            
            # Calculate confidence
            confidence = min(1.0, sum(SOURCE_WEIGHTS.get(s, 0.5) for s in sources))
            
            # Merge amounts (prefer non-null, then higher)
            amount_usd = max((u.get("amount_usd") or 0) for u in group) or None
            amount_tokens = max((u.get("amount_tokens") or 0) for u in group) or None
            percent_supply = max((u.get("percent_supply") or 0) for u in group) or None
            
            curated = {
                "id": primary["id"],
                "symbol": primary.get("symbol"),
                "project": primary.get("project"),
                "project_key": primary.get("project_key"),
                "unlock_date": primary.get("unlock_date"),
                "unlock_type": primary.get("unlock_type"),
                "amount_usd": amount_usd,
                "amount_tokens": amount_tokens,
                "percent_supply": percent_supply,
                "sources": sources,
                "confidence": confidence,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await self.db.intel_unlocks.update_one(
                {"id": curated["id"]},
                {"$set": curated},
                upsert=True
            )
            merged += 1
        
        logger.info(f"[Dedup] Merged {merged} unlock events from {len(all_unlocks)} sources")
        return {"deduped": merged, "total_sources": len(all_unlocks)}
    
    async def dedupe_funding(self) -> Dict[str, Any]:
        """Deduplicate funding rounds"""
        cursor = self.db.normalized_funding.find({}, {"_id": 0})
        all_funding = await cursor.to_list(None)
        
        if not all_funding:
            return {"deduped": 0, "total_sources": 0}
        
        # Group by project + round type + date (within 7 days)
        groups: Dict[str, List[Dict]] = {}
        
        for funding in all_funding:
            project_key = funding.get("project_key", "").lower()
            round_type = funding.get("round_type", "other")
            date = funding.get("round_date", 0)
            
            if not project_key:
                continue
            
            # Round date to week for grouping
            week = date // (86400 * 7) if date else 0
            key = f"{project_key}:{round_type}:{week}"
            
            if key not in groups:
                groups[key] = []
            groups[key].append(funding)
        
        merged = 0
        
        for key, group in groups.items():
            if not group:
                continue
            
            primary = group[0]
            sources = list(set(f.get("source") for f in group if f.get("source")))
            confidence = min(1.0, sum(SOURCE_WEIGHTS.get(s, 0.5) for s in sources))
            
            # Merge investors
            all_investors = set()
            all_leads = set()
            for f in group:
                all_investors.update(f.get("investors", []))
                all_leads.update(f.get("lead_investors", []))
            
            # Merge amounts
            raised_usd = max((f.get("raised_usd") or 0) for f in group) or None
            
            curated = {
                "id": primary["id"],
                "symbol": primary.get("symbol"),
                "project": primary.get("project"),
                "project_key": primary.get("project_key"),
                "round_type": primary.get("round_type"),
                "round_date": primary.get("round_date"),
                "raised_usd": raised_usd,
                "investors": list(all_investors),
                "lead_investors": list(all_leads),
                "investor_count": len(all_investors),
                "sources": sources,
                "confidence": confidence,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await self.db.intel_funding.update_one(
                {"id": curated["id"]},
                {"$set": curated},
                upsert=True
            )
            merged += 1
        
        logger.info(f"[Dedup] Merged {merged} funding rounds from {len(all_funding)} sources")
        return {"deduped": merged, "total_sources": len(all_funding)}
    
    async def dedupe_investors(self) -> Dict[str, Any]:
        """Deduplicate investors by slug"""
        cursor = self.db.normalized_investors.find({}, {"_id": 0})
        all_investors = await cursor.to_list(None)
        
        if not all_investors:
            return {"deduped": 0, "total_sources": 0}
        
        # Group by slug
        groups: Dict[str, List[Dict]] = {}
        
        for inv in all_investors:
            slug = inv.get("slug", "").lower()
            if not slug:
                continue
            
            if slug not in groups:
                groups[slug] = []
            groups[slug].append(inv)
        
        merged = 0
        
        for slug, group in groups.items():
            if not group:
                continue
            
            primary = group[0]
            sources = list(set(i.get("source") for i in group if i.get("source")))
            
            # Merge stats
            investments_count = max(i.get("investments_count", 0) for i in group)
            
            # Merge portfolios
            all_portfolio = set()
            for i in group:
                all_portfolio.update(i.get("portfolio", []))
            
            curated = {
                "id": primary["id"],
                "name": primary.get("name"),
                "slug": slug,
                "tier": primary.get("tier"),
                "category": primary.get("category"),
                "investments_count": investments_count,
                "portfolio": list(all_portfolio),
                "logo_url": primary.get("logo_url"),
                "sources": sources,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await self.db.intel_investors.update_one(
                {"slug": slug},
                {"$set": curated},
                upsert=True
            )
            merged += 1
        
        logger.info(f"[Dedup] Merged {merged} investors from {len(all_investors)} sources")
        return {"deduped": merged, "total_sources": len(all_investors)}
    
    # ═══════════════════════════════════════════════════════════════
    # EVENT INDEX
    # ═══════════════════════════════════════════════════════════════
    
    async def build_event_index(self) -> Dict[str, Any]:
        """
        Build unified event index from curated tables.
        
        Enables fast queries:
        - GET /events?symbol=SOL
        - GET /events?type=unlock&date_range=next_30_days
        """
        events_created = 0
        
        # Index unlocks
        cursor = self.db.intel_unlocks.find({}, {"_id": 0})
        unlocks = await cursor.to_list(None)
        
        for unlock in unlocks:
            event = {
                "id": f"unlock:{unlock.get('id')}",
                "event_type": "unlock",
                "symbol": unlock.get("symbol"),
                "project": unlock.get("project"),
                "project_key": unlock.get("project_key"),
                "event_date": unlock.get("unlock_date"),
                "amount_usd": unlock.get("amount_usd"),
                "sources": unlock.get("sources", []),
                "confidence": unlock.get("confidence", 0.5),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await self.db.intel_events.update_one(
                {"id": event["id"]},
                {"$set": event},
                upsert=True
            )
            events_created += 1
        
        # Index funding
        cursor = self.db.intel_funding.find({}, {"_id": 0})
        funding = await cursor.to_list(None)
        
        for f in funding:
            event = {
                "id": f"funding:{f.get('id')}",
                "event_type": "funding",
                "symbol": f.get("symbol"),
                "project": f.get("project"),
                "project_key": f.get("project_key"),
                "event_date": f.get("round_date"),
                "amount_usd": f.get("raised_usd"),
                "sources": f.get("sources", []),
                "confidence": f.get("confidence", 0.5),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await self.db.intel_events.update_one(
                {"id": event["id"]},
                {"$set": event},
                upsert=True
            )
            events_created += 1
        
        # Create indexes for fast queries
        await self.db.intel_events.create_index([("symbol", 1), ("event_date", 1)])
        await self.db.intel_events.create_index([("event_type", 1), ("event_date", 1)])
        await self.db.intel_events.create_index([("event_date", 1)])
        
        logger.info(f"[EventIndex] Built index with {events_created} events")
        return {"events_indexed": events_created}
    
    # ═══════════════════════════════════════════════════════════════
    # FULL PIPELINE
    # ═══════════════════════════════════════════════════════════════
    
    async def run_full_pipeline(self) -> Dict[str, Any]:
        """Run full normalization → dedup → index pipeline"""
        results = {
            "dedupe_unlocks": await self.dedupe_unlocks(),
            "dedupe_funding": await self.dedupe_funding(),
            "dedupe_investors": await self.dedupe_investors(),
            "event_index": await self.build_event_index()
        }
        
        logger.info(f"[Pipeline] Full normalization complete: {results}")
        return results
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics"""
        return {
            "normalized": {
                "unlocks": await self.db.normalized_unlocks.count_documents({}),
                "funding": await self.db.normalized_funding.count_documents({}),
                "investors": await self.db.normalized_investors.count_documents({}),
                "sales": await self.db.normalized_sales.count_documents({})
            },
            "curated": {
                "unlocks": await self.db.intel_unlocks.count_documents({}),
                "funding": await self.db.intel_funding.count_documents({}),
                "investors": await self.db.intel_investors.count_documents({}),
                "sales": await self.db.intel_sales.count_documents({})
            },
            "events": await self.db.intel_events.count_documents({})
        }


def create_normalization_engine(db: AsyncIOMotorDatabase) -> NormalizationEngine:
    """Factory function"""
    return NormalizationEngine(db)
