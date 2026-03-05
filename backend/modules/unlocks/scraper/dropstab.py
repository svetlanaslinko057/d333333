"""
Dropstab Scraper
Source: dropstab.com/unlocks
"""

import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid
import re

from ..domain import Project, TokenUnlock, UnlockCategory

logger = logging.getLogger(__name__)


class DropstabScraper:
    """
    Scraper for Dropstab token unlock data.
    Uses their public API endpoints.
    """
    
    BASE_URL = "https://dropstab.com"
    API_URL = "https://api.dropstab.com"
    TIMEOUT = 30
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; FOMO/1.0)',
            'Accept': 'application/json'
        }
    
    async def fetch_upcoming_unlocks(self, days: int = 90) -> List[Dict]:
        """
        Fetch upcoming token unlocks from Dropstab.
        Returns raw unlock data.
        """
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                # Try the API endpoint
                res = await client.get(
                    f"{self.API_URL}/v1/unlocks/upcoming",
                    headers=self.headers,
                    params={'days': days}
                )
                
                if res.status_code == 200:
                    return res.json().get('data', [])
                
                # Fallback: try web scraping approach
                logger.warning(f"[Dropstab] API returned {res.status_code}, trying fallback")
                return await self._scrape_unlocks_page()
                
        except Exception as e:
            logger.error(f"[Dropstab] Fetch failed: {e}")
            return []
    
    async def _scrape_unlocks_page(self) -> List[Dict]:
        """Fallback scraper for Dropstab unlocks page"""
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                res = await client.get(
                    f"{self.BASE_URL}/unlocks",
                    headers={
                        **self.headers,
                        'Accept': 'text/html'
                    }
                )
                
                if res.status_code != 200:
                    return []
                
                # Parse HTML for unlock data
                # This is a simplified parser - real implementation would use BeautifulSoup
                html = res.text
                
                # Look for JSON data in script tags
                import json
                pattern = r'__NEXT_DATA__.*?type="application/json">(.*?)</script>'
                match = re.search(pattern, html, re.DOTALL)
                
                if match:
                    try:
                        data = json.loads(match.group(1))
                        props = data.get('props', {}).get('pageProps', {})
                        return props.get('unlocks', [])
                    except json.JSONDecodeError:
                        pass
                
                return []
                
        except Exception as e:
            logger.error(f"[Dropstab] Scrape failed: {e}")
            return []
    
    def normalize_unlock(self, raw: Dict) -> Optional[TokenUnlock]:
        """Convert raw Dropstab data to TokenUnlock"""
        try:
            # Extract fields (adjust based on actual Dropstab response)
            project_name = raw.get('project_name') or raw.get('name', '')
            project_symbol = raw.get('symbol', '').upper()
            
            if not project_symbol:
                return None
            
            # Parse date
            date_str = raw.get('unlock_date') or raw.get('date')
            if isinstance(date_str, str):
                unlock_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            elif isinstance(date_str, (int, float)):
                unlock_date = datetime.fromtimestamp(date_str, tz=timezone.utc)
            else:
                return None
            
            # Parse amounts
            amount = float(raw.get('unlock_amount', 0) or raw.get('amount', 0) or 0)
            percent = float(raw.get('unlock_percent', 0) or raw.get('percent', 0) or 0)
            value_usd = raw.get('unlock_value_usd') or raw.get('value_usd')
            
            # Map category
            raw_category = raw.get('category', 'other').lower()
            category = self._map_category(raw_category)
            
            # Generate IDs
            project_id = f"dropstab:{project_symbol.lower()}"
            unlock_id = f"dropstab:{project_symbol.lower()}:{int(unlock_date.timestamp())}"
            
            return TokenUnlock(
                id=unlock_id,
                project_id=project_id,
                project_symbol=project_symbol,
                project_name=project_name,
                unlock_date=unlock_date,
                unlock_amount=amount,
                unlock_percent=percent,
                unlock_value_usd=float(value_usd) if value_usd else None,
                category=category,
                description=raw.get('description'),
                source='dropstab',
                source_url=f"{self.BASE_URL}/coins/{project_symbol.lower()}"
            )
            
        except Exception as e:
            logger.error(f"[Dropstab] Normalize failed: {e}")
            return None
    
    def normalize_project(self, raw: Dict) -> Optional[Project]:
        """Extract project info from unlock data"""
        try:
            symbol = raw.get('symbol', '').upper()
            if not symbol:
                return None
            
            return Project(
                id=f"dropstab:{symbol.lower()}",
                name=raw.get('project_name') or raw.get('name', symbol),
                symbol=symbol,
                slug=symbol.lower(),
                website=raw.get('website'),
                logo_url=raw.get('logo') or raw.get('logo_url'),
                coingecko_id=raw.get('coingecko_id'),
                total_supply=raw.get('total_supply'),
                circulating_supply=raw.get('circulating_supply')
            )
        except Exception as e:
            logger.error(f"[Dropstab] Project normalize failed: {e}")
            return None
    
    def _map_category(self, raw_category: str) -> UnlockCategory:
        """Map raw category string to UnlockCategory"""
        mapping = {
            'team': UnlockCategory.TEAM,
            'investor': UnlockCategory.INVESTOR,
            'investors': UnlockCategory.INVESTOR,
            'seed': UnlockCategory.INVESTOR,
            'private': UnlockCategory.INVESTOR,
            'ecosystem': UnlockCategory.ECOSYSTEM,
            'treasury': UnlockCategory.TREASURY,
            'foundation': UnlockCategory.FOUNDATION,
            'advisor': UnlockCategory.ADVISOR,
            'advisors': UnlockCategory.ADVISOR,
            'marketing': UnlockCategory.MARKETING,
            'liquidity': UnlockCategory.LIQUIDITY,
            'community': UnlockCategory.COMMUNITY,
            'airdrop': UnlockCategory.COMMUNITY,
        }
        return mapping.get(raw_category, UnlockCategory.OTHER)
    
    async def sync_all(self) -> Dict[str, int]:
        """
        Full sync: fetch all unlocks and return counts.
        Returns dict with projects and unlocks counts.
        """
        raw_data = await self.fetch_upcoming_unlocks(days=180)
        
        projects = {}
        unlocks = []
        
        for raw in raw_data:
            # Extract project
            project = self.normalize_project(raw)
            if project and project.id not in projects:
                projects[project.id] = project
            
            # Extract unlock
            unlock = self.normalize_unlock(raw)
            if unlock:
                unlocks.append(unlock)
        
        return {
            'projects': list(projects.values()),
            'unlocks': unlocks,
            'raw_count': len(raw_data)
        }


# Singleton
dropstab_scraper = DropstabScraper()
