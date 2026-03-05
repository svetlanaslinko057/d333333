"""
Dropstab Module - Hybrid Client (SSR + BFF fallback)

Primary: SSR scraping from __NEXT_DATA__ 
Fallback: BFF API if available
"""

from .scraper import DropstabScraper, dropstab_scraper
from .sync import DropstabSync

__all__ = ['DropstabScraper', 'dropstab_scraper', 'DropstabSync']
