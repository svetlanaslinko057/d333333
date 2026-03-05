"""
Dropstab SSR Scraper
Extracts data from Next.js __NEXT_DATA__ embedded in HTML pages

This is the correct way to scrape Dropstab - they use Server-Side Rendering,
so all data is already in the HTML, not fetched via API.

Pages to scrape:
- /coins - All projects with market data
- /vesting - Token unlocks  
- /categories - Category breakdown
- /top-performance - Gainers/losers
- /investors - VC list
- /latest-fundraising-rounds - Funding rounds
"""

import asyncio
import httpx
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://dropstab.com"


class DropstabScraper:
    """
    Scraper for Dropstab using Next.js SSR data extraction.
    
    No API key needed - extracts data from __NEXT_DATA__ script tag.
    """
    
    def __init__(self):
        self.timeout = 30.0
        self.min_interval = 1.0  # 1 second between requests (be nice)
        self.last_request = 0
        self.max_retries = 3
        
        # Browser headers
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    async def _rate_limit(self):
        """Enforce rate limiting"""
        now = datetime.now(timezone.utc).timestamp()
        diff = now - self.last_request
        if diff < self.min_interval:
            await asyncio.sleep(self.min_interval - diff)
        self.last_request = datetime.now(timezone.utc).timestamp()
    
    async def _fetch_page(self, path: str) -> Optional[str]:
        """Fetch HTML page"""
        url = f"{BASE_URL}{path}"
        
        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()
                
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    response = await client.get(url, headers=self.headers)
                    
                    if response.status_code == 200:
                        logger.info(f"[Dropstab] Fetched {path} ({len(response.text)} bytes)")
                        return response.text
                    
                    if response.status_code == 429:
                        delay = (attempt + 1) * 5
                        logger.warning(f"[Dropstab] 429 Rate limited, waiting {delay}s...")
                        await asyncio.sleep(delay)
                        continue
                    
                    logger.warning(f"[Dropstab] {path} returned {response.status_code}")
                    
            except Exception as e:
                logger.error(f"[Dropstab] {path} error: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep((attempt + 1) * 2)
        
        return None
    
    def _extract_next_data(self, html: str) -> Optional[Dict]:
        """Extract __NEXT_DATA__ JSON from HTML"""
        try:
            soup = BeautifulSoup(html, 'lxml')
            script = soup.find('script', id='__NEXT_DATA__')
            
            if script and script.string:
                data = json.loads(script.string)
                logger.debug(f"[Dropstab] Extracted __NEXT_DATA__ keys: {list(data.keys())}")
                return data
            
            logger.warning("[Dropstab] No __NEXT_DATA__ found in page")
            return None
            
        except Exception as e:
            logger.error(f"[Dropstab] Failed to parse __NEXT_DATA__: {e}")
            return None
    
    def _get_page_props(self, next_data: Dict) -> Dict:
        """Extract pageProps from Next.js data"""
        try:
            return next_data.get('props', {}).get('pageProps', {})
        except:
            return {}
    
    # ═══════════════════════════════════════════════════════════════
    # SCRAPE METHODS
    # ═══════════════════════════════════════════════════════════════
    
    async def scrape_coins_page(self, page: int = 1) -> List[Dict]:
        """
        Scrape single page of coins
        Page 1: / (home page has first 100)
        Page 2+: /?page=N
        """
        # Dropstab homepage has coins, not /coins path
        if page == 1:
            path = '/'
        else:
            path = f'/?page={page}'
        
        html = await self._fetch_page(path)
        if not html:
            return []
        
        next_data = self._extract_next_data(html)
        if not next_data:
            return []
        
        page_props = self._get_page_props(next_data)
        
        # Main data is in coinsBody.coins
        coins_body = page_props.get('coinsBody', {})
        coins = coins_body.get('coins', [])
        
        if coins:
            logger.info(f"[Dropstab] Page {page}: scraped {len(coins)} coins")
            return coins
        
        # Fallback: check other fields
        for key in ['fallbackCoins', 'market', 'data']:
            fallback = page_props.get(key)
            if isinstance(fallback, dict):
                fallback = fallback.get('coins', [])
            if fallback and isinstance(fallback, list) and len(fallback) > 0:
                logger.info(f"[Dropstab] Page {page}: scraped {len(fallback)} coins from {key}")
                return fallback
        
        logger.warning(f"[Dropstab] Page {page}: no coin data found")
        return []
    
    async def scrape_coins(self, max_pages: int = 1) -> List[Dict]:
        """
        Scrape coins with pagination
        Default: 1 page (~100 coins) for quick sync
        Full sync: max_pages=200 (~15000+ coins)
        """
        all_coins = []
        
        for page in range(1, max_pages + 1):
            coins = await self.scrape_coins_page(page)
            
            if not coins:
                logger.info(f"[Dropstab] Pagination complete at page {page-1}")
                break
            
            all_coins.extend(coins)
            
            # Log progress every 10 pages
            if page % 10 == 0:
                logger.info(f"[Dropstab] Progress: {len(all_coins)} coins scraped ({page} pages)")
        
        logger.info(f"[Dropstab] Total scraped: {len(all_coins)} coins from {min(page, max_pages)} pages")
        return all_coins
    
    async def scrape_coins_full(self, max_pages: int = 200) -> List[Dict]:
        """
        Full market scrape - get all coins (15000+)
        Use this for daily full sync
        """
        logger.info(f"[Dropstab] Starting FULL market scrape (up to {max_pages} pages)...")
        return await self.scrape_coins(max_pages=max_pages)
    
    async def scrape_vesting(self) -> List[Dict]:
        """
        Scrape /vesting page - token unlocks
        Returns: list of upcoming unlock events
        """
        html = await self._fetch_page('/vesting')
        if not html:
            return []
        
        next_data = self._extract_next_data(html)
        if not next_data:
            return []
        
        page_props = self._get_page_props(next_data)
        
        unlocks = (
            page_props.get('unlocks') or
            page_props.get('vestingEvents') or
            page_props.get('events') or
            page_props.get('data') or
            []
        )
        
        # Check dehydratedState
        if not unlocks:
            dehydrated = page_props.get('dehydratedState', {})
            queries = dehydrated.get('queries', [])
            for query in queries:
                state = query.get('state', {})
                data = state.get('data', {})
                if isinstance(data, dict):
                    unlocks = data.get('unlocks', data.get('events', data.get('data', [])))
                    if unlocks:
                        break
        
        logger.info(f"[Dropstab] Scraped {len(unlocks)} unlock events from /vesting")
        return unlocks if isinstance(unlocks, list) else []
    
    async def scrape_categories(self) -> List[Dict]:
        """
        Scrape /categories page
        Returns: list of categories (AI, DePIN, GameFi, etc)
        """
        html = await self._fetch_page('/categories')
        if not html:
            return []
        
        next_data = self._extract_next_data(html)
        if not next_data:
            return []
        
        page_props = self._get_page_props(next_data)
        
        categories = (
            page_props.get('categories') or
            page_props.get('data') or
            []
        )
        
        logger.info(f"[Dropstab] Scraped {len(categories)} categories")
        return categories if isinstance(categories, list) else []
    
    async def scrape_top_performance(self) -> Dict[str, List]:
        """
        Scrape /top-performance page - gainers and losers
        Returns: dict with 'gainers' and 'losers' lists
        """
        html = await self._fetch_page('/top-performance')
        if not html:
            return {'gainers': [], 'losers': []}
        
        next_data = self._extract_next_data(html)
        if not next_data:
            return {'gainers': [], 'losers': []}
        
        page_props = self._get_page_props(next_data)
        
        result = {
            'gainers': page_props.get('gainers', page_props.get('topGainers', [])),
            'losers': page_props.get('losers', page_props.get('topLosers', []))
        }
        
        logger.info(f"[Dropstab] Scraped {len(result['gainers'])} gainers, {len(result['losers'])} losers")
        return result
    
    async def scrape_investors(self) -> List[Dict]:
        """
        Scrape /investors page - VC and fund list
        Returns: list of investors
        """
        html = await self._fetch_page('/investors')
        if not html:
            return []
        
        next_data = self._extract_next_data(html)
        if not next_data:
            return []
        
        page_props = self._get_page_props(next_data)
        
        investors = (
            page_props.get('investors') or
            page_props.get('data') or
            []
        )
        
        # Check dehydratedState
        if not investors:
            dehydrated = page_props.get('dehydratedState', {})
            queries = dehydrated.get('queries', [])
            for query in queries:
                state = query.get('state', {})
                data = state.get('data', {})
                if isinstance(data, dict):
                    investors = data.get('investors', data.get('data', []))
                    if investors:
                        break
        
        logger.info(f"[Dropstab] Scraped {len(investors)} investors")
        return investors if isinstance(investors, list) else []
    
    async def scrape_fundraising(self) -> List[Dict]:
        """
        Scrape /latest-fundraising-rounds page
        Returns: list of recent funding rounds
        """
        html = await self._fetch_page('/latest-fundraising-rounds')
        if not html:
            return []
        
        next_data = self._extract_next_data(html)
        if not next_data:
            return []
        
        page_props = self._get_page_props(next_data)
        
        rounds = (
            page_props.get('rounds') or
            page_props.get('fundraisingRounds') or
            page_props.get('data') or
            []
        )
        
        logger.info(f"[Dropstab] Scraped {len(rounds)} funding rounds")
        return rounds if isinstance(rounds, list) else []
    
    async def scrape_activities(self) -> List[Dict]:
        """
        Scrape /activities page - listings, launches, events
        Returns: list of activities
        """
        html = await self._fetch_page('/activities')
        if not html:
            return []
        
        next_data = self._extract_next_data(html)
        if not next_data:
            return []
        
        page_props = self._get_page_props(next_data)
        
        activities = (
            page_props.get('activities') or
            page_props.get('events') or
            page_props.get('data') or
            []
        )
        
        logger.info(f"[Dropstab] Scraped {len(activities)} activities")
        return activities if isinstance(activities, list) else []
    
    async def scrape_coin_detail(self, slug: str) -> Optional[Dict]:
        """
        Scrape /coins/{slug} page - detailed coin info
        Returns: coin details with full data
        """
        html = await self._fetch_page(f'/coins/{slug}')
        if not html:
            return None
        
        next_data = self._extract_next_data(html)
        if not next_data:
            return None
        
        page_props = self._get_page_props(next_data)
        
        coin = (
            page_props.get('coin') or
            page_props.get('currency') or
            page_props.get('data') or
            page_props
        )
        
        logger.info(f"[Dropstab] Scraped coin detail: {slug}")
        return coin if isinstance(coin, dict) else None
    
    async def scrape_all(self) -> Dict[str, Any]:
        """
        Scrape all available data from Dropstab
        Returns: dict with all datasets
        """
        logger.info("[Dropstab] Starting full scrape...")
        
        results = {
            'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
            'source': 'dropstab_ssr'
        }
        
        # Scrape each page
        results['coins'] = await self.scrape_coins()
        results['unlocks'] = await self.scrape_vesting()
        results['categories'] = await self.scrape_categories()
        
        perf = await self.scrape_top_performance()
        results['gainers'] = perf['gainers']
        results['losers'] = perf['losers']
        
        results['investors'] = await self.scrape_investors()
        results['fundraising'] = await self.scrape_fundraising()
        results['activities'] = await self.scrape_activities()
        
        # Summary
        results['summary'] = {
            'coins': len(results['coins']),
            'unlocks': len(results['unlocks']),
            'categories': len(results['categories']),
            'gainers': len(results['gainers']),
            'losers': len(results['losers']),
            'investors': len(results['investors']),
            'fundraising': len(results['fundraising']),
            'activities': len(results['activities'])
        }
        
        logger.info(f"[Dropstab] Full scrape complete: {results['summary']}")
        return results


# Global instance
dropstab_scraper = DropstabScraper()
