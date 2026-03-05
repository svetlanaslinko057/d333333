"""
Browser Discovery
Captures full request blueprints from browser network
"""

import asyncio
import logging
import time
import random
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from .models import CapturedRequest
from .registry import endpoint_registry
from .raw_store import raw_store
from ..common.proxy_manager import proxy_manager

logger = logging.getLogger(__name__)

# Stealth scripts
STEALTH_SCRIPTS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
"""


class BrowserDiscovery:
    """
    Discovers API endpoints by capturing browser network traffic.
    
    Features:
    - Full request blueprint capture (headers, cookies, body)
    - Stealth patches for anti-bot bypass
    - Human behaviour simulation
    - Automatic classification
    """
    
    def __init__(self):
        self.captured: List[CapturedRequest] = []
    
    async def _human_behavior(self, page):
        """Simulate human interaction"""
        await asyncio.sleep(random.uniform(1.5, 2.5))
        await page.mouse.move(random.randint(100, 600), random.randint(100, 400))
        await asyncio.sleep(random.uniform(0.3, 0.8))
        
        for _ in range(random.randint(2, 4)):
            await page.mouse.wheel(0, random.randint(400, 900))
            await asyncio.sleep(random.uniform(0.8, 1.5))
        
        await page.mouse.move(random.randint(200, 800), random.randint(200, 600))
    
    def _classify_response(self, data: Any, url: str) -> str:
        """Classify captured data type"""
        if not isinstance(data, dict):
            if isinstance(data, list):
                return "list"
            return "unknown"
        
        keys_lower = str(data.keys()).lower()
        
        if "unlock" in keys_lower or "vesting" in keys_lower:
            return "unlocks"
        if "funding" in keys_lower or "round" in keys_lower or "raise" in keys_lower:
            return "funding"
        if "investor" in keys_lower or "fund" in keys_lower:
            return "investors"
        if "exchange" in keys_lower or "market" in keys_lower or "pair" in keys_lower:
            return "exchanges"
        if "sale" in keys_lower or "ico" in url or "ieo" in url or "ido" in url:
            return "sales"
        if "coin" in keys_lower or "token" in keys_lower:
            return "coins"
        if "category" in keys_lower or "sector" in keys_lower:
            return "categories"
        
        if "data" in data and isinstance(data["data"], list):
            return "paginated"
        if "total" in data:
            return "paginated"
        
        return "unknown"
    
    async def discover(
        self,
        source: str,
        targets: Dict[str, str],
        headless: bool = True
    ) -> Dict[str, Any]:
        """
        Discover endpoints from multiple pages.
        
        Args:
            source: Source name (dropstab, cryptorank)
            targets: Dict of {target_name: page_url}
            headless: Run browser headless
        
        Returns:
            Discovery summary
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {"error": "Playwright not installed"}
        
        self.captured = []
        start_time = time.time()
        
        logger.info(f"[Discovery] Starting {source} discovery ({len(targets)} pages)...")
        
        async with async_playwright() as p:
            launch_args = {
                "headless": headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox"
                ]
            }
            
            proxy = proxy_manager.get_playwright_proxy()
            if proxy:
                launch_args["proxy"] = proxy
            
            browser = await p.chromium.launch(**launch_args)
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York"
            )
            
            await context.add_init_script(STEALTH_SCRIPTS)
            
            page = await context.new_page()
            
            for target_name, page_url in targets.items():
                logger.info(f"[Discovery] Opening: {page_url}")
                
                # Capture handler for this page
                async def capture_handler(response):
                    try:
                        request = response.request
                        
                        if request.resource_type not in ("xhr", "fetch"):
                            return
                        
                        ct = response.headers.get("content-type", "")
                        if "json" not in ct.lower():
                            return
                        
                        if response.status != 200:
                            return
                        
                        try:
                            data = await response.json()
                        except:
                            return
                        
                        if not data:
                            return
                        
                        # Skip tracking
                        if any(x in response.url for x in ["analytics", "pixel", "track", "yandex", "google"]):
                            return
                        
                        # Build full blueprint
                        req = CapturedRequest(
                            url=response.url,
                            method=request.method,
                            headers=dict(request.headers),
                            body=request.post_data,
                            cookies={},  # Would need extra work to capture cookies
                            source=source,
                            target=target_name,
                            captured_at=datetime.now(timezone.utc).isoformat(),
                            from_page=page_url,
                            response_status=response.status,
                            response_type=self._classify_response(data, response.url),
                            response_keys=list(data.keys())[:10] if isinstance(data, dict) else [],
                            sample_size=len(data.get("data", data)) if isinstance(data, (dict, list)) else 0
                        )
                        
                        self.captured.append(req)
                        logger.info(f"[Discovery] Captured: {req.response_type} from {response.url[:60]}")
                        
                    except Exception as e:
                        logger.debug(f"[Discovery] Capture error: {e}")
                
                page.on("response", capture_handler)
                
                try:
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
                    await self._human_behavior(page)
                    await asyncio.sleep(random.uniform(2, 4))
                    
                    # Try clicking tabs/buttons
                    for selector in ["text=Load more", "text=Show more", "button:has-text('Next')"]:
                        try:
                            btn = page.locator(selector).first
                            if await btn.is_visible(timeout=1000):
                                await btn.click()
                                await asyncio.sleep(1.5)
                        except:
                            pass
                    
                except Exception as e:
                    logger.warning(f"[Discovery] Page failed: {page_url} -> {e}")
                
                await asyncio.sleep(random.uniform(2, 3))
            
            await browser.close()
        
        # Save to registry
        new_count = 0
        for req in self.captured:
            if endpoint_registry.upsert(req):
                new_count += 1
        
        # Save raw discovery data
        raw_path = raw_store.put(
            source=source,
            target="discovery",
            payload=[r.to_dict() for r in self.captured],
            meta={"pages": list(targets.keys())}
        )
        
        elapsed = time.time() - start_time
        
        result = {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "source": source,
            "pages_visited": len(targets),
            "total_captured": len(self.captured),
            "new_endpoints": new_count,
            "elapsed_sec": round(elapsed, 1),
            "raw_file": raw_path
        }
        
        logger.info(f"[Discovery] Complete: {len(self.captured)} captured, {new_count} new")
        
        return result


# Singleton
browser_discovery = BrowserDiscovery()
