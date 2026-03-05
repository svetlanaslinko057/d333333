"""
Scraper Runner
Orchestrates discovery and sync operations
"""

import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone

from .models import CapturedRequest
from .registry import endpoint_registry
from .raw_store import raw_store
from .replay import replay_client
from .discovery import browser_discovery

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# TARGET DEFINITIONS
# ═══════════════════════════════════════════════════════════════

DROPSTAB_TARGETS = {
    "unlocks": "https://dropstab.com/token-unlock",
    "funding": "https://dropstab.com/funding-rounds",
    "investors": "https://dropstab.com/investors",
    "ico": "https://dropstab.com/ico",
    "ieo": "https://dropstab.com/ieo",
    "ido": "https://dropstab.com/ido",
    "coins": "https://dropstab.com/coins",
    "categories": "https://dropstab.com/categories",
}

CRYPTORANK_TARGETS = {
    "funding": "https://cryptorank.io/funding-rounds",
    "funds": "https://cryptorank.io/funds",
    "investors": "https://cryptorank.io/investors",
    "unlocks": "https://cryptorank.io/token-unlocks",
    "exchanges": "https://cryptorank.io/exchanges",
    "launchpads": "https://cryptorank.io/launchpads",
    "ico": "https://cryptorank.io/ico",
    "ieo": "https://cryptorank.io/ieo",
    "ido": "https://cryptorank.io/ido",
    "listings": "https://cryptorank.io/new-cryptocurrencies",
}


class ScraperRunner:
    """
    Main scraper runner.
    
    Operations:
    1. discover() - Browser captures endpoints, saves to registry
    2. sync() - Replays endpoints from registry, saves raw data
    3. Multi-layer fallback (API → Browser)
    """
    
    def __init__(self):
        pass
    
    # ═══════════════════════════════════════════════════════════════
    # DISCOVERY (Layer 2 - Browser)
    # ═══════════════════════════════════════════════════════════════
    
    async def discover_dropstab(self, targets: List[str] = None, headless: bool = True) -> Dict[str, Any]:
        """
        Discover Dropstab API endpoints.
        
        Args:
            targets: Specific targets to discover, or all if None
            headless: Run browser headless
        """
        if targets:
            selected = {k: v for k, v in DROPSTAB_TARGETS.items() if k in targets}
        else:
            selected = DROPSTAB_TARGETS
        
        return await browser_discovery.discover("dropstab", selected, headless)
    
    async def discover_cryptorank(self, targets: List[str] = None, headless: bool = True) -> Dict[str, Any]:
        """Discover CryptoRank API endpoints."""
        if targets:
            selected = {k: v for k, v in CRYPTORANK_TARGETS.items() if k in targets}
        else:
            selected = CRYPTORANK_TARGETS
        
        return await browser_discovery.discover("cryptorank", selected, headless)
    
    # ═══════════════════════════════════════════════════════════════
    # SYNC (Layer 1 - Direct API with fallback)
    # ═══════════════════════════════════════════════════════════════
    
    async def sync(self, source: str, target: str) -> Dict[str, Any]:
        """
        Sync data from registered endpoints.
        
        1. Get best endpoints from registry
        2. Try direct API replay
        3. If all fail → trigger discovery
        4. Save raw data
        """
        logger.info(f"[Runner] Syncing {source}/{target}...")
        
        # Get endpoints from registry
        endpoints = endpoint_registry.get_best(source, target, limit=5)
        
        if not endpoints:
            logger.warning(f"[Runner] No endpoints for {source}/{target}, triggering discovery")
            
            # Auto-discover
            if source == "dropstab":
                await self.discover_dropstab(targets=[target])
            elif source == "cryptorank":
                await self.discover_cryptorank(targets=[target])
            
            endpoints = endpoint_registry.get_best(source, target, limit=5)
            
            if not endpoints:
                return {"error": f"No endpoints found for {source}/{target}"}
        
        # Try replay
        results = []
        success_endpoint = None
        
        for req in endpoints:
            success, data = await replay_client.replay_async(req)
            
            if success:
                success_endpoint = req
                endpoint_registry.report_success(req)
                results.append({
                    "url": req.url,
                    "success": True,
                    "payload": data
                })
                break
            else:
                endpoint_registry.report_fail(req, str(data))
                results.append({
                    "url": req.url,
                    "success": False,
                    "error": str(data)
                })
        
        if not success_endpoint:
            return {
                "source": source,
                "target": target,
                "success": False,
                "tried": len(results),
                "results": results
            }
        
        # Save raw data
        raw_path = raw_store.put(
            source=source,
            target=target,
            payload=results[-1]["payload"],
            meta={
                "endpoint": success_endpoint.url,
                "method": success_endpoint.method
            }
        )
        
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "source": source,
            "target": target,
            "success": True,
            "endpoint": success_endpoint.url,
            "raw_file": raw_path
        }
    
    async def sync_all(self, source: str) -> Dict[str, Any]:
        """Sync all targets for a source"""
        targets = DROPSTAB_TARGETS.keys() if source == "dropstab" else CRYPTORANK_TARGETS.keys()
        
        results = {}
        for target in targets:
            try:
                results[target] = await self.sync(source, target)
            except Exception as e:
                results[target] = {"error": str(e)}
            
            await asyncio.sleep(1)  # Rate limit
        
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "source": source,
            "results": results
        }
    
    # ═══════════════════════════════════════════════════════════════
    # ADMIN
    # ═══════════════════════════════════════════════════════════════
    
    def get_status(self) -> Dict[str, Any]:
        """Get runner status"""
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "registry": endpoint_registry.get_stats(),
            "raw_store": raw_store.get_stats(),
            "sources": {
                "dropstab": {
                    "targets": list(DROPSTAB_TARGETS.keys()),
                    "endpoints": len(endpoint_registry.get_all(source="dropstab"))
                },
                "cryptorank": {
                    "targets": list(CRYPTORANK_TARGETS.keys()),
                    "endpoints": len(endpoint_registry.get_all(source="cryptorank"))
                }
            }
        }


# Singleton
scraper_runner = ScraperRunner()
