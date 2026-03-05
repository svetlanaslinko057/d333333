"""
Global Proxy Manager
Single proxy for all scrapers - simple and controllable
"""

import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Proxy configuration"""
    server: str
    username: Optional[str] = None
    password: Optional[str] = None
    
    @property
    def url(self) -> str:
        """Get proxy URL for requests library"""
        if self.username and self.password:
            # Parse server to insert auth
            if "://" in self.server:
                proto, rest = self.server.split("://", 1)
                return f"{proto}://{self.username}:{self.password}@{rest}"
            return f"http://{self.username}:{self.password}@{self.server}"
        return self.server
    
    @property
    def requests_format(self) -> Dict[str, str]:
        """Get proxy dict for requests library"""
        return {
            "http": self.url,
            "https": self.url
        }
    
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
    Global proxy manager for all scrapers.
    
    Simple architecture:
    - One proxy for everything
    - Manual change when blocked
    - No rotation, no pools
    
    Usage:
        from proxy_manager import proxy_manager
        
        # For requests
        proxies = proxy_manager.get_requests_proxy()
        r = requests.get(url, proxies=proxies)
        
        # For Playwright
        proxy = proxy_manager.get_playwright_proxy()
        browser = p.chromium.launch(proxy=proxy)
        
        # For httpx
        proxy = proxy_manager.get_httpx_proxy()
        async with httpx.AsyncClient(proxy=proxy) as client:
            ...
    """
    
    def __init__(self):
        self._proxy: Optional[ProxyConfig] = None
        self._load_from_env()
    
    def _load_from_env(self):
        """Load proxy from environment"""
        proxy_url = os.getenv("GLOBAL_PROXY")
        
        if not proxy_url:
            logger.info("[Proxy] No GLOBAL_PROXY configured - direct connection")
            return
        
        # Parse proxy URL
        # Format: http://user:pass@host:port or http://host:port
        try:
            if "@" in proxy_url:
                # Has auth
                proto_auth, host_port = proxy_url.rsplit("@", 1)
                proto, auth = proto_auth.split("://", 1)
                username, password = auth.split(":", 1)
                server = f"{proto}://{host_port}"
                
                self._proxy = ProxyConfig(
                    server=server,
                    username=username,
                    password=password
                )
            else:
                self._proxy = ProxyConfig(server=proxy_url)
            
            logger.info(f"[Proxy] Configured: {self._proxy.server}")
            
        except Exception as e:
            logger.error(f"[Proxy] Failed to parse GLOBAL_PROXY: {e}")
    
    def set_proxy(self, server: str, username: str = None, password: str = None):
        """Manually set proxy"""
        self._proxy = ProxyConfig(
            server=server,
            username=username,
            password=password
        )
        logger.info(f"[Proxy] Set to: {server}")
    
    def clear_proxy(self):
        """Clear proxy - use direct connection"""
        self._proxy = None
        logger.info("[Proxy] Cleared - using direct connection")
    
    @property
    def is_configured(self) -> bool:
        """Check if proxy is configured"""
        return self._proxy is not None
    
    def get_requests_proxy(self) -> Optional[Dict[str, str]]:
        """Get proxy for requests library"""
        if not self._proxy:
            return None
        return self._proxy.requests_format
    
    def get_playwright_proxy(self) -> Optional[Dict[str, Any]]:
        """Get proxy for Playwright"""
        if not self._proxy:
            return None
        return self._proxy.playwright_format
    
    def get_httpx_proxy(self) -> Optional[str]:
        """Get proxy for httpx"""
        if not self._proxy:
            return None
        return self._proxy.httpx_format
    
    def get_status(self) -> Dict[str, Any]:
        """Get proxy status"""
        return {
            "configured": self.is_configured,
            "server": self._proxy.server if self._proxy else None,
            "has_auth": bool(self._proxy and self._proxy.username)
        }


# Singleton instance
proxy_manager = ProxyManager()
