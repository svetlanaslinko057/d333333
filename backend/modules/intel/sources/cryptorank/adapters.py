"""
CryptoRank Adapter Parsers

Converts raw CryptoRank JSON → Unified Intel Models

CryptoRank data sources:
- api.cryptorank.io/v0/*
- Internal API discovered via browser
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from ...models import (
    IntelUnlock,
    IntelFunding,
    IntelInvestor,
    IntelSale,
    IntelEvent
)

logger = logging.getLogger(__name__)


def parse_timestamp(value: Any) -> Optional[int]:
    """Convert various date formats to unix timestamp"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value < 1e12 else int(value / 1000)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return int(dt.timestamp())
        except (ValueError, AttributeError):
            pass
        for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%d.%m.%Y']:
            try:
                dt = datetime.strptime(value, fmt)
                return int(dt.timestamp())
            except ValueError:
                pass
    return None


def normalize_round_type(stage: str) -> str:
    """Normalize funding round type from CryptoRank format"""
    if not stage:
        return "other"
    
    stage_lower = stage.lower()
    
    mapping = {
        "pre-seed": "pre_seed",
        "pre_seed": "pre_seed",
        "preseed": "pre_seed",
        "seed": "seed",
        "private": "private",
        "strategic": "strategic",
        "series_a": "series_a",
        "series a": "series_a",
        "series-a": "series_a",
        "series_b": "series_b",
        "series b": "series_b",
        "series_c": "series_c",
        "series c": "series_c",
        "public": "public",
    }
    
    for k, v in mapping.items():
        if k in stage_lower:
            return v
    
    return "other"


# ═══════════════════════════════════════════════════════════════
# UNLOCK PARSERS
# ═══════════════════════════════════════════════════════════════

def parse_unlocks(raw_data: List[Dict]) -> List[IntelUnlock]:
    """
    Parse token unlocks from CryptoRank.
    
    CryptoRank format:
    {
        "key": "tribal",
        "symbol": "TRIBL",
        "name": "Tribal",
        "unlockUsd": 29983890,
        "tokensPercent": 6.1,
        "unlockDate": "2026-03-04",
        "isHidden": false
    }
    """
    results = []
    
    for item in raw_data:
        try:
            symbol = (item.get("symbol") or "").upper()
            project = item.get("name") or item.get("key") or ""
            project_key = item.get("key") or symbol.lower()
            
            unlock_date = parse_timestamp(item.get("unlockDate"))
            
            if not unlock_date:
                continue
            
            unlock = IntelUnlock(
                source="cryptorank",
                source_id=f"{project_key}-{item.get('unlockDate', '')}",
                project=project,
                symbol=symbol,
                project_key=project_key,
                unlock_date=unlock_date,
                unlock_type="vesting",
                amount_tokens=item.get("unlockTokens"),
                amount_usd=item.get("unlockUsd"),
                percent_supply=item.get("tokensPercent"),
                is_hidden=item.get("isHidden", False),
                raw_data=item
            )
            
            results.append(unlock)
            
        except Exception as e:
            logger.warning(f"[CryptoRank] Failed to parse unlock: {e}")
            continue
    
    logger.info(f"[CryptoRank] Parsed {len(results)} unlocks")
    return results


def parse_tge_unlocks(raw_data: List[Dict]) -> List[IntelUnlock]:
    """
    Parse TGE unlocks from CryptoRank.
    
    CryptoRank TGE format:
    {
        "key": "hyperlend",
        "symbol": "HPL",
        "unlockTokens": 17360000,
        "unlockPercent": 1.7,
        "tgeDate": "2026-02-26",
        "isHidden": false
    }
    """
    results = []
    
    for item in raw_data:
        try:
            symbol = (item.get("symbol") or "").upper()
            project = item.get("name") or item.get("key") or ""
            project_key = item.get("key") or symbol.lower()
            
            unlock_date = parse_timestamp(item.get("tgeDate"))
            
            if not unlock_date:
                continue
            
            unlock = IntelUnlock(
                source="cryptorank",
                source_id=f"tge-{project_key}-{item.get('tgeDate', '')}",
                project=project,
                symbol=symbol,
                project_key=project_key,
                unlock_date=unlock_date,
                unlock_type="tge",
                amount_tokens=item.get("unlockTokens"),
                amount_usd=None,
                percent_supply=item.get("unlockPercent"),
                is_hidden=item.get("isHidden", False),
                raw_data=item
            )
            
            results.append(unlock)
            
        except Exception as e:
            logger.warning(f"[CryptoRank] Failed to parse TGE unlock: {e}")
            continue
    
    logger.info(f"[CryptoRank] Parsed {len(results)} TGE unlocks")
    return results


# ═══════════════════════════════════════════════════════════════
# FUNDING PARSERS
# ═══════════════════════════════════════════════════════════════

def parse_funding(raw_data: List[Dict]) -> List[IntelFunding]:
    """
    Parse funding rounds from CryptoRank.
    
    CryptoRank format:
    {
        "key": "cyclops",
        "name": "Cyclops",
        "symbol": null,
        "icon": "...",
        "raise": 8000000,
        "stage": "STRATEGIC",
        "date": "2026-03-04",
        "funds": [
            {
                "key": "castle-island-ventures",
                "name": "Castle Island Ventures",
                "tier": 2,
                "type": "NORMAL",
                "category": {"name": "venture"},
                "totalInvestments": 48
            }
        ]
    }
    """
    results = []
    
    for item in raw_data:
        try:
            symbol = (item.get("symbol") or "").upper() if item.get("symbol") else ""
            project = item.get("name") or ""
            project_key = item.get("key") or symbol.lower()
            
            if not project:
                continue
            
            round_date = parse_timestamp(item.get("date"))
            
            # Parse investors from funds array
            investors = []
            lead_investors = []
            
            for fund in (item.get("funds") or []):
                fund_name = fund.get("name", "")
                if fund_name:
                    investors.append(fund_name)
                    if fund.get("tier") == 1:
                        lead_investors.append(fund_name)
            
            funding = IntelFunding(
                source="cryptorank",
                source_id=f"{project_key}-{item.get('stage', '')}-{item.get('date', '')}",
                project=project,
                symbol=symbol,
                project_key=project_key,
                round_type=normalize_round_type(item.get("stage")),
                round_date=round_date or 0,
                raised_usd=item.get("raise"),
                valuation_usd=item.get("valuation"),
                investors=investors,
                lead_investors=lead_investors,
                investor_count=len(investors),
                raw_data=item
            )
            
            results.append(funding)
            
        except Exception as e:
            logger.warning(f"[CryptoRank] Failed to parse funding: {e}")
            continue
    
    logger.info(f"[CryptoRank] Parsed {len(results)} funding rounds")
    return results


# ═══════════════════════════════════════════════════════════════
# INVESTOR PARSERS
# ═══════════════════════════════════════════════════════════════

def parse_investors(raw_data: List[Dict]) -> List[IntelInvestor]:
    """
    Parse investors from CryptoRank.
    
    CryptoRank format (from top investors):
    {
        "slug": "coinbase-ventures",
        "name": "Coinbase Ventures",
        "count": 38,
        "logo": "..."
    }
    
    Or from funds array:
    {
        "key": "castle-island-ventures",
        "name": "Castle Island Ventures",
        "tier": 2,
        "type": "NORMAL",
        "category": {"name": "venture"},
        "totalInvestments": 48,
        "image": "..."
    }
    """
    results = []
    
    for item in raw_data:
        try:
            name = item.get("name") or ""
            slug = item.get("slug") or item.get("key") or name.lower().replace(" ", "-")
            
            if not name:
                continue
            
            # Determine tier
            tier_raw = item.get("tier")
            if tier_raw == 1:
                tier = "tier_1"
            elif tier_raw == 2:
                tier = "tier_2"
            elif tier_raw == 3:
                tier = "tier_3"
            else:
                tier = "other"
            
            # Get category
            category = item.get("category")
            if isinstance(category, dict):
                category = category.get("name", "")
            elif not isinstance(category, str):
                category = ""
            
            investor = IntelInvestor(
                source="cryptorank",
                source_id=slug,
                name=name,
                slug=slug,
                tier=tier,
                category=category or item.get("type", "").lower(),
                investments_count=item.get("totalInvestments") or item.get("count") or 0,
                portfolio=[],
                website="",
                twitter="",
                logo_url=item.get("logo") or item.get("image") or "",
                raw_data=item
            )
            
            results.append(investor)
            
        except Exception as e:
            logger.warning(f"[CryptoRank] Failed to parse investor: {e}")
            continue
    
    logger.info(f"[CryptoRank] Parsed {len(results)} investors")
    return results


def extract_investors_from_funding(funding_data: List[Dict]) -> List[IntelInvestor]:
    """Extract unique investors from funding rounds"""
    seen = set()
    investors = []
    
    for item in funding_data:
        for fund in (item.get("funds") or []):
            slug = fund.get("key") or fund.get("slug")
            if slug and slug not in seen:
                seen.add(slug)
                parsed = parse_investors([fund])
                investors.extend(parsed)
    
    return investors


# ═══════════════════════════════════════════════════════════════
# SALE PARSERS
# ═══════════════════════════════════════════════════════════════

def parse_sales(raw_data: List[Dict]) -> List[IntelSale]:
    """
    Parse token sales (ICO/IEO/IDO) from CryptoRank.
    
    CryptoRank format:
    {
        "key": "project-x",
        "name": "Project X",
        "symbol": "PRX",
        "saleType": "IDO",
        "launchpad": {"name": "Binance Launchpad", "key": "binance"},
        "startDate": "2026-04-01",
        "endDate": "2026-04-05",
        "price": 0.05,
        "raise": 5000000,
        "roi": {"USD": 3.0},
        "athRoi": {"USD": 10.5}
    }
    """
    results = []
    
    for item in raw_data:
        try:
            symbol = (item.get("symbol") or "").upper()
            project = item.get("name") or ""
            project_key = item.get("key") or symbol.lower()
            
            if not project:
                continue
            
            # Get platform/launchpad
            launchpad = item.get("launchpad")
            platform = ""
            if isinstance(launchpad, dict):
                platform = launchpad.get("name", "")
            elif isinstance(launchpad, str):
                platform = launchpad
            
            # Get ROI
            roi = item.get("roi")
            roi_usd = roi.get("USD") if isinstance(roi, dict) else roi
            
            ath_roi = item.get("athRoi")
            ath_roi_usd = ath_roi.get("USD") if isinstance(ath_roi, dict) else ath_roi
            
            sale = IntelSale(
                source="cryptorank",
                source_id=f"{project_key}-{item.get('saleType', '')}",
                project=project,
                symbol=symbol,
                project_key=project_key,
                sale_type=item.get("saleType", "other").lower(),
                platform=platform,
                start_date=parse_timestamp(item.get("startDate")),
                end_date=parse_timestamp(item.get("endDate")),
                price_usd=item.get("price"),
                raise_usd=item.get("raise"),
                raise_target_usd=item.get("target"),
                current_price_usd=item.get("currentPrice"),
                roi_usd=roi_usd,
                ath_roi_usd=ath_roi_usd,
                raw_data=item
            )
            
            results.append(sale)
            
        except Exception as e:
            logger.warning(f"[CryptoRank] Failed to parse sale: {e}")
            continue
    
    logger.info(f"[CryptoRank] Parsed {len(results)} sales")
    return results


# ═══════════════════════════════════════════════════════════════
# LAUNCHPAD PARSERS
# ═══════════════════════════════════════════════════════════════

def parse_launchpads(raw_data: List[Dict]) -> List[Dict]:
    """
    Parse launchpad platforms from CryptoRank.
    
    Returns raw launchpad data (not unified model yet).
    """
    results = []
    
    for item in raw_data:
        try:
            key = item.get("key") or item.get("slug")
            name = item.get("name")
            
            if not key or not name:
                continue
            
            doc = {
                "source": "cryptorank",
                "source_id": key,
                "name": name,
                "slug": key,
                "projects_count": item.get("projectsCount") or item.get("count") or 0,
                "avg_roi": item.get("avgRoi"),
                "ath_roi": item.get("athRoi"),
                "logo": item.get("logo") or item.get("image"),
                "raw_data": item
            }
            
            results.append(doc)
            
        except Exception as e:
            logger.warning(f"[CryptoRank] Failed to parse launchpad: {e}")
            continue
    
    logger.info(f"[CryptoRank] Parsed {len(results)} launchpads")
    return results


# ═══════════════════════════════════════════════════════════════
# AUTO-DETECT PARSER
# ═══════════════════════════════════════════════════════════════

def parse_auto(raw_data: Any, target_hint: str = "") -> Dict[str, List]:
    """
    Auto-detect data type and parse accordingly.
    
    Args:
        raw_data: Raw JSON from scraper
        target_hint: Hint about data type ("unlocks", "funding", etc)
    
    Returns:
        Dict with parsed results by type
    """
    results = {
        "unlocks": [],
        "funding": [],
        "investors": [],
        "sales": [],
        "launchpads": []
    }
    
    if not raw_data:
        return results
    
    # Handle paginated response
    if isinstance(raw_data, dict) and "data" in raw_data:
        data_list = raw_data["data"]
    elif isinstance(raw_data, list):
        data_list = raw_data
    else:
        data_list = [raw_data]
    
    if not data_list:
        return results
    
    # Try to detect type from content
    sample = data_list[0] if isinstance(data_list[0], dict) else {}
    keys = set(sample.keys())
    
    # Detect by keys or hint
    if "unlockDate" in keys or "unlockUsd" in keys or target_hint == "unlocks":
        results["unlocks"] = parse_unlocks(data_list)
    
    elif "tgeDate" in keys or target_hint == "tge_unlocks":
        results["unlocks"] = parse_tge_unlocks(data_list)
    
    elif "stage" in keys or "raise" in keys or "funds" in keys or target_hint == "funding":
        results["funding"] = parse_funding(data_list)
        # Also extract investors
        results["investors"] = extract_investors_from_funding(data_list)
    
    elif "totalInvestments" in keys or target_hint == "investors" or target_hint == "funds":
        results["investors"] = parse_investors(data_list)
    
    elif "saleType" in keys or target_hint in ["ico", "ieo", "ido", "sales"]:
        results["sales"] = parse_sales(data_list)
    
    elif "projectsCount" in keys or target_hint == "launchpads":
        results["launchpads"] = parse_launchpads(data_list)
    
    else:
        logger.warning(f"[CryptoRank] Could not auto-detect type for hint: {target_hint}")
    
    return results
