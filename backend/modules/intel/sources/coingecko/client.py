"""
CoinGecko API Client with Load Balancing
Supports multiple API instances for increased rate limits

Free tier: ~10-30 calls/minute per IP
With multiple instances: multiply rate limit
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import httpx
from dataclasses import dataclass, field
from collections import deque
import random

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"
PRO_BASE_URL = "https://pro-api.coingecko.com/api/v3"


@dataclass
class APIInstance:
    """Single CoinGecko API instance"""
    name: str
    api_key: Optional[str] = None
    base_url: str = BASE_URL
    rate_limit: int = 10  # calls per minute
    calls_made: deque = field(default_factory=lambda: deque(maxlen=100))
    is_healthy: bool = True
    last_error: Optional[str] = None
    consecutive_errors: int = 0
    
    def can_make_request(self) -> bool:
        """Check if instance can make a request based on rate limit"""
        if not self.is_healthy:
            return False
        
        now = datetime.now(timezone.utc).timestamp()
        # Count calls in last 60 seconds
        recent_calls = sum(1 for t in self.calls_made if now - t < 60)
        return recent_calls < self.rate_limit
    
    def record_call(self, success: bool = True, error: Optional[str] = None):
        """Record API call"""
        self.calls_made.append(datetime.now(timezone.utc).timestamp())
        
        if success:
            self.consecutive_errors = 0
            self.is_healthy = True
        else:
            self.consecutive_errors += 1
            self.last_error = error
            # Mark unhealthy after 3 consecutive errors
            if self.consecutive_errors >= 3:
                self.is_healthy = False
                logger.warning(f"[CoinGecko] Instance {self.name} marked unhealthy")
    
    def get_headers(self) -> Dict[str, str]:
        """Get request headers"""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-cg-pro-api-key"] = self.api_key
        return headers


class CoinGeckoPool:
    """
    Pool of CoinGecko API instances for load balancing
    Automatically distributes requests across healthy instances
    """
    
    def __init__(self):
        self.instances: List[APIInstance] = []
        self.current_index = 0
        self._lock = asyncio.Lock()
    
    def add_instance(
        self, 
        name: str, 
        api_key: Optional[str] = None,
        rate_limit: int = 10
    ):
        """Add API instance to pool"""
        base_url = PRO_BASE_URL if api_key else BASE_URL
        instance = APIInstance(
            name=name,
            api_key=api_key,
            base_url=base_url,
            rate_limit=rate_limit
        )
        self.instances.append(instance)
        logger.info(f"[CoinGecko] Added instance: {name} (rate_limit={rate_limit})")
    
    def get_available_instance(self) -> Optional[APIInstance]:
        """Get next available instance using round-robin with health check"""
        if not self.instances:
            return None
        
        # Try all instances starting from current
        for _ in range(len(self.instances)):
            instance = self.instances[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.instances)
            
            if instance.can_make_request():
                return instance
        
        return None
    
    def get_random_healthy_instance(self) -> Optional[APIInstance]:
        """Get random healthy instance"""
        healthy = [i for i in self.instances if i.is_healthy and i.can_make_request()]
        return random.choice(healthy) if healthy else None
    
    def get_total_rate_limit(self) -> int:
        """Get combined rate limit of all healthy instances"""
        return sum(i.rate_limit for i in self.instances if i.is_healthy)
    
    def get_status(self) -> Dict[str, Any]:
        """Get pool status"""
        return {
            'total_instances': len(self.instances),
            'healthy_instances': sum(1 for i in self.instances if i.is_healthy),
            'total_rate_limit': self.get_total_rate_limit(),
            'instances': [
                {
                    'name': i.name,
                    'healthy': i.is_healthy,
                    'rate_limit': i.rate_limit,
                    'has_api_key': bool(i.api_key),
                    'recent_calls': len([t for t in i.calls_made 
                                        if datetime.now(timezone.utc).timestamp() - t < 60]),
                    'last_error': i.last_error
                }
                for i in self.instances
            ]
        }
    
    def reset_unhealthy(self):
        """Reset unhealthy instances for retry"""
        for instance in self.instances:
            if not instance.is_healthy:
                instance.is_healthy = True
                instance.consecutive_errors = 0
                logger.info(f"[CoinGecko] Reset instance: {instance.name}")


class CoinGeckoClient:
    """
    CoinGecko API Client with automatic load balancing
    """
    
    def __init__(self, pool: CoinGeckoPool):
        self.pool = pool
        self.timeout = 30.0
    
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict] = None,
        retry_count: int = 3
    ) -> Optional[Any]:
        """Make request with automatic instance selection and retry"""
        
        for attempt in range(retry_count):
            instance = self.pool.get_available_instance()
            
            if not instance:
                # All instances busy, wait a bit
                logger.warning("[CoinGecko] All instances busy, waiting...")
                await asyncio.sleep(2)
                continue
            
            url = f"{instance.base_url}{endpoint}"
            
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        params=params,
                        headers=instance.get_headers()
                    )
                    
                    if response.status_code == 429:
                        # Rate limited
                        logger.warning(f"[CoinGecko] Rate limited on {instance.name}")
                        instance.record_call(False, "429 Rate Limited")
                        await asyncio.sleep(5)
                        continue
                    
                    if response.status_code >= 500:
                        # Server error
                        instance.record_call(False, f"{response.status_code} Server Error")
                        continue
                    
                    response.raise_for_status()
                    instance.record_call(True)
                    return response.json()
                    
            except httpx.TimeoutException:
                logger.warning(f"[CoinGecko] Timeout on {instance.name}")
                instance.record_call(False, "Timeout")
            except Exception as e:
                logger.error(f"[CoinGecko] Error on {instance.name}: {e}")
                instance.record_call(False, str(e))
        
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # COIN DATA ENDPOINTS
    # ═══════════════════════════════════════════════════════════════
    
    async def ping(self) -> bool:
        """Check API status"""
        data = await self._request("GET", "/ping")
        return data is not None
    
    async def get_coin(self, coin_id: str) -> Optional[Dict]:
        """
        Get coin data by ID
        Returns: market_data, description, links, categories, etc.
        """
        return await self._request(
            "GET", 
            f"/coins/{coin_id}",
            params={
                'localization': 'false',
                'tickers': 'false',
                'market_data': 'true',
                'community_data': 'false',
                'developer_data': 'false',
                'sparkline': 'false'
            }
        )
    
    async def get_coin_market_data(
        self, 
        coin_ids: List[str],
        vs_currency: str = 'usd'
    ) -> List[Dict]:
        """
        Get market data for multiple coins
        More efficient than individual calls
        """
        ids_str = ','.join(coin_ids[:250])  # Max 250 per request
        
        data = await self._request(
            "GET",
            "/coins/markets",
            params={
                'ids': ids_str,
                'vs_currency': vs_currency,
                'order': 'market_cap_desc',
                'per_page': 250,
                'page': 1,
                'sparkline': 'false',
                'price_change_percentage': '24h,7d,30d'
            }
        )
        return data or []
    
    async def get_coin_list(self) -> List[Dict]:
        """Get list of all coins (id, symbol, name)"""
        return await self._request("GET", "/coins/list") or []
    
    async def get_markets(
        self,
        vs_currency: str = 'usd',
        order: str = 'market_cap_desc',
        per_page: int = 100,
        page: int = 1,
        category: Optional[str] = None
    ) -> List[Dict]:
        """Get market data with pagination"""
        params = {
            'vs_currency': vs_currency,
            'order': order,
            'per_page': per_page,
            'page': page,
            'sparkline': 'false',
            'price_change_percentage': '24h,7d,30d'
        }
        if category:
            params['category'] = category
        
        return await self._request("GET", "/coins/markets", params) or []
    
    async def search(self, query: str) -> Optional[Dict]:
        """Search for coins, categories, exchanges"""
        return await self._request("GET", "/search", {'query': query})
    
    # ═══════════════════════════════════════════════════════════════
    # GLOBAL DATA
    # ═══════════════════════════════════════════════════════════════
    
    async def get_global(self) -> Optional[Dict]:
        """Get global crypto market data"""
        data = await self._request("GET", "/global")
        return data.get('data') if data else None
    
    async def get_global_defi(self) -> Optional[Dict]:
        """Get global DeFi data"""
        data = await self._request("GET", "/global/decentralized_finance_defi")
        return data.get('data') if data else None
    
    # ═══════════════════════════════════════════════════════════════
    # CATEGORIES
    # ═══════════════════════════════════════════════════════════════
    
    async def get_categories(self) -> List[Dict]:
        """Get all categories with market data"""
        return await self._request("GET", "/coins/categories") or []
    
    async def get_categories_list(self) -> List[Dict]:
        """Get categories list (id, name only)"""
        return await self._request("GET", "/coins/categories/list") or []
    
    # ═══════════════════════════════════════════════════════════════
    # TRENDING
    # ═══════════════════════════════════════════════════════════════
    
    async def get_trending(self) -> Optional[Dict]:
        """Get trending coins, NFTs, categories"""
        return await self._request("GET", "/search/trending")
    
    # ═══════════════════════════════════════════════════════════════
    # HISTORICAL
    # ═══════════════════════════════════════════════════════════════
    
    async def get_coin_history(
        self, 
        coin_id: str, 
        date: str  # dd-mm-yyyy
    ) -> Optional[Dict]:
        """Get historical data for specific date"""
        return await self._request(
            "GET",
            f"/coins/{coin_id}/history",
            params={'date': date, 'localization': 'false'}
        )
    
    async def get_market_chart(
        self,
        coin_id: str,
        vs_currency: str = 'usd',
        days: int = 30
    ) -> Optional[Dict]:
        """Get OHLC chart data"""
        return await self._request(
            "GET",
            f"/coins/{coin_id}/market_chart",
            params={
                'vs_currency': vs_currency,
                'days': days
            }
        )


# ═══════════════════════════════════════════════════════════════
# GLOBAL POOL INSTANCE
# ═══════════════════════════════════════════════════════════════

# Create default pool with free instances
coingecko_pool = CoinGeckoPool()

# Add default free instances (can be extended via admin API)
coingecko_pool.add_instance("free_1", rate_limit=10)
coingecko_pool.add_instance("free_2", rate_limit=10)
coingecko_pool.add_instance("free_3", rate_limit=10)

# Create default client
coingecko_client = CoinGeckoClient(coingecko_pool)
