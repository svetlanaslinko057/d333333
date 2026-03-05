"""
Dropstab BFF API Client
Uses internal API: https://extra-bff.dropstab.com

This is the real API that dropstab.com website uses.
Supports pagination - can fetch all ~15000 coins.

Endpoints:
- /coins - Market data with pagination
- /coins/{slug} - Coin details
- /categories - Categories/narratives
- /ecosystems - Blockchain ecosystems
- /trending - Trending tokens
- /gainers - Top gainers
- /losers - Top losers
- /unlock-events - Token unlocks
- /vesting/{slug} - Vesting schedule
- /funding - Funding rounds
- /investors - VC list
- /listings - Exchange listings
- /exchanges - Exchange list
"""

import asyncio
import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BASE_URL = "https://extra-bff.dropstab.com"


class DropstabClient:
    """
    Dropstab BFF API Client.
    Uses internal API endpoints with pagination support.
    """
    
    def __init__(self):
        self.base_url = BASE_URL
        self.timeout = 30.0
        self.min_interval = 0.3  # 300ms between requests
        self.last_request = 0
        self.max_retries = 5
        
        # Browser headers
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': 'https://dropstab.com',
            'Referer': 'https://dropstab.com/',
        }
    
    async def _rate_limit(self):
        """Enforce rate limiting"""
        now = datetime.now(timezone.utc).timestamp()
        diff = now - self.last_request
        if diff < self.min_interval:
            await asyncio.sleep(self.min_interval - diff)
        self.last_request = datetime.now(timezone.utc).timestamp()
    
    async def _request(
        self, 
        endpoint: str, 
        params: Optional[Dict] = None
    ) -> Optional[Any]:
        """Make request with retry"""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()
                
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    response = await client.get(url, headers=self.headers, params=params)
                    
                    if response.status_code == 200:
                        return response.json()
                    
                    if response.status_code == 429:
                        delay = (attempt + 1) * 3
                        logger.warning(f"[Dropstab] 429 Rate limited, waiting {delay}s...")
                        await asyncio.sleep(delay)
                        continue
                    
                    if response.status_code >= 500:
                        delay = (attempt + 1) * 2
                        logger.warning(f"[Dropstab] {response.status_code}, retry in {delay}s...")
                        await asyncio.sleep(delay)
                        continue
                    
                    logger.warning(f"[Dropstab] {endpoint} returned {response.status_code}")
                    return None
                    
            except Exception as e:
                logger.error(f"[Dropstab] {endpoint} error: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep((attempt + 1) * 2)
        
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # COINS / MARKET DATA
    # ═══════════════════════════════════════════════════════════════
    
    async def get_coins(
        self, 
        page: int = 1, 
        size: int = 100,
        sort: str = 'marketCap',
        order: str = 'desc'
    ) -> List[Dict]:
        """
        GET /coins - Paginated market data
        Returns: list of coins with price, mcap, volume, change
        """
        data = await self._request('/coins', {
            'page': page,
            'size': size,
            'sort': sort,
            'order': order
        })
        
        if not data:
            return []
        
        # Extract coins list
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get('coins', data.get('data', data.get('items', [])))
        return []
    
    async def get_coins_all(
        self, 
        size: int = 100, 
        max_pages: int = 150,
        sort: str = 'marketCap'
    ) -> List[Dict]:
        """
        Fetch ALL coins with pagination (~15000)
        """
        all_coins = []
        page = 1
        
        while page <= max_pages:
            coins = await self.get_coins(page=page, size=size, sort=sort)
            
            if not coins:
                break
            
            all_coins.extend(coins)
            logger.info(f"[Dropstab] Page {page}: {len(coins)} coins (total: {len(all_coins)})")
            
            if len(coins) < size:
                break
            
            page += 1
        
        return all_coins
    
    async def get_coin(self, slug: str) -> Optional[Dict]:
        """
        GET /coins/{slug} - Detailed coin info
        """
        return await self._request(f'/coins/{slug}')
    
    # ═══════════════════════════════════════════════════════════════
    # CATEGORIES & ECOSYSTEMS
    # ═══════════════════════════════════════════════════════════════
    
    async def get_categories(self) -> List[Dict]:
        """GET /categories - AI, GameFi, DePIN, etc"""
        data = await self._request('/categories')
        return self._extract_list(data)
    
    async def get_ecosystems(self) -> List[Dict]:
        """GET /ecosystems - Ethereum, Solana, etc"""
        data = await self._request('/ecosystems')
        return self._extract_list(data)
    
    # ═══════════════════════════════════════════════════════════════
    # TRENDING / GAINERS / LOSERS
    # ═══════════════════════════════════════════════════════════════
    
    async def get_trending(self) -> List[Dict]:
        """GET /trending"""
        data = await self._request('/trending')
        return self._extract_list(data)
    
    async def get_gainers(self) -> List[Dict]:
        """GET /gainers"""
        data = await self._request('/gainers')
        return self._extract_list(data)
    
    async def get_losers(self) -> List[Dict]:
        """GET /losers"""
        data = await self._request('/losers')
        return self._extract_list(data)
    
    # ═══════════════════════════════════════════════════════════════
    # TOKEN UNLOCKS
    # ═══════════════════════════════════════════════════════════════
    
    async def get_unlock_events(
        self, 
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict]:
        """
        GET /unlock-events
        Returns: token, unlockDate, unlockPercent, unlockUSD
        """
        params = {}
        if from_date:
            params['from'] = from_date
        if to_date:
            params['to'] = to_date
        
        data = await self._request('/unlock-events', params if params else None)
        return self._extract_list(data)
    
    async def get_vesting(self, slug: str) -> Optional[Dict]:
        """GET /vesting/{slug} - Vesting schedule"""
        return await self._request(f'/vesting/{slug}')
    
    # ═══════════════════════════════════════════════════════════════
    # FUNDING & INVESTORS
    # ═══════════════════════════════════════════════════════════════
    
    async def get_funding(self) -> List[Dict]:
        """GET /funding - Funding rounds"""
        data = await self._request('/funding')
        return self._extract_list(data)
    
    async def get_investors(self) -> List[Dict]:
        """GET /investors - VC list"""
        data = await self._request('/investors')
        return self._extract_list(data)
    
    # ═══════════════════════════════════════════════════════════════
    # LISTINGS & EXCHANGES
    # ═══════════════════════════════════════════════════════════════
    
    async def get_listings(self) -> List[Dict]:
        """GET /listings - Exchange listings"""
        data = await self._request('/listings')
        return self._extract_list(data)
    
    async def get_exchanges(self) -> List[Dict]:
        """GET /exchanges"""
        data = await self._request('/exchanges')
        return self._extract_list(data)
    
    # ═══════════════════════════════════════════════════════════════
    # SIGNALS & CHARTS
    # ═══════════════════════════════════════════════════════════════
    
    async def get_signals(self) -> List[Dict]:
        """GET /signals - Market signals"""
        data = await self._request('/signals')
        return self._extract_list(data)
    
    async def get_chart(self, slug: str) -> Optional[Dict]:
        """GET /charts/{slug} - Historical price"""
        return await self._request(f'/charts/{slug}')
    
    async def get_token_metrics(self, slug: str) -> Optional[Dict]:
        """GET /token-metrics/{slug}"""
        return await self._request(f'/token-metrics/{slug}')
    
    # ═══════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════
    
    def _extract_list(self, data: Any) -> List[Dict]:
        """Extract list from response"""
        if data is None:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ['data', 'items', 'list', 'results', 'coins', 
                       'categories', 'ecosystems', 'unlocks', 'investors',
                       'listings', 'exchanges', 'signals']:
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []


# Global instance
dropstab_client = DropstabClient()
