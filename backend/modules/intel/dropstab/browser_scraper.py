"""
Dropstab Browser Scraper (Stealth Edition)
- Real browser automation with stealth patches
- Human behaviour simulation
- Multi-layer extraction (API → Browser → DOM)
- Automatic endpoint discovery

Stealth Features:
- navigator.webdriver = undefined
- chrome.runtime mock
- Human-like mouse/scroll behaviour
- Realistic viewport/user-agent
"""

import asyncio
import json
import time
import random
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Output directory for captured data
OUTPUT_DIR = Path("/app/backend/modules/intel/dropstab/browser_output")
SNAPSHOTS_DIR = OUTPUT_DIR / "snapshots"

# Target pages to scrape
TARGETS = [
    {"label": "unlocks", "url": "https://dropstab.com/token-unlock"},
    {"label": "funding", "url": "https://dropstab.com/funding-rounds"},
    {"label": "investors", "url": "https://dropstab.com/investors"},
    {"label": "ico", "url": "https://dropstab.com/ico"},
    {"label": "ieo", "url": "https://dropstab.com/ieo"},
    {"label": "ido", "url": "https://dropstab.com/ido"},
    {"label": "categories", "url": "https://dropstab.com/categories"},
    {"label": "coins", "url": "https://dropstab.com/coins"},
]

# Stealth JavaScript patches
STEALTH_SCRIPTS = """
// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// Mock chrome.runtime
window.chrome = {
    runtime: {}
};

// Mock permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// Mock plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

// Mock languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});
"""


class DropstabBrowserScraper:
    """
    Stealth browser scraper for Dropstab.
    
    Features:
    - Anti-detection stealth patches
    - Human behaviour simulation
    - XHR/fetch JSON capture
    - Automatic endpoint discovery
    - Snapshot system for debugging
    """
    
    def __init__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        self.captured: List[Dict] = []
        self._proxy = None
    
    def set_proxy(self, proxy_config: Optional[Dict] = None):
        """Set proxy for browser"""
        self._proxy = proxy_config
    
    async def _human_behavior(self, page):
        """
        Simulate human behaviour to avoid bot detection.
        - Random mouse movements
        - Natural scroll patterns
        - Human-like delays
        """
        # Initial pause (humans don't act instantly)
        await asyncio.sleep(random.uniform(1.2, 2.5))
        
        # Random mouse movement
        await page.mouse.move(
            random.randint(100, 600),
            random.randint(100, 400)
        )
        
        await asyncio.sleep(random.uniform(0.3, 0.8))
        
        # Scroll down naturally
        for _ in range(random.randint(2, 4)):
            scroll_amount = random.randint(300, 800)
            await page.mouse.wheel(0, scroll_amount)
            await asyncio.sleep(random.uniform(0.8, 1.5))
        
        # Another mouse movement
        await page.mouse.move(
            random.randint(200, 800),
            random.randint(200, 600)
        )
        
        await asyncio.sleep(random.uniform(0.5, 1.2))
    
    def _capture_response(self, label: str):
        """Create response capture handler"""
        async def handler(response):
            try:
                request = response.request
                
                # Only capture XHR/fetch
                if request.resource_type not in ("xhr", "fetch"):
                    return
                
                # Only JSON responses
                content_type = response.headers.get("content-type", "")
                if "json" not in content_type.lower():
                    return
                
                if response.status != 200:
                    return
                
                try:
                    data = await response.json()
                except:
                    return
                
                if not data:
                    return
                
                data_type = self._classify_data(data, response.url)
                
                self.captured.append({
                    "label": label,
                    "url": response.url,
                    "type": data_type,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": data
                })
                
                logger.info(f"[Dropstab] Captured: {data_type} from {response.url[:80]}")
                
            except Exception as e:
                logger.debug(f"[Dropstab] Capture error: {e}")
        
        return handler
    
    def _classify_data(self, data: Any, url: str) -> str:
        """Classify captured data by structure"""
        if not isinstance(data, dict):
            if isinstance(data, list) and len(data) > 0:
                return "list_data"
            return "unknown"
        
        keys_str = str(data.keys()).lower()
        
        if "coins" in data or "coinsbody" in data:
            return "coins"
        if "unlock" in keys_str or "vesting" in keys_str:
            return "unlocks"
        if "funding" in keys_str or "round" in keys_str:
            return "funding"
        if "investor" in keys_str or "fund" in keys_str:
            return "investors"
        if any(x in url.lower() for x in ["ico", "ieo", "ido"]):
            return "sales"
        if "category" in keys_str:
            return "categories"
        if "data" in data and isinstance(data["data"], list):
            return "list_wrapper"
        if "total" in data:
            return "paginated"
        
        return "unknown"
    
    async def _save_snapshot(self, page, label: str):
        """Save page snapshot for debugging"""
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            
            # Save HTML
            html = await page.content()
            html_path = SNAPSHOTS_DIR / f"{label}_{timestamp}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            
            # Save screenshot
            screenshot_path = SNAPSHOTS_DIR / f"{label}_{timestamp}.png"
            await page.screenshot(path=str(screenshot_path), full_page=False)
            
            logger.debug(f"[Dropstab] Snapshot saved: {label}_{timestamp}")
            
        except Exception as e:
            logger.warning(f"[Dropstab] Snapshot failed: {e}")
    
    async def scrape_all(self, headless: bool = True) -> Dict[str, Any]:
        """
        Scrape all target pages using stealth browser.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("[Dropstab] Playwright not installed!")
            return {"error": "Playwright not installed"}
        
        self.captured = []
        start_time = time.time()
        
        logger.info(f"[Dropstab] Starting stealth scrape ({len(TARGETS)} pages)...")
        
        async with async_playwright() as p:
            # Launch with anti-detection args
            launch_args = {
                "headless": headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-dev-shm-usage",
                    "--no-sandbox"
                ]
            }
            
            if self._proxy:
                launch_args["proxy"] = self._proxy
                logger.info(f"[Dropstab] Using proxy: {self._proxy.get('server')}")
            
            browser = await p.chromium.launch(**launch_args)
            
            # Context with realistic settings
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York"
            )
            
            # Apply stealth scripts
            await context.add_init_script(STEALTH_SCRIPTS)
            
            page = await context.new_page()
            
            for target in TARGETS:
                label = target["label"]
                url = target["url"]
                
                logger.info(f"[Dropstab] Opening: {url}")
                
                page.on("response", self._capture_response(label))
                
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    
                    # Human behaviour simulation
                    await self._human_behavior(page)
                    
                    # Wait for dynamic content
                    await asyncio.sleep(random.uniform(2, 4))
                    
                    # Try clicking load more buttons
                    for selector in ["text=Load more", "text=Show more", "button:has-text('Next')"]:
                        try:
                            btn = page.locator(selector).first
                            if await btn.is_visible(timeout=1000):
                                await btn.click()
                                await asyncio.sleep(random.uniform(1.5, 2.5))
                        except:
                            pass
                    
                    # Save snapshot on first page
                    if target == TARGETS[0]:
                        await self._save_snapshot(page, label)
                    
                except Exception as e:
                    logger.warning(f"[Dropstab] Failed to load {url}: {e}")
                    await self._save_snapshot(page, f"{label}_error")
                
                # Human-like delay between pages
                await asyncio.sleep(random.uniform(2, 4))
            
            await browser.close()
        
        elapsed = time.time() - start_time
        
        self._save_output()
        self._save_endpoints()
        
        by_type = {}
        for item in self.captured:
            t = item["type"]
            by_type[t] = by_type.get(t, 0) + 1
        
        result = {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "source": "dropstab_browser",
            "elapsed_sec": round(elapsed, 1),
            "pages_visited": len(TARGETS),
            "total_captured": len(self.captured),
            "by_type": by_type,
            "output_dir": str(OUTPUT_DIR)
        }
        
        logger.info(f"[Dropstab] Complete: {len(self.captured)} items in {elapsed:.1f}s")
        
        return result
    
    def _save_output(self):
        """Save captured data to files"""
        all_path = OUTPUT_DIR / "dropstab_all.json"
        with open(all_path, "w", encoding="utf-8") as f:
            json.dump(self.captured, f, indent=2, ensure_ascii=False)
        
        by_type = {}
        for item in self.captured:
            t = item["type"]
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(item)
        
        for data_type, items in by_type.items():
            path = OUTPUT_DIR / f"dropstab_{data_type}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
    
    def _save_endpoints(self):
        """Save discovered endpoints to registry"""
        endpoints = []
        seen = set()
        
        for item in self.captured:
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            
            # Skip tracking/analytics
            if any(x in url for x in ["yandex", "google", "analytics", "pixel"]):
                continue
            
            endpoints.append({
                "url": url,
                "method": item.get("method", "GET"),
                "headers": {k: v for k, v in item.get("headers", {}).items() 
                          if k.lower() in ["accept", "content-type", "origin", "referer"]},
                "type": item["type"],
                "discovered": datetime.now(timezone.utc).isoformat()
            })
        
        path = OUTPUT_DIR / "dropstab_endpoints.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(endpoints, f, indent=2, ensure_ascii=False)
        
        logger.info(f"[Dropstab] Saved {len(endpoints)} endpoints to registry")
    
    async def scrape_single(self, target_label: str, headless: bool = True) -> Dict[str, Any]:
        """Scrape single target page"""
        target = next((t for t in TARGETS if t["label"] == target_label), None)
        if not target:
            return {"error": f"Unknown target: {target_label}"}
        
        # Temporarily modify targets
        original = list(TARGETS)
        TARGETS.clear()
        TARGETS.append(target)
        
        try:
            result = await self.scrape_all(headless=headless)
        finally:
            TARGETS.clear()
            TARGETS.extend(original)
        
        return result
    
    def get_captured_data(self, data_type: str = None) -> List[Dict]:
        """Get captured data, optionally filtered by type"""
        if data_type:
            return [item for item in self.captured if item["type"] == data_type]
        return self.captured
    
    def get_discovered_endpoints(self) -> List[Dict]:
        """Get list of discovered endpoints"""
        path = OUTPUT_DIR / "dropstab_endpoints.json"
        if path.exists():
            return json.load(open(path, "r", encoding="utf-8"))
        return []


# Singleton instance
dropstab_browser = DropstabBrowserScraper()
