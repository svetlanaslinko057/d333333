"""
Dropstab Sync Service - Hybrid approach

Uses SSR scraping as primary method (works reliably).
BFF API as fallback if available.

SSR gets ~100 coins per page load.
For full market, make multiple requests to different pages.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from .scraper import DropstabScraper, dropstab_scraper
from ..common.storage import upsert_with_diff

logger = logging.getLogger(__name__)


class DropstabSync:
    """
    Sync service using SSR scraping (primary) with BFF fallback.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, scraper: Optional[DropstabScraper] = None):
        self.db = db
        self.scraper = scraper or dropstab_scraper
    
    async def sync_markets(self, limit: int = 100, max_pages: int = 1) -> Dict[str, Any]:
        """
        Sync market data via SSR scraping with pagination
        
        Args:
            limit: Max coins to process per page
            max_pages: Number of pages to scrape (1 page = ~100 coins)
                - max_pages=1: Quick sync (100 coins)
                - max_pages=200: Full market (~15000+ coins)
        """
        logger.info(f"[Dropstab] Syncing markets via SSR (max_pages={max_pages})...")
        
        raw = await self.scraper.scrape_coins(max_pages=max_pages)
        if not raw:
            return {'total': 0, 'changed': 0, 'note': 'No data from SSR'}
        
        collection = self.db.intel_projects
        changed = 0
        processed = 0
        
        for item in raw:
            doc = self._parse_coin(item)
            if doc:
                result = await upsert_with_diff(collection, doc)
                if result.get('changed'):
                    changed += 1
                processed += 1
        
        logger.info(f"[Dropstab] Markets: {len(raw)} scraped, {processed} processed, {changed} changed")
        return {'total': len(raw), 'processed': processed, 'changed': changed}
    
    async def sync_markets_full(self, max_pages: int = 200) -> Dict[str, Any]:
        """
        Full market sync - get all coins (15000+)
        This is for daily cron job
        """
        logger.info(f"[Dropstab] Starting FULL market sync...")
        return await self.sync_markets(max_pages=max_pages)
    
    async def sync_projects(self, limit: int = 100, max_pages: int = 1) -> Dict[str, Any]:
        """Alias for sync_markets with pagination"""
        return await self.sync_markets(limit=limit, max_pages=max_pages)
    
    async def sync_unlock_events(self, limit: int = 100, max_pages: int = 1) -> Dict[str, Any]:
        """Sync unlocks via SSR"""
        logger.info("[Dropstab] Syncing unlocks via SSR...")
        
        raw = await self.scraper.scrape_vesting()
        if not raw:
            return {'total': 0, 'changed': 0, 'note': 'No data from SSR'}
        
        collection = self.db.intel_unlocks
        changed = 0
        
        for item in raw[:limit]:
            doc = self._parse_unlock(item)
            if doc:
                result = await upsert_with_diff(collection, doc)
                if result.get('changed'):
                    changed += 1
        
        logger.info(f"[Dropstab] Unlocks: {len(raw)} scraped, {changed} changed")
        return {'total': len(raw), 'changed': changed}
    
    async def sync_categories(self) -> Dict[str, Any]:
        """Sync categories via SSR"""
        logger.info("[Dropstab] Syncing categories via SSR...")
        
        raw = await self.scraper.scrape_categories()
        if not raw:
            return {'total': 0, 'changed': 0, 'note': 'No data from SSR'}
        
        collection = self.db.intel_categories
        changed = 0
        
        for item in raw:
            doc = self._parse_category(item)
            if doc:
                result = await upsert_with_diff(collection, doc)
                if result.get('changed'):
                    changed += 1
        
        logger.info(f"[Dropstab] Categories: {len(raw)} scraped, {changed} changed")
        return {'total': len(raw), 'changed': changed}
    
    async def sync_narratives(self) -> Dict[str, Any]:
        return await self.sync_categories()
    
    async def sync_ecosystems(self) -> Dict[str, Any]:
        return await self.sync_categories()
    
    async def sync_trending(self) -> Dict[str, Any]:
        """Sync gainers/losers via SSR"""
        logger.info("[Dropstab] Syncing trending via SSR...")
        
        perf = await self.scraper.scrape_top_performance()
        gainers = perf.get('gainers', [])
        losers = perf.get('losers', [])
        
        if not gainers and not losers:
            return {'total': 0, 'note': 'No data from SSR'}
        
        collection = self.db.intel_activity
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        for idx, item in enumerate(gainers):
            doc = self._make_activity_doc(item, 'gainer', idx, date)
            await collection.update_one({'key': doc['key']}, {'$set': doc}, upsert=True)
        
        for idx, item in enumerate(losers):
            doc = self._make_activity_doc(item, 'loser', idx, date)
            await collection.update_one({'key': doc['key']}, {'$set': doc}, upsert=True)
        
        logger.info(f"[Dropstab] Trending: {len(gainers)} gainers, {len(losers)} losers")
        return {'gainers': len(gainers), 'losers': len(losers)}
    
    async def sync_gainers(self) -> Dict[str, Any]:
        return await self.sync_trending()
    
    async def sync_losers(self) -> Dict[str, Any]:
        return await self.sync_trending()
    
    async def sync_investors(self) -> Dict[str, Any]:
        """Sync investors via SSR"""
        logger.info("[Dropstab] Syncing investors via SSR...")
        
        raw = await self.scraper.scrape_investors()
        if not raw:
            return {'total': 0, 'changed': 0, 'note': 'No data from SSR'}
        
        collection = self.db.intel_investors
        changed = 0
        
        for item in raw:
            doc = self._parse_investor(item)
            if doc:
                result = await upsert_with_diff(collection, doc)
                if result.get('changed'):
                    changed += 1
        
        logger.info(f"[Dropstab] Investors: {len(raw)} scraped, {changed} changed")
        return {'total': len(raw), 'changed': changed}
    
    async def sync_fundraising(self) -> Dict[str, Any]:
        """Sync funding via SSR"""
        logger.info("[Dropstab] Syncing fundraising via SSR...")
        
        raw = await self.scraper.scrape_fundraising()
        if not raw:
            return {'total': 0, 'changed': 0, 'note': 'No data from SSR'}
        
        collection = self.db.intel_fundraising
        changed = 0
        
        for item in raw:
            doc = self._parse_funding(item)
            if doc:
                result = await upsert_with_diff(collection, doc)
                if result.get('changed'):
                    changed += 1
        
        logger.info(f"[Dropstab] Fundraising: {len(raw)} scraped, {changed} changed")
        return {'total': len(raw), 'changed': changed}
    
    async def sync_listings(self, limit: int = 100, max_pages: int = 1) -> Dict[str, Any]:
        """Sync activities/listings via SSR"""
        logger.info("[Dropstab] Syncing listings via SSR...")
        
        raw = await self.scraper.scrape_activities()
        if not raw:
            return {'total': 0, 'changed': 0, 'note': 'No data from SSR'}
        
        collection = self.db.intel_activity
        changed = 0
        
        for item in raw[:limit]:
            doc = self._parse_activity(item)
            if doc:
                result = await upsert_with_diff(collection, doc)
                if result.get('changed'):
                    changed += 1
        
        logger.info(f"[Dropstab] Listings: {len(raw)} scraped, {changed} changed")
        return {'total': len(raw), 'changed': changed}
    
    async def sync_market_overview(self) -> Dict[str, Any]:
        return await self.sync_markets(limit=10)
    
    async def sync_all(self) -> Dict[str, Any]:
        """Run full sync"""
        logger.info("[Dropstab] Starting full SSR sync...")
        
        results = {
            'source': 'dropstab',
            'method': 'ssr_scrape',
            'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
            'syncs': {}
        }
        
        sync_tasks = [
            ('markets', lambda: self.sync_markets(limit=100)),
            ('unlocks', self.sync_unlock_events),
            ('categories', self.sync_categories),
            ('trending', self.sync_trending),
            ('investors', self.sync_investors),
            ('fundraising', self.sync_fundraising),
            ('listings', lambda: self.sync_listings(limit=100)),
        ]
        
        for name, sync_func in sync_tasks:
            try:
                results['syncs'][name] = await sync_func()
            except Exception as e:
                logger.error(f"[Dropstab] {name} sync failed: {e}")
                results['syncs'][name] = {'error': str(e)}
        
        logger.info("[Dropstab] Full sync complete")
        return results
    
    # ═══════════════════════════════════════════════════════════════
    # PARSERS
    # ═══════════════════════════════════════════════════════════════
    
    def _get_usd(self, data) -> Optional[float]:
        """Extract USD value from nested structure"""
        if data is None:
            return None
        if isinstance(data, dict):
            usd_val = data.get('USD')
            if usd_val is not None:
                try:
                    return float(usd_val)
                except:
                    return None
            return None
        try:
            return float(data)
        except:
            return None
    
    def _parse_coin(self, item: Dict) -> Optional[Dict]:
        """Parse coin from SSR data"""
        if not item:
            return None
        
        symbol = str(item.get('symbol', '')).upper()
        slug = item.get('slug') or symbol.lower()
        
        if not symbol and not slug:
            return None
        
        # Handle nested price/volume/change
        price_usd = self._get_usd(item.get('price'))
        market_cap = self._get_usd(item.get('marketCap'))
        fdv = self._get_usd(item.get('fdvMarketCap')) or self._get_usd(item.get('fdv'))
        
        # Volume is nested: volume.1D.USD
        volume_data = item.get('volume', {})
        if isinstance(volume_data, dict):
            volume_1d = volume_data.get('1D', {})
            volume_usd = self._get_usd(volume_1d)
        else:
            volume_usd = None
        
        # Change is nested: change.1D.USD  
        change_data = item.get('change', {})
        change_1d = change_data.get('1D', {}) if isinstance(change_data, dict) else {}
        change_24h = self._get_usd(change_1d)
        
        return {
            'key': f"dropstab:{slug}",
            'source': 'dropstab',
            'slug': slug,
            'symbol': symbol,
            'name': item.get('name', ''),
            'image': item.get('image'),
            'price_usd': float(price_usd) if price_usd else None,
            'market_cap': float(market_cap) if market_cap else None,
            'fully_diluted_valuation': float(fdv) if fdv else None,
            'total_volume': float(volume_usd) if volume_usd else None,
            'price_change_percentage_24h': float(change_24h) if change_24h else None,
            'market_cap_rank': item.get('rank'),
            'updated_at': datetime.now(timezone.utc)
        }
    
    def _parse_unlock(self, item: Dict) -> Optional[Dict]:
        if not item:
            return None
        
        symbol = str(item.get('symbol', '')).upper()
        slug = item.get('slug') or symbol.lower()
        unlock_date = item.get('date') or item.get('unlockDate')
        
        if not slug:
            return None
        
        return {
            'key': f"dropstab:unlock:{slug}:{unlock_date or 'unknown'}",
            'source': 'dropstab',
            'slug': slug,
            'symbol': symbol,
            'name': item.get('name', ''),
            'unlock_date': unlock_date,
            'unlock_percent': item.get('unlockPercent') or item.get('percent'),
            'unlock_usd': item.get('unlockUsd') or item.get('value'),
            'tokens_amount': item.get('tokensAmount') or item.get('amount'),
            'allocation': item.get('allocation') or item.get('type'),
            'updated_at': datetime.now(timezone.utc)
        }
    
    def _parse_category(self, item: Dict) -> Optional[Dict]:
        if not item:
            return None
        
        cat_id = item.get('slug') or item.get('id') or str(item.get('name', '')).lower().replace(' ', '-')
        
        return {
            'key': f"dropstab:category:{cat_id}",
            'source': 'dropstab',
            'category_id': cat_id,
            'name': item.get('name', ''),
            'slug': item.get('slug', cat_id),
            'coins_count': item.get('coinsCount', 0),
            'market_cap': item.get('marketCap', 0),
            'updated_at': datetime.now(timezone.utc)
        }
    
    def _parse_investor(self, item: Dict) -> Optional[Dict]:
        if not item:
            return None
        
        slug = item.get('slug') or item.get('id')
        if not slug:
            return None
        
        return {
            'key': f"dropstab:investor:{slug}",
            'source': 'dropstab',
            'slug': slug,
            'name': item.get('name', ''),
            'tier': item.get('tier'),
            'type': item.get('type'),
            'image': item.get('image'),
            'investments_count': item.get('investmentsCount') or item.get('investments'),
            'website': item.get('website'),
            'twitter': item.get('twitter'),
            'updated_at': datetime.now(timezone.utc)
        }
    
    def _parse_funding(self, item: Dict) -> Optional[Dict]:
        if not item:
            return None
        
        round_id = item.get('id') or item.get('roundId')
        coin_slug = item.get('slug') or item.get('projectSlug')
        
        if not round_id and not coin_slug:
            return None
        
        return {
            'key': f"dropstab:funding:{coin_slug or 'unknown'}:{round_id or 'unknown'}",
            'source': 'dropstab',
            'round_id': round_id,
            'coin_slug': coin_slug,
            'symbol': str(item.get('symbol', '')).upper(),
            'name': item.get('name', ''),
            'round': item.get('round') or item.get('stage'),
            'date': item.get('date'),
            'amount': item.get('amount') or item.get('raised'),
            'valuation': item.get('valuation'),
            'investors': item.get('investors', []),
            'updated_at': datetime.now(timezone.utc)
        }
    
    def _parse_activity(self, item: Dict) -> Optional[Dict]:
        if not item:
            return None
        
        activity_id = item.get('id')
        if not activity_id:
            return None
        
        return {
            'key': f"dropstab:activity:{activity_id}",
            'source': 'dropstab',
            'type': 'activity',
            'activity_id': activity_id,
            'title': item.get('title') or item.get('name'),
            'description': item.get('description'),
            'status': item.get('status'),
            'date': item.get('date'),
            'coin_symbol': str(item.get('coinSymbol', '')).upper(),
            'exchange': item.get('exchange'),
            'updated_at': datetime.now(timezone.utc)
        }
    
    def _make_activity_doc(self, item: Dict, activity_type: str, rank: int, date: str) -> Dict:
        return {
            'key': f"dropstab:{activity_type}:{item.get('symbol', rank)}:{date}",
            'source': 'dropstab',
            'type': activity_type,
            'symbol': str(item.get('symbol', '')).upper(),
            'name': item.get('name', ''),
            'slug': item.get('slug', ''),
            'rank': rank + 1,
            'price': self._get_usd(item.get('price')),
            'change_24h': self._get_usd(item.get('change', {}).get('1D') if isinstance(item.get('change'), dict) else item.get('change')),
            'date': date,
            'updated_at': datetime.now(timezone.utc)
        }
