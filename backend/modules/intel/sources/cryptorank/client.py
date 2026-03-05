"""
CryptoRank Scraper Client
Simple HTTP client for manual scraping - no API key required.

This module processes JSON data that has already been fetched
(via browser, manual scraping, etc.) rather than making direct API calls.
"""

import requests
import logging

logger = logging.getLogger(__name__)


class CryptoRankClient:
    """
    Simple scraper client.
    Used for manual fetch operations when needed.
    Most sync operations receive JSON data directly.
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/json',
        })
    
    def fetch_json(self, url: str, timeout: int = 20) -> dict:
        """
        Fetch JSON from URL.
        Used for manual scraping when URL is known.
        """
        try:
            r = self.session.get(url, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"[CryptoRank] fetch failed: {e}")
            return {}


# Singleton
cryptorank_client = CryptoRankClient()
