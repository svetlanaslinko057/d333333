"""
Replay Client
Replays captured requests with full blueprint
"""

import logging
import requests
import httpx
from typing import Any, Dict, Optional, Tuple

from .models import CapturedRequest
from ..common.proxy_manager import proxy_manager

logger = logging.getLogger(__name__)


class ReplayClient:
    """
    Replays captured requests exactly as they were captured.
    
    Features:
    - Full header/cookie/body replay
    - Proxy support with failover
    - Sync and async variants
    """
    
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
    
    def replay_sync(self, req: CapturedRequest) -> Tuple[bool, Any]:
        """
        Replay request synchronously.
        
        Returns:
            (success, payload_or_error)
        """
        try:
            kwargs = req.to_requests_kwargs()
            kwargs["timeout"] = self.timeout
            
            # Add proxy if configured
            proxy = proxy_manager.get_requests_proxy()
            if proxy:
                kwargs["proxies"] = proxy
            
            # Make request
            response = requests.request(**kwargs)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    return (True, data)
                except:
                    return (True, response.text)
            else:
                return (False, f"HTTP {response.status_code}")
                
        except Exception as e:
            return (False, str(e))
    
    async def replay_async(self, req: CapturedRequest) -> Tuple[bool, Any]:
        """
        Replay request asynchronously.
        """
        try:
            kwargs = {
                "method": req.method,
                "url": req.url,
                "headers": req._clean_headers(),
                "timeout": self.timeout
            }
            
            if req.body:
                try:
                    kwargs["json"] = __import__("json").loads(req.body)
                except:
                    kwargs["content"] = req.body
            
            if req.cookies:
                kwargs["cookies"] = req.cookies
            
            # Add proxy
            proxy = proxy_manager.get_httpx_proxy()
            
            async with httpx.AsyncClient(proxy=proxy) as client:
                response = await client.request(**kwargs)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        return (True, data)
                    except:
                        return (True, response.text)
                else:
                    return (False, f"HTTP {response.status_code}")
                    
        except Exception as e:
            return (False, str(e))
    
    def replay_with_failover(self, requests_list: list[CapturedRequest]) -> Tuple[CapturedRequest, Any]:
        """
        Try multiple endpoints until one succeeds.
        
        Returns:
            (successful_request, payload)
        """
        for req in requests_list:
            success, result = self.replay_sync(req)
            if success:
                return (req, result)
            logger.warning(f"[Replay] Failed: {req.url[:60]} -> {result}")
        
        raise Exception("All endpoints failed")


# Singleton
replay_client = ReplayClient()
