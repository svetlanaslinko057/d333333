"""
Dropstab Browser Scraper
Uses Playwright for real browser automation to bypass bot detection.

Why browser is needed:
- Dropstab uses bot detection + SSR filtering + cloud firewall
- Regular HTTP requests get fake 404
- Real browser passes all checks

Targets:
- /token-unlock - vesting/unlock schedule
- /funding-rounds - latest fundraising
- /investors - VC/fund list
- /ico, /ieo, /ido - token sales
"""

import asyncio
import json
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Output directory for captured data
OUTPUT_DIR = Path("/app/backend/modules/intel/dropstab/browser_output")

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


class DropstabBrowserScraper:
    """
    Browser-based scraper for Dropstab using Playwright.
    
    Captures XHR/fetch JSON responses while navigating pages.
    Looks like real user to bypass bot detection.
    """
    
    def __init__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.captured: List[Dict] = []
        self._proxy = None
    
    def set_proxy(self, proxy_config: Optional[Dict] = None):
        """Set proxy for browser"""
        self._proxy = proxy_config
    
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
                
                # Skip small responses (likely errors)
                if response.status != 200:
                    return
                
                # Parse JSON
                try:
                    data = await response.json()
                except:
                    return
                
                # Skip empty responses
                if not data:
                    return
                
                # Classify the data
                data_type = self._classify_data(data, response.url)
                
                self.captured.append({
                    "label": label,
                    "url": response.url,
                    "type": data_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": data
                })
                
                logger.info(f"[Dropstab Browser] Captured: {data_type} from {response.url[:80]}")
                
            except Exception as e:
                logger.debug(f"[Dropstab Browser] Capture error: {e}")
        
        return handler
    
    def _classify_data(self, data: Any, url: str) -> str:
        """Classify captured data by structure"""
        if not isinstance(data, dict):
            if isinstance(data, list) and len(data) > 0:
                return "list_data"
            return "unknown"
        
        # Check for common patterns
        if "coins" in data or "coinsBody" in data:
            return "coins"
        if "unlock" in str(data.keys()).lower() or "vesting" in str(data.keys()).lower():
            return "unlocks"
        if "funding" in str(data.keys()).lower() or "round" in str(data.keys()).lower():
            return "funding"
        if "investor" in str(data.keys()).lower() or "fund" in str(data.keys()).lower():
            return "investors"
        if "ico" in url or "ieo" in url or "ido" in url:
            return "sales"
        if "category" in str(data.keys()).lower():
            return "categories"
        
        # Check for list wrapper
        if "data" in data and isinstance(data["data"], list):
            return "list_wrapper"
        if "total" in data:
            return "paginated"
        
        return "unknown"
    
    async def scrape_all(self, headless: bool = True) -> Dict[str, Any]:
        """
        Scrape all target pages using browser.
        
        Args:
            headless: Run browser in headless mode (True for server, False for debug)
        
        Returns:
            Summary with captured data
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("[Dropstab Browser] Playwright not installed!")
            return {
                "error": "Playwright not installed. Run: pip install playwright && playwright install chromium"
            }
        
        self.captured = []
        start_time = time.time()
        
        logger.info(f"[Dropstab Browser] Starting scrape ({len(TARGETS)} pages)...")
        
        async with async_playwright() as p:
            # Launch browser with anti-detection
            launch_args = {
                "headless": headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--no-sandbox"
                ]
            }
            
            # Add proxy if configured
            if self._proxy:
                launch_args["proxy"] = self._proxy
                logger.info(f"[Dropstab Browser] Using proxy: {self._proxy.get('server')}")
            
            browser = await p.chromium.launch(**launch_args)
            
            # Create context with realistic settings
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York"
            )
            
            page = await context.new_page()
            
            # Scrape each target
            for target in TARGETS:
                label = target["label"]
                url = target["url"]
                
                logger.info(f"[Dropstab Browser] Opening: {url}")
                
                # Set up response capture
                page.on("response", self._capture_response(label))
                
                try:
                    # Navigate with longer timeout
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                    
                    # Wait for dynamic content
                    await asyncio.sleep(4)
                    
                    # Scroll to trigger lazy loading
                    await page.mouse.wheel(0, 2000)
                    await asyncio.sleep(2)
                    await page.mouse.wheel(0, 2000)
                    await asyncio.sleep(2)
                    
                    # Try clicking common pagination/load more buttons
                    for selector in ["text=Load more", "text=Show more", "button:has-text('Next')"]:
                        try:
                            btn = page.locator(selector).first
                            if await btn.is_visible():
                                await btn.click()
                                await asyncio.sleep(2)
                        except:
                            pass
                    
                except Exception as e:
                    logger.warning(f"[Dropstab Browser] Failed to load {url}: {e}")
                
                # Delay between pages
                await asyncio.sleep(3)
            
            await browser.close()
        
        elapsed = time.time() - start_time
        
        # Save captured data
        self._save_output()
        
        # Group by type
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
        
        logger.info(f"[Dropstab Browser] Complete: {len(self.captured)} items in {elapsed:.1f}s")
        
        return result
    
    def _save_output(self):
        """Save captured data to files"""
        # Save all data
        all_path = OUTPUT_DIR / "dropstab_all.json"
        with open(all_path, "w", encoding="utf-8") as f:
            json.dump(self.captured, f, indent=2, ensure_ascii=False)
        
        # Save by type
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
        
        logger.info(f"[Dropstab Browser] Saved to {OUTPUT_DIR}")
    
    async def scrape_single(self, target_label: str, headless: bool = True) -> Dict[str, Any]:
        """Scrape single target page"""
        target = next((t for t in TARGETS if t["label"] == target_label), None)
        if not target:
            return {"error": f"Unknown target: {target_label}"}
        
        # Temporarily replace TARGETS
        original_targets = TARGETS.copy()
        TARGETS.clear()
        TARGETS.append(target)
        
        try:
            result = await self.scrape_all(headless=headless)
        finally:
            TARGETS.clear()
            TARGETS.extend(original_targets)
        
        return result
    
    def get_captured_data(self, data_type: str = None) -> List[Dict]:
        """Get captured data, optionally filtered by type"""
        if data_type:
            return [item for item in self.captured if item["type"] == data_type]
        return self.captured


# Singleton instance
dropstab_browser = DropstabBrowserScraper()


# Standalone script runner
if __name__ == "__main__":
    import sys
    
    async def main():
        print("Starting Dropstab browser scraper...")
        
        # Load proxy from env
        from proxy_manager import proxy_manager
        if proxy_manager.is_configured:
            dropstab_browser.set_proxy(proxy_manager.get_playwright_proxy())
        
        # Run headless=False for debugging
        headless = "--headless" in sys.argv
        result = await dropstab_browser.scrape_all(headless=headless)
        
        print(json.dumps(result, indent=2))
    
    asyncio.run(main())
