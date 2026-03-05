"""
Dropstab Adapter Parsers

Converts raw Dropstab JSON → Unified Intel Models

Dropstab data sources:
- api2.dropstab.com/portfolio/api/markets
- extra-bff.dropstab.com/v1.2/*
- SSR __NEXT_DATA__ from pages
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
        # Already timestamp
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
    """Normalize funding round type"""
    if not stage:
        return "other"
    
    stage_lower = stage.lower()
    
    mapping = {
        "pre-seed": "pre_seed",
        "preseed": "pre_seed",
        "seed": "seed",
        "private": "private",
        "strategic": "strategic",
        "series a": "series_a",
        "series-a": "series_a",
        "series b": "series_b",
        "series-b": "series_b",
        "series c": "series_c",
        "series-c": "series_c",
        "public": "public",
        "ipo": "public",
    }
    
    for k, v in mapping.items():
        if k in stage_lower:
            return v
    
    return "other"


def normalize_sale_type(sale_type: str) -> str:
    """Normalize sale type"""
    if not sale_type:
        return "other"
    
    sale_lower = sale_type.lower()
    
    if "ico" in sale_lower:
        return "ico"
    if "ieo" in sale_lower:
        return "ieo"
    if "ido" in sale_lower:
        return "ido"
    if "igo" in sale_lower:
        return "igo"
    if "private" in sale_lower:
        return "private_sale"
    if "public" in sale_lower:
        return "public_sale"
    
    return "other"


# ═══════════════════════════════════════════════════════════════
# UNLOCK PARSERS
# ═══════════════════════════════════════════════════════════════

def parse_unlocks(raw_data: List[Dict]) -> List[IntelUnlock]:
    """
    Parse token unlocks from Dropstab.
    
    Expected input format (from api2.dropstab.com or SSR):
    {
        "id": 123,
        "name": "Solana",
        "symbol": "SOL",
        "slug": "solana",
        "unlockDate": "2026-06-01",
        "amount": 10000000,
        "value": 1200000000,
        "percent": 1.8,
        "type": "vesting"
    }
    """
    results = []
    
    for item in raw_data:
        try:
            symbol = (item.get("symbol") or "").upper()
            project = item.get("name") or item.get("project") or ""
            project_key = item.get("slug") or item.get("key") or symbol.lower()
            
            # Get unlock date
            unlock_date = parse_timestamp(
                item.get("unlockDate") or 
                item.get("unlock_date") or 
                item.get("date")
            )
            
            if not unlock_date:
                continue
            
            unlock = IntelUnlock(
                source="dropstab",
                source_id=str(item.get("id", "")),
                project=project,
                symbol=symbol,
                project_key=project_key,
                unlock_date=unlock_date,
                unlock_type=item.get("type", "vesting"),
                amount_tokens=item.get("amount") or item.get("unlockAmount"),
                amount_usd=item.get("value") or item.get("unlockUsd"),
                percent_supply=item.get("percent") or item.get("tokensPercent"),
                is_hidden=item.get("isHidden", False),
                raw_data=item
            )
            
            results.append(unlock)
            
        except Exception as e:
            logger.warning(f"[Dropstab] Failed to parse unlock: {e}")
            continue
    
    logger.info(f"[Dropstab] Parsed {len(results)} unlocks")
    return results


# ═══════════════════════════════════════════════════════════════
# FUNDING PARSERS
# ═══════════════════════════════════════════════════════════════

def parse_funding(raw_data: List[Dict]) -> List[IntelFunding]:
    """
    Parse funding rounds from Dropstab.
    
    Expected input format:
    {
        "id": 456,
        "name": "Project X",
        "symbol": "PRX",
        "slug": "project-x",
        "round": "Series A",
        "date": "2026-03-01",
        "raised": 15000000,
        "valuation": 150000000,
        "investors": [
            {"name": "a16z", "lead": true},
            {"name": "Paradigm", "lead": false}
        ]
    }
    """
    results = []
    
    for item in raw_data:
        try:
            symbol = (item.get("symbol") or "").upper()
            project = item.get("name") or item.get("project") or ""
            project_key = item.get("slug") or item.get("key") or symbol.lower()
            
            # Get round date
            round_date = parse_timestamp(
                item.get("date") or 
                item.get("roundDate") or 
                item.get("announcedDate")
            )
            
            # Parse investors
            investors = []
            lead_investors = []
            
            inv_list = item.get("investors") or item.get("funds") or []
            for inv in inv_list:
                if isinstance(inv, dict):
                    inv_name = inv.get("name", "")
                    if inv_name:
                        investors.append(inv_name)
                        if inv.get("lead") or inv.get("isLead") or inv.get("tier") == 1:
                            lead_investors.append(inv_name)
                elif isinstance(inv, str):
                    investors.append(inv)
            
            funding = IntelFunding(
                source="dropstab",
                source_id=str(item.get("id", "")),
                project=project,
                symbol=symbol,
                project_key=project_key,
                round_type=normalize_round_type(item.get("round") or item.get("stage")),
                round_date=round_date or 0,
                raised_usd=item.get("raised") or item.get("raise") or item.get("amount"),
                valuation_usd=item.get("valuation"),
                investors=investors,
                lead_investors=lead_investors,
                investor_count=len(investors),
                raw_data=item
            )
            
            results.append(funding)
            
        except Exception as e:
            logger.warning(f"[Dropstab] Failed to parse funding: {e}")
            continue
    
    logger.info(f"[Dropstab] Parsed {len(results)} funding rounds")
    return results


# ═══════════════════════════════════════════════════════════════
# INVESTOR PARSERS
# ═══════════════════════════════════════════════════════════════

def parse_investors(raw_data: List[Dict]) -> List[IntelInvestor]:
    """
    Parse investors/VCs from Dropstab.
    
    Expected input format:
    {
        "id": 789,
        "name": "Andreessen Horowitz",
        "slug": "a16z",
        "type": "venture",
        "tier": 1,
        "investmentsCount": 350,
        "logo": "https://...",
        "portfolio": ["solana", "ethereum", "polygon"]
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
            
            investor = IntelInvestor(
                source="dropstab",
                source_id=str(item.get("id", "")),
                name=name,
                slug=slug,
                tier=tier,
                category=item.get("type") or item.get("category") or "",
                investments_count=item.get("investmentsCount") or item.get("investments_count") or 0,
                portfolio=item.get("portfolio") or [],
                website=item.get("website") or "",
                twitter=item.get("twitter") or "",
                logo_url=item.get("logo") or item.get("image") or "",
                raw_data=item
            )
            
            results.append(investor)
            
        except Exception as e:
            logger.warning(f"[Dropstab] Failed to parse investor: {e}")
            continue
    
    logger.info(f"[Dropstab] Parsed {len(results)} investors")
    return results


# ═══════════════════════════════════════════════════════════════
# SALE PARSERS
# ═══════════════════════════════════════════════════════════════

def parse_sales(raw_data: List[Dict]) -> List[IntelSale]:
    """
    Parse token sales (ICO/IEO/IDO) from Dropstab.
    
    Expected input format:
    {
        "id": 111,
        "name": "Project Y",
        "symbol": "PRY",
        "slug": "project-y",
        "saleType": "IDO",
        "platform": "Binance Launchpad",
        "startDate": "2026-04-01",
        "endDate": "2026-04-05",
        "price": 0.05,
        "raised": 5000000,
        "currentPrice": 0.15,
        "roi": 3.0,
        "athRoi": 10.5
    }
    """
    results = []
    
    for item in raw_data:
        try:
            symbol = (item.get("symbol") or "").upper()
            project = item.get("name") or item.get("project") or ""
            project_key = item.get("slug") or item.get("key") or symbol.lower()
            
            sale = IntelSale(
                source="dropstab",
                source_id=str(item.get("id", "")),
                project=project,
                symbol=symbol,
                project_key=project_key,
                sale_type=normalize_sale_type(item.get("saleType") or item.get("type")),
                platform=item.get("platform") or item.get("launchpad") or "",
                start_date=parse_timestamp(item.get("startDate") or item.get("start_date")),
                end_date=parse_timestamp(item.get("endDate") or item.get("end_date")),
                price_usd=item.get("price") or item.get("salePrice"),
                raise_usd=item.get("raised") or item.get("raise"),
                raise_target_usd=item.get("target") or item.get("raiseTarget"),
                current_price_usd=item.get("currentPrice") or item.get("current_price"),
                roi_usd=item.get("roi"),
                ath_roi_usd=item.get("athRoi") or item.get("ath_roi"),
                raw_data=item
            )
            
            results.append(sale)
            
        except Exception as e:
            logger.warning(f"[Dropstab] Failed to parse sale: {e}")
            continue
    
    logger.info(f"[Dropstab] Parsed {len(results)} sales")
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
        "sales": []
    }
    
    if not raw_data:
        return results
    
    # Ensure we have a list
    data_list = raw_data if isinstance(raw_data, list) else [raw_data]
    
    # Try to detect type from content
    if data_list:
        sample = data_list[0] if isinstance(data_list[0], dict) else {}
        keys = set(sample.keys())
        
        # Detect by keys
        if "unlockDate" in keys or "unlock_date" in keys or target_hint == "unlocks":
            results["unlocks"] = parse_unlocks(data_list)
        
        elif "round" in keys or "stage" in keys or "raised" in keys or target_hint == "funding":
            results["funding"] = parse_funding(data_list)
        
        elif "investmentsCount" in keys or "investments_count" in keys or target_hint == "investors":
            results["investors"] = parse_investors(data_list)
        
        elif "saleType" in keys or "platform" in keys or target_hint in ["ico", "ieo", "ido", "sales"]:
            results["sales"] = parse_sales(data_list)
        
        else:
            # Try all parsers
            if target_hint:
                logger.warning(f"[Dropstab] Unknown target hint: {target_hint}, trying all parsers")
            
            # Try each parser and keep non-empty results
            unlocks = parse_unlocks(data_list)
            if unlocks:
                results["unlocks"] = unlocks
            
            funding = parse_funding(data_list)
            if funding:
                results["funding"] = funding
    
    return results
