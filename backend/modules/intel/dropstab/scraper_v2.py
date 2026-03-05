"""
Dropstab Production Scraper v2
- Dynamic dataset finder (structure-agnostic)
- Retry/throttling
- Raw snapshot debug
- 4 data blocks: coins, unlocks, funding, investors
"""

import asyncio
import httpx
import json
import time
import random
import hashlib
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from pathlib import Path

logger = logging.getLogger(__name__)

BASE = "https://dropstab.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

RETRIES = 5
SNAPSHOT_DIR = Path("/app/backend/modules/intel/dropstab/snapshots")


class DropstabScraperV2:
    """
    Production-grade Dropstab scraper with:
    - Dynamic dataset discovery
    - Automatic retry with exponential backoff
    - Rate limiting
    - Snapshot debugging
    """
    
    def __init__(self):
        self.timeout = 30.0
        self.min_interval = 1.5
        self.last_request = 0
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    
    async def _rate_limit(self):
        """Enforce rate limiting with random jitter"""
        now = time.time()
        diff = now - self.last_request
        if diff < self.min_interval:
            wait = self.min_interval - diff + random.uniform(0.5, 1.5)
            await asyncio.sleep(wait)
        self.last_request = time.time()
    
    async def _fetch(self, url: str) -> Optional[str]:
        """Fetch with retry and exponential backoff"""
        for attempt in range(RETRIES):
            try:
                await self._rate_limit()
                
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    response = await client.get(url, headers=HEADERS)
                    
                    if response.status_code == 200:
                        logger.info(f"[Dropstab] OK: {url} ({len(response.text)} bytes)")
                        return response.text
                    
                    if response.status_code in [429, 500, 502, 503]:
                        delay = (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(f"[Dropstab] {response.status_code} on {url}, retry in {delay:.1f}s")
                        await asyncio.sleep(delay)
                        continue
                    
                    logger.warning(f"[Dropstab] {url} returned {response.status_code}")
                    
            except Exception as e:
                delay = (2 ** attempt) + random.uniform(0, 1)
                logger.error(f"[Dropstab] Error on {url}: {e}, retry in {delay:.1f}s")
                await asyncio.sleep(delay)
        
        return None
    
    def _extract_next_data(self, html: str) -> Optional[Dict]:
        """Extract __NEXT_DATA__ JSON from HTML"""
        try:
            soup = BeautifulSoup(html, 'lxml')
            script = soup.find('script', id='__NEXT_DATA__')
            
            if script and script.string:
                return json.loads(script.string)
            
            logger.warning("[Dropstab] No __NEXT_DATA__ found")
            return None
            
        except Exception as e:
            logger.error(f"[Dropstab] Failed to parse __NEXT_DATA__: {e}")
            return None
    
    def _find_dataset(self, obj: Any, keys: List[str]) -> Optional[List[Dict]]:
        """
        Dynamic dataset finder - searches recursively for lists
        containing objects with specified keys.
        
        This makes the scraper resilient to structure changes.
        """
        if isinstance(obj, list):
            if len(obj) > 0 and isinstance(obj[0], dict):
                if any(k in obj[0] for k in keys):
                    return obj
        
        if isinstance(obj, dict):
            for v in obj.values():
                result = self._find_dataset(v, keys)
                if result:
                    return result
        
        return None
    
    def _save_snapshot(self, name: str, data: Any) -> None:
        """Save raw snapshot for debugging"""
        try:
            path = SNAPSHOT_DIR / f"snapshot_{name}.json"
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            logger.debug(f"[Dropstab] Snapshot saved: {path}")
        except Exception as e:
            logger.error(f"[Dropstab] Snapshot save failed: {e}")
    
    def _compute_hash(self, data: Any) -> str:
        """Compute hash for change detection"""
        return hashlib.sha1(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()[:12]
    
    # ═══════════════════════════════════════════════════════════════
    # SCRAPE METHODS
    # ═══════════════════════════════════════════════════════════════
    
    async def scrape_coins(self) -> List[Dict]:
        """
        Scrape coins metadata from homepage.
        Keys: symbol, price, rank, marketCap
        """
        logger.info("[Dropstab] Scraping coins...")
        
        # Try multiple paths
        for path in ['/', '/coins']:
            html = await self._fetch(f"{BASE}{path}")
            if not html:
                continue
            
            data = self._extract_next_data(html)
            if not data:
                continue
            
            # Dynamic search for coin dataset
            coins = self._find_dataset(data, ["symbol", "price", "rank", "marketCap", "name"])
            
            if coins:
                self._save_snapshot("coins", coins)
                logger.info(f"[Dropstab] Found {len(coins)} coins from {path}")
                return coins
        
        logger.warning("[Dropstab] No coins found")
        return []
    
    async def scrape_unlocks(self) -> List[Dict]:
        """
        Scrape token unlock events.
        Keys: unlockDate, unlockAmount, project, allocation
        """
        logger.info("[Dropstab] Scraping unlocks...")
        
        for path in ['/vesting', '/unlock', '/token-unlocks']:
            html = await self._fetch(f"{BASE}{path}")
            if not html:
                continue
            
            data = self._extract_next_data(html)
            if not data:
                continue
            
            # Dynamic search for unlock dataset
            unlocks = self._find_dataset(data, [
                "unlockDate", "unlockAmount", "allocation", 
                "vestingEvent", "unlock", "nextUnlock"
            ])
            
            if unlocks:
                self._save_snapshot("unlocks", unlocks)
                logger.info(f"[Dropstab] Found {len(unlocks)} unlocks from {path}")
                return unlocks
        
        logger.warning("[Dropstab] No unlocks found")
        return []
    
    async def scrape_funding(self) -> List[Dict]:
        """
        Scrape funding rounds.
        Keys: raised, round, valuation, investors, date
        """
        logger.info("[Dropstab] Scraping funding...")
        
        for path in ['/latest-funding-rounds', '/funding-rounds', '/fundraising']:
            html = await self._fetch(f"{BASE}{path}")
            if not html:
                continue
            
            data = self._extract_next_data(html)
            if not data:
                continue
            
            # Dynamic search for funding dataset
            funding = self._find_dataset(data, [
                "raised", "round", "valuation", "investors",
                "fundingRound", "stage", "amountRaised"
            ])
            
            if funding:
                self._save_snapshot("funding", funding)
                logger.info(f"[Dropstab] Found {len(funding)} funding rounds from {path}")
                return funding
        
        logger.warning("[Dropstab] No funding found")
        return []
    
    async def scrape_investors(self) -> List[Dict]:
        """
        Scrape investor/VC list.
        Keys: name, portfolio, investments, type, tier
        """
        logger.info("[Dropstab] Scraping investors...")
        
        for path in ['/investors', '/funds', '/vcs']:
            html = await self._fetch(f"{BASE}{path}")
            if not html:
                continue
            
            data = self._extract_next_data(html)
            if not data:
                continue
            
            # Dynamic search for investor dataset
            investors = self._find_dataset(data, [
                "portfolio", "investments", "totalInvestments",
                "name", "tier", "type", "fund"
            ])
            
            if investors:
                self._save_snapshot("investors", investors)
                logger.info(f"[Dropstab] Found {len(investors)} investors from {path}")
                return investors
        
        logger.warning("[Dropstab] No investors found")
        return []
    
    async def scrape_all(self) -> Dict[str, Any]:
        """
        Run full scrape pipeline.
        Returns summary with all datasets.
        """
        start = time.time()
        
        coins = await self.scrape_coins()
        await asyncio.sleep(random.uniform(1, 2))
        
        unlocks = await self.scrape_unlocks()
        await asyncio.sleep(random.uniform(1, 2))
        
        funding = await self.scrape_funding()
        await asyncio.sleep(random.uniform(1, 2))
        
        investors = await self.scrape_investors()
        
        elapsed = time.time() - start
        
        result = {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "source": "dropstab_v2",
            "elapsed_sec": round(elapsed, 2),
            "datasets": {
                "coins": {
                    "count": len(coins),
                    "hash": self._compute_hash(coins) if coins else None,
                    "data": coins
                },
                "unlocks": {
                    "count": len(unlocks),
                    "hash": self._compute_hash(unlocks) if unlocks else None,
                    "data": unlocks
                },
                "funding": {
                    "count": len(funding),
                    "hash": self._compute_hash(funding) if funding else None,
                    "data": funding
                },
                "investors": {
                    "count": len(investors),
                    "hash": self._compute_hash(investors) if investors else None,
                    "data": investors
                }
            },
            "summary": {
                "coins": len(coins),
                "unlocks": len(unlocks),
                "funding": len(funding),
                "investors": len(investors)
            }
        }
        
        logger.info(f"[Dropstab] Scrape complete in {elapsed:.1f}s: "
                   f"coins={len(coins)}, unlocks={len(unlocks)}, "
                   f"funding={len(funding)}, investors={len(investors)}")
        
        return result


# Singleton instance
dropstab_scraper_v2 = DropstabScraperV2()
