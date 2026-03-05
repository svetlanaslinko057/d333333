"""
Scraper Scheduler - Manages periodic scraper execution
"""

import asyncio
import logging
import random
from typing import Optional, Dict, List
from datetime import datetime, timezone
from .registry import scraper_registry

logger = logging.getLogger(__name__)


class ScraperScheduler:
    """
    Scheduler for periodic scraper execution.
    Supports jitter to prevent thundering herd.
    """
    
    def __init__(self, db):
        self.db = db
        self._running = False
        self._tasks: Dict[str, asyncio.Task] = {}
        self._jitter_seconds = 300  # 0-5 min random jitter
    
    async def start(self):
        """Start all scheduled scrapers."""
        if self._running:
            return
        
        self._running = True
        logger.info("[Scheduler] Starting scraper scheduler...")
        
        # Get all registered scrapers
        scrapers = scraper_registry.list_all()
        
        for scraper_info in scrapers:
            name = scraper_info['name']
            interval = scraper_info['interval_hours']
            
            # Create task for each scraper
            task = asyncio.create_task(self._run_loop(name, interval))
            self._tasks[name] = task
            logger.info(f"[Scheduler] Scheduled {name} every {interval}h")
    
    async def stop(self):
        """Stop all scheduled scrapers."""
        self._running = False
        
        for name, task in self._tasks.items():
            task.cancel()
        
        self._tasks.clear()
        logger.info("[Scheduler] Stopped")
    
    async def _run_loop(self, scraper_name: str, interval_hours: int):
        """Run scraper in a loop with interval."""
        while self._running:
            try:
                # Add jitter
                jitter = random.randint(0, self._jitter_seconds)
                await asyncio.sleep(jitter)
                
                # Run scraper
                await self.run_scraper(scraper_name)
                
                # Wait for next interval
                interval_seconds = interval_hours * 3600
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Scheduler] {scraper_name} loop error: {e}")
                await asyncio.sleep(300)  # Wait 5 min on error
    
    async def run_scraper(self, name: str) -> Optional[Dict]:
        """Run a specific scraper."""
        scraper = scraper_registry.get_instance(name, self.db)
        
        if not scraper:
            logger.warning(f"[Scheduler] Scraper not found: {name}")
            return None
        
        logger.info(f"[Scheduler] Running {name}...")
        result = await scraper.run()
        
        return result
    
    async def run_all(self, source: Optional[str] = None) -> List[Dict]:
        """Run all scrapers (optionally filtered by source)."""
        results = []
        
        scrapers = scraper_registry.list_all()
        
        for scraper_info in scrapers:
            if source and scraper_info['source'] != source:
                continue
            
            result = await self.run_scraper(scraper_info['name'])
            if result:
                results.append(result)
        
        return results
    
    def status(self) -> Dict:
        """Get scheduler status."""
        return {
            'running': self._running,
            'active_tasks': len(self._tasks),
            'scrapers': list(self._tasks.keys())
        }


# Factory function
def create_scheduler(db):
    return ScraperScheduler(db)
