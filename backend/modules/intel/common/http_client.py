"""
HTTP Client with retry, rate limiting, and error handling
"""

import asyncio
import httpx
import logging
from typing import Optional, Dict, Any
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter"""
    def __init__(self, min_interval_ms: int = 800):
        self.min_interval = min_interval_ms / 1000
        self.last_request = 0
    
    async def wait(self):
        now = time.time()
        diff = now - self.last_request
        if diff < self.min_interval:
            await asyncio.sleep(self.min_interval - diff)
        self.last_request = time.time()


class HttpClient:
    """
    HTTP client with:
    - Rate limiting
    - Exponential backoff retry
    - Proper headers
    """
    
    def __init__(
        self,
        base_url: str,
        timeout_ms: int = 20000,
        min_interval_ms: int = 800,
        max_retries: int = 3
    ):
        self.base_url = base_url
        self.timeout = timeout_ms / 1000
        self.max_retries = max_retries
        self.limiter = RateLimiter(min_interval_ms)
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': 'https://dropstab.com',
            'Referer': 'https://dropstab.com/',
        }
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        body: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Any:
        """Make request with retry logic"""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(self.max_retries + 1):
            try:
                await self.limiter.wait()
                
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    if method == 'GET':
                        res = await client.get(url, headers=self.headers, params=params)
                    else:
                        res = await client.post(url, headers=self.headers, json=body or {})
                    
                    if res.status_code == 200:
                        return res.json()
                    
                    if res.status_code in [429, 500, 502, 503, 504]:
                        raise httpx.HTTPStatusError(
                            f"Status {res.status_code}",
                            request=res.request,
                            response=res
                        )
                    
                    # Other errors - don't retry
                    logger.warning(f"[HTTP] {method} {endpoint} returned {res.status_code}")
                    return None
                    
            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < self.max_retries:
                    delay = min(4, 0.4 * (2 ** attempt)) + (asyncio.get_event_loop().time() % 0.15)
                    logger.debug(f"[HTTP] Retry {attempt + 1}/{self.max_retries} after {delay:.1f}s")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"[HTTP] {method} {endpoint} failed after {self.max_retries} retries: {e}")
                    raise
        
        return None
    
    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        return await self._request('GET', endpoint, params=params)
    
    async def post(self, endpoint: str, body: Optional[Dict] = None) -> Any:
        return await self._request('POST', endpoint, body=body)
