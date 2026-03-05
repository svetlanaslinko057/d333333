"""
CryptoRank Discovery & Sync
Browser-based endpoint discovery for CryptoRank data
"""

import json
import time
import re
import logging
import asyncio
import httpx
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Storage paths
ENDPOINTS_DIR = Path("/app/backend/modules/intel/sources/cryptorank/endpoints")
OUTPUT_DIR = Path("/app/backend/modules/intel/sources/cryptorank/output")

# CryptoRank target pages for discovery
TARGETS = [
    {"label": "funding_rounds", "url": "https://cryptorank.io/funding-rounds"},
    {"label": "funds", "url": "https://cryptorank.io/funds"},
    {"label": "investors", "url": "https://cryptorank.io/investors"},
    {"label": "token_unlocks", "url": "https://cryptorank.io/token-unlocks"},
    {"label": "exchanges", "url": "https://cryptorank.io/exchanges"},
    {"label": "launchpads", "url": "https://cryptorank.io/launchpads"},
    {"label": "ico", "url": "https://cryptorank.io/ico"},
    {"label": "new_listings", "url": "https://cryptorank.io/new-cryptocurrencies"},
]


@dataclass
class CapturedCall:
    """Captured API call from browser network"""
    label: str
    kind: str
    url: str
    method: str
    status: int
    request_headers: Dict[str, str]
    request_post_data: Optional[str]
    response_sample: Any
    matched_reason: str


def classify_payload(payload: Any, url: str) -> Tuple[str, str]:
    """
    Classify CryptoRank JSON payload by structure.
    Returns (kind, reason)
    """
    if not isinstance(payload, dict):
        return ("unknown", "not_dict")

    # Common list wrapper: { total, data }
    if "total" in payload and isinstance(payload.get("data"), list):
        row = payload["data"][0] if payload["data"] else {}
        if isinstance(row, dict):
            keys = set(row.keys())

            # Funding rounds
            if ("stage" in keys or "round" in keys) and ("date" in keys or "createdAt" in keys):
                return ("fundraising_rounds", "total+data with stage/date")

            # Funds/investors
            if {"name", "key"}.issubset(keys) and ("tier" in keys or "totalInvestments" in keys):
                return ("funds_or_investors", "total+data with fund-ish row")

            # Exchanges
            if ("exchange" in keys or "pairs" in keys) and ("volume" in keys or "volume24h" in keys):
                return ("exchanges_or_markets", "total+data with exchange/volume")

            # Sales/launchpads
            if {"startDate", "endDate"}.intersection(keys) and ("price" in keys or "raise" in keys):
                return ("sales_or_launchpads", "total+data with start/end")

        return ("generic_list", "total+data")

    # Unlocks
    unlock_keys = {"unlock", "unlocks", "unlockEvents", "nextUnlock", "schedule"}
    if unlock_keys.intersection(payload.keys()):
        return ("unlocks", f"keys:{list(unlock_keys.intersection(payload.keys()))[:3]}")

    # URL hinting fallback
    if re.search(r"fund|raise|round", url, re.I):
        return ("fundraising_misc", "url_hint_fund")
    if re.search(r"unlock|vesting", url, re.I):
        return ("unlocks", "url_hint_unlock")
    if re.search(r"exchange|market", url, re.I):
        return ("exchanges_or_markets", "url_hint_market")

    return ("unknown", "no_match")


class CryptoRankDiscovery:
    """
    Browser-based endpoint discovery for CryptoRank.
    Captures XHR/fetch calls and classifies them.
    """
    
    def __init__(self):
        ENDPOINTS_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.captured: List[CapturedCall] = []
    
    async def discover_with_playwright(self, headless: bool = True) -> Dict[str, Any]:
        """
        Run Playwright browser to discover API endpoints.
        Requires: pip install playwright && playwright install chromium
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return {"error": "playwright_not_installed"}
        
        logger.info("[CryptoRank] Starting endpoint discovery...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1440, "height": 900},
                locale="en-US",
            )
            page = await context.new_page()
            
            async def on_response(response):
                try:
                    req = response.request
                    url = response.url
                    
                    if req.resource_type not in ("xhr", "fetch"):
                        return
                    
                    ct = (response.headers.get("content-type") or "").lower()
                    if "json" not in ct:
                        return
                    
                    payload = await response.json()
                    kind, reason = classify_payload(payload, url)
                    
                    if kind == "unknown":
                        return
                    
                    # Trim sample
                    sample = payload
                    if isinstance(sample, dict) and isinstance(sample.get("data"), list):
                        sample = {**sample, "data": sample["data"][:2]}
                    
                    self.captured.append(CapturedCall(
                        label=page.url,
                        kind=kind,
                        url=url,
                        method=req.method,
                        status=response.status,
                        request_headers={k.lower(): v for k, v in req.headers.items()},
                        request_post_data=req.post_data,
                        response_sample=sample,
                        matched_reason=reason,
                    ))
                except:
                    pass
            
            page.on("response", on_response)
            
            for target in TARGETS:
                logger.info(f"[CryptoRank] Visiting: {target['url']}")
                try:
                    await page.goto(target["url"], wait_until="networkidle", timeout=60000)
                    await asyncio.sleep(3)
                    
                    # Scroll to trigger lazy loads
                    await page.mouse.wheel(0, 1500)
                    await asyncio.sleep(1)
                    await page.mouse.wheel(0, 1500)
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.warning(f"[CryptoRank] Failed to load {target['url']}: {e}")
            
            await browser.close()
        
        # Deduplicate
        unique = {}
        for c in self.captured:
            if c.status != 200:
                continue
            key = (c.kind, c.url, c.method)
            unique[key] = c
        
        result = {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "countMatched": len(unique),
            "calls": [asdict(v) for v in unique.values()]
        }
        
        # Save to file
        out_path = ENDPOINTS_DIR / "cryptorank_endpoints.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"[CryptoRank] Discovery complete: {len(unique)} endpoints saved to {out_path}")
        return result


class CryptoRankSync:
    """
    Sync service using discovered endpoints.
    """
    
    def __init__(self, db=None):
        self.db = db
        self.timeout = 60.0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        }
    
    def _load_endpoints(self) -> List[Dict]:
        """Load discovered endpoints"""
        path = ENDPOINTS_DIR / "cryptorank_endpoints.json"
        if not path.exists():
            return []
        data = json.load(open(path, "r", encoding="utf-8"))
        return data.get("calls", [])
    
    def _clean_headers(self, h: Dict[str, str]) -> Dict[str, str]:
        """Clean headers for replay"""
        h = dict(h or {})
        for k in ["content-length", "host", ":authority", ":method", ":path", ":scheme"]:
            h.pop(k, None)
        h.update(self.headers)
        return h
    
    async def _fetch_endpoint(self, call: Dict) -> Optional[Any]:
        """Fetch single endpoint"""
        url = call["url"]
        method = call["method"]
        headers = self._clean_headers(call.get("request_headers", {}))
        post_data = call.get("request_post_data")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers)
            elif method.upper() == "POST":
                if post_data:
                    try:
                        body = json.loads(post_data)
                        response = await client.post(url, headers=headers, json=body)
                    except:
                        response = await client.post(url, headers=headers, content=post_data)
                else:
                    response = await client.post(url, headers=headers)
            else:
                return None
            
            if response.status_code == 200:
                return response.json()
            
            logger.warning(f"[CryptoRank] {url} returned {response.status_code}")
            return None
    
    async def sync_by_kind(self, kind: str) -> Dict[str, Any]:
        """Sync all endpoints of a specific kind"""
        endpoints = self._load_endpoints()
        matched = [e for e in endpoints if e.get("kind") == kind]
        
        if not matched:
            return {"error": f"No endpoints found for kind: {kind}"}
        
        results = []
        for endpoint in matched[:5]:  # Limit to 5 endpoints per kind
            try:
                data = await self._fetch_endpoint(endpoint)
                if data:
                    results.append({
                        "url": endpoint["url"],
                        "data": data
                    })
            except Exception as e:
                logger.error(f"[CryptoRank] Failed to fetch {endpoint['url']}: {e}")
            
            await asyncio.sleep(0.5)
        
        # Save output
        out_path = OUTPUT_DIR / f"cryptorank_{kind}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        return {
            "kind": kind,
            "endpoints_found": len(matched),
            "fetched": len(results),
            "output": str(out_path)
        }
    
    async def sync_all_discovered(self) -> Dict[str, Any]:
        """Sync all discovered endpoint kinds"""
        endpoints = self._load_endpoints()
        
        kinds = set(e.get("kind") for e in endpoints if e.get("kind"))
        
        results = {}
        for kind in kinds:
            if kind == "unknown":
                continue
            try:
                results[kind] = await self.sync_by_kind(kind)
            except Exception as e:
                results[kind] = {"error": str(e)}
        
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "source": "cryptorank",
            "kinds_synced": list(results.keys()),
            "results": results
        }
    
    # ═══════════════════════════════════════════════════════════════
    # INGEST METHODS (for manual JSON POST)
    # ═══════════════════════════════════════════════════════════════
    
    async def ingest_funding(self, data: List[Dict]) -> Dict[str, Any]:
        """Ingest funding rounds data"""
        if not self.db:
            return {"error": "No database configured"}
        
        saved = 0
        for item in data:
            doc = {
                "key": f"cryptorank:funding:{item.get('key', item.get('id', ''))}",
                "source": "cryptorank",
                "project_key": item.get("key"),
                "project_name": item.get("name"),
                "round": item.get("round") or item.get("stage"),
                "raised": item.get("raised") or item.get("amountRaised"),
                "valuation": item.get("valuation"),
                "date": item.get("date") or item.get("createdAt"),
                "investors": item.get("investors") or item.get("funds", []),
                "updated_at": datetime.now(timezone.utc)
            }
            
            await self.db.intel_funding.update_one(
                {"key": doc["key"]},
                {"$set": doc},
                upsert=True
            )
            saved += 1
        
        return {"entity": "funding", "total": len(data), "saved": saved}
    
    async def ingest_investors(self, data: List[Dict]) -> Dict[str, Any]:
        """Ingest investor/fund data"""
        if not self.db:
            return {"error": "No database configured"}
        
        saved = 0
        for item in data:
            doc = {
                "key": f"cryptorank:investor:{item.get('key', item.get('id', ''))}",
                "source": "cryptorank",
                "name": item.get("name"),
                "type": item.get("type"),
                "tier": item.get("tier"),
                "total_investments": item.get("totalInvestments"),
                "portfolio_size": item.get("portfolioSize"),
                "country": item.get("country"),
                "updated_at": datetime.now(timezone.utc)
            }
            
            await self.db.intel_investors.update_one(
                {"key": doc["key"]},
                {"$set": doc},
                upsert=True
            )
            saved += 1
        
        return {"entity": "investors", "total": len(data), "saved": saved}
    
    async def ingest_unlocks(self, data: List[Dict]) -> Dict[str, Any]:
        """Ingest token unlock data"""
        if not self.db:
            return {"error": "No database configured"}
        
        saved = 0
        for item in data:
            doc = {
                "key": f"cryptorank:unlock:{item.get('key', item.get('id', ''))}:{item.get('unlockDate', '')}",
                "source": "cryptorank",
                "project_key": item.get("key"),
                "project_name": item.get("name"),
                "unlock_date": item.get("unlockDate") or item.get("date"),
                "unlock_amount": item.get("unlockAmount") or item.get("amount"),
                "unlock_percent": item.get("unlockPercent") or item.get("percent"),
                "unlock_usd": item.get("unlockUsd") or item.get("value"),
                "allocation": item.get("allocation"),
                "updated_at": datetime.now(timezone.utc)
            }
            
            await self.db.intel_unlocks.update_one(
                {"key": doc["key"]},
                {"$set": doc},
                upsert=True
            )
            saved += 1
        
        return {"entity": "unlocks", "total": len(data), "saved": saved}
    
    async def ingest_all(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ingest all CryptoRank data types"""
        results = {}
        
        if "funding" in data:
            results["funding"] = await self.ingest_funding(data["funding"])
        
        if "investors" in data:
            results["investors"] = await self.ingest_investors(data["investors"])
        
        if "unlocks" in data:
            results["unlocks"] = await self.ingest_unlocks(data["unlocks"])
        
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "source": "cryptorank",
            "results": results
        }


# Singleton instances
cryptorank_discovery = CryptoRankDiscovery()
cryptorank_sync = CryptoRankSync()
