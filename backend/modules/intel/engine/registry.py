"""
Scraper Registry - Manages all registered scrapers
"""

import logging
from typing import List, Dict, Optional, Type
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ScraperRegistry:
    """
    Central registry for all scrapers.
    Allows dynamic registration and lookup.
    """
    
    def __init__(self):
        self._scrapers: Dict[str, Type[BaseScraper]] = {}
        self._instances: Dict[str, BaseScraper] = {}
    
    def register(self, scraper_class: Type[BaseScraper]):
        """Register a scraper class."""
        name = scraper_class.name
        self._scrapers[name] = scraper_class
        logger.info(f"[Registry] Registered scraper: {name}")
    
    def get(self, name: str) -> Optional[Type[BaseScraper]]:
        """Get scraper class by name."""
        return self._scrapers.get(name)
    
    def get_instance(self, name: str, db) -> Optional[BaseScraper]:
        """Get or create scraper instance."""
        if name not in self._instances:
            scraper_class = self._scrapers.get(name)
            if scraper_class:
                self._instances[name] = scraper_class(db)
        return self._instances.get(name)
    
    def list_all(self) -> List[Dict]:
        """List all registered scrapers."""
        return [
            {
                'name': name,
                'source': cls.source,
                'entity': cls.entity_type,
                'interval_hours': cls.interval_hours,
                'priority': cls.priority
            }
            for name, cls in self._scrapers.items()
        ]
    
    def list_by_source(self, source: str) -> List[str]:
        """List scrapers for a specific source."""
        return [
            name for name, cls in self._scrapers.items()
            if cls.source == source
        ]
    
    def list_by_entity(self, entity_type: str) -> List[str]:
        """List scrapers for a specific entity type."""
        return [
            name for name, cls in self._scrapers.items()
            if cls.entity_type == entity_type
        ]


# Singleton
scraper_registry = ScraperRegistry()
