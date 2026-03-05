"""
Global Proxy Manager with Failover
- Multiple proxies with priority order
- Automatic failover (not rotation!)
- Admin API for management
"""

import os
import logging
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Proxy configuration"""
    id: int
    server: str
    priority: int = 1
    enabled: bool = True
    username: Optional[str] = None
    password: Optional[str] = None
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    success_count: int = 0
    error_count: int = 0
    
    @property
    def url(self) -> str:
        """Get proxy URL for requests library"""
        if self.username and self.password:
            if "://" in self.server:
                proto, rest = self.server.split("://", 1)
                return f"{proto}://{self.username}:{self.password}@{rest}"
            return f"http://{self.username}:{self.password}@{self.server}"
        return self.server
    
    @property
    def requests_format(self) -> Dict[str, str]:
        """Get proxy dict for requests library"""
        return {"http": self.url, "https": self.url}
    
    @property
    def playwright_format(self) -> Dict[str, Any]:
        """Get proxy dict for Playwright"""
        config = {"server": self.server}
        if self.username:
            config["username"] = self.username
        if self.password:
            config["password"] = self.password
        return config
    
    @property
    def httpx_format(self) -> str:
        """Get proxy URL for httpx"""
        return self.url


class ProxyManager:
    """
    Proxy Manager with Failover (NOT rotation!)
    
    Architecture:
    - Primary proxy used by default
    - If fails → automatic switch to backup
    - Order matters: 1 → 2 → 3
    - Admin can add/remove/reorder proxies
    
    Usage:
        # For requests with failover
        result = proxy_manager.request_with_failover(
            lambda proxy: requests.get(url, proxies=proxy, timeout=30)
        )
        
        # Get current best proxy for Playwright
        proxy = proxy_manager.get_playwright_proxy()
    """
    
    def __init__(self):
        self._proxies: List[ProxyConfig] = []
        self._next_id = 1
        self._load_from_env()
    
    def _load_from_env(self):
        """Load proxies from environment"""
        # Primary proxy
        proxy_url = os.getenv("GLOBAL_PROXY")
        if proxy_url:
            self._add_proxy_from_url(proxy_url, priority=1)
        
        # Backup proxies
        proxy2 = os.getenv("GLOBAL_PROXY_2")
        if proxy2:
            self._add_proxy_from_url(proxy2, priority=2)
        
        proxy3 = os.getenv("GLOBAL_PROXY_3")
        if proxy3:
            self._add_proxy_from_url(proxy3, priority=3)
        
        if self._proxies:
            logger.info(f"[Proxy] Loaded {len(self._proxies)} proxies from env")
        else:
            logger.info("[Proxy] No proxies configured - direct connection")
    
    def _add_proxy_from_url(self, url: str, priority: int):
        """Parse proxy URL and add to list"""
        try:
            username = None
            password = None
            server = url
            
            if "@" in url:
                proto_auth, host_port = url.rsplit("@", 1)
                proto, auth = proto_auth.split("://", 1)
                username, password = auth.split(":", 1)
                server = f"{proto}://{host_port}"
            
            proxy = ProxyConfig(
                id=self._next_id,
                server=server,
                priority=priority,
                username=username,
                password=password
            )
            self._proxies.append(proxy)
            self._next_id += 1
            
        except Exception as e:
            logger.error(f"[Proxy] Failed to parse: {e}")
    
    def _get_sorted_proxies(self) -> List[ProxyConfig]:
        """Get proxies sorted by priority (lower = higher priority)"""
        return sorted(
            [p for p in self._proxies if p.enabled],
            key=lambda x: x.priority
        )
    
    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════════
    
    @property
    def is_configured(self) -> bool:
        """Check if any proxy is configured"""
        return len(self._proxies) > 0
    
    @property
    def has_enabled_proxy(self) -> bool:
        """Check if any proxy is enabled"""
        return any(p.enabled for p in self._proxies)
    
    def get_primary_proxy(self) -> Optional[ProxyConfig]:
        """Get highest priority enabled proxy"""
        proxies = self._get_sorted_proxies()
        return proxies[0] if proxies else None
    
    def get_requests_proxy(self) -> Optional[Dict[str, str]]:
        """Get proxy for requests library"""
        proxy = self.get_primary_proxy()
        return proxy.requests_format if proxy else None
    
    def get_playwright_proxy(self) -> Optional[Dict[str, Any]]:
        """Get proxy for Playwright"""
        proxy = self.get_primary_proxy()
        return proxy.playwright_format if proxy else None
    
    def get_httpx_proxy(self) -> Optional[str]:
        """Get proxy for httpx"""
        proxy = self.get_primary_proxy()
        return proxy.httpx_format if proxy else None
    
    def request_with_failover(self, func: Callable[[Dict[str, str]], Any]) -> Any:
        """
        Execute request with automatic proxy failover.
        
        Args:
            func: Function that takes proxy dict and makes request
            
        Returns:
            Result from successful request
            
        Raises:
            Exception if all proxies fail
        """
        proxies = self._get_sorted_proxies()
        
        if not proxies:
            # No proxy - direct connection
            return func(None)
        
        last_error = None
        
        for proxy in proxies:
            try:
                result = func(proxy.requests_format)
                
                # Success - update stats
                proxy.last_success = datetime.now(timezone.utc)
                proxy.success_count += 1
                proxy.last_error = None
                
                return result
                
            except Exception as e:
                proxy.last_error = str(e)
                proxy.error_count += 1
                last_error = e
                logger.warning(f"[Proxy] Proxy {proxy.id} failed: {e}, trying next...")
                continue
        
        raise Exception(f"All proxies failed. Last error: {last_error}")
    
    # ═══════════════════════════════════════════════════════════════
    # ADMIN API
    # ═══════════════════════════════════════════════════════════════
    
    def add_proxy(self, server: str, username: str = None, password: str = None, priority: int = None) -> Dict:
        """Add new proxy"""
        if priority is None:
            priority = max([p.priority for p in self._proxies], default=0) + 1
        
        proxy = ProxyConfig(
            id=self._next_id,
            server=server,
            priority=priority,
            username=username,
            password=password
        )
        self._proxies.append(proxy)
        self._next_id += 1
        
        logger.info(f"[Proxy] Added proxy {proxy.id}: {server}")
        return {"id": proxy.id, "priority": priority}
    
    def remove_proxy(self, proxy_id: int) -> Dict:
        """Remove proxy by ID"""
        self._proxies = [p for p in self._proxies if p.id != proxy_id]
        logger.info(f"[Proxy] Removed proxy {proxy_id}")
        return {"removed": proxy_id}
    
    def set_priority(self, proxy_id: int, priority: int) -> Dict:
        """Set proxy priority"""
        for proxy in self._proxies:
            if proxy.id == proxy_id:
                proxy.priority = priority
                return {"id": proxy_id, "priority": priority}
        return {"error": f"Proxy {proxy_id} not found"}
    
    def enable_proxy(self, proxy_id: int) -> Dict:
        """Enable proxy"""
        for proxy in self._proxies:
            if proxy.id == proxy_id:
                proxy.enabled = True
                return {"id": proxy_id, "enabled": True}
        return {"error": f"Proxy {proxy_id} not found"}
    
    def disable_proxy(self, proxy_id: int) -> Dict:
        """Disable proxy"""
        for proxy in self._proxies:
            if proxy.id == proxy_id:
                proxy.enabled = False
                return {"id": proxy_id, "enabled": False}
        return {"error": f"Proxy {proxy_id} not found"}
    
    def get_status(self) -> Dict[str, Any]:
        """Get full proxy status"""
        return {
            "configured": self.is_configured,
            "total": len(self._proxies),
            "enabled": len([p for p in self._proxies if p.enabled]),
            "proxies": [
                {
                    "id": p.id,
                    "server": p.server,
                    "priority": p.priority,
                    "enabled": p.enabled,
                    "has_auth": bool(p.username),
                    "success_count": p.success_count,
                    "error_count": p.error_count,
                    "last_success": p.last_success.isoformat() if p.last_success else None,
                    "last_error": p.last_error
                }
                for p in sorted(self._proxies, key=lambda x: x.priority)
            ]
        }
    
    def get_list(self) -> List[Dict]:
        """Get proxy list for admin"""
        return self.get_status()["proxies"]


# Singleton instance
proxy_manager = ProxyManager()
