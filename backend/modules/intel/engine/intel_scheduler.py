"""
Intel Sync Scheduler
Manages periodic data synchronization from all sources (Dropstab, CryptoRank)
"""

import asyncio
import logging
import random
from typing import Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class IntelSyncScheduler:
    """
    Scheduler for periodic Intel data synchronization.
    Manages sync jobs for Dropstab and CryptoRank.
    
    Intervals (configurable):
    - Unlocks: every 3 hours (high value, time-sensitive)
    - Fundraising: every 4 hours
    - Investors: every 6 hours
    - Projects: every 12 hours
    - Categories/Launchpads: every 24 hours
    """
    
    # Default sync intervals in seconds
    INTERVALS = {
        'dropstab_unlocks': 3 * 3600,      # 3 hours
        'dropstab_fundraising': 4 * 3600,  # 4 hours  
        'dropstab_investors': 6 * 3600,    # 6 hours
        'dropstab_projects': 12 * 3600,    # 12 hours
        'dropstab_activity': 6 * 3600,     # 6 hours
        
        'cryptorank_unlocks': 3 * 3600,    # 3 hours
        'cryptorank_funding': 4 * 3600,    # 4 hours
        'cryptorank_investors': 6 * 3600,  # 6 hours
        'cryptorank_projects': 12 * 3600,  # 12 hours
        'cryptorank_launchpads': 24 * 3600,  # 24 hours
        'cryptorank_categories': 24 * 3600,  # 24 hours
    }
    
    def __init__(self, db):
        self.db = db
        self._running = False
        self._tasks: Dict[str, asyncio.Task] = {}
        self._jitter_seconds = 300  # 0-5 min random jitter
        
        # Lazy imports
        self._dropstab_sync = None
        self._cryptorank_sync = None
    
    def _get_dropstab_sync(self):
        """Lazy load Dropstab sync"""
        if self._dropstab_sync is None:
            from ..dropstab.sync import DropstabSync
            self._dropstab_sync = DropstabSync(self.db)
        return self._dropstab_sync
    
    def _get_cryptorank_sync(self):
        """Lazy load CryptoRank sync"""
        if self._cryptorank_sync is None:
            from ..sources.cryptorank.sync import CryptoRankSync
            self._cryptorank_sync = CryptoRankSync(self.db)
        return self._cryptorank_sync
    
    async def start(self, enable_dropstab: bool = True, enable_cryptorank: bool = True):
        """
        Start the sync scheduler.
        
        Args:
            enable_dropstab: Enable Dropstab sync jobs
            enable_cryptorank: Enable CryptoRank sync jobs
        """
        if self._running:
            logger.warning("[IntelScheduler] Already running")
            return
        
        self._running = True
        logger.info("[IntelScheduler] Starting Intel sync scheduler...")
        
        # Start Dropstab sync tasks
        if enable_dropstab:
            await self._start_dropstab_tasks()
        
        # Start CryptoRank sync tasks (scraper - no API key needed)
        if enable_cryptorank:
            await self._start_cryptorank_tasks()
        
        logger.info(f"[IntelScheduler] Started {len(self._tasks)} sync tasks")
    
    async def _start_dropstab_tasks(self):
        """Start Dropstab sync tasks"""
        dropstab = self._get_dropstab_sync()
        
        sync_jobs = [
            ('dropstab_unlocks', dropstab.sync_unlocks, self.INTERVALS['dropstab_unlocks']),
            ('dropstab_fundraising', dropstab.sync_fundraising, self.INTERVALS['dropstab_fundraising']),
            ('dropstab_investors', dropstab.sync_investors, self.INTERVALS['dropstab_investors']),
            ('dropstab_projects', dropstab.sync_projects, self.INTERVALS['dropstab_projects']),
            ('dropstab_activity', dropstab.sync_activity, self.INTERVALS['dropstab_activity']),
        ]
        
        for name, sync_func, interval in sync_jobs:
            task = asyncio.create_task(self._run_loop(name, sync_func, interval))
            self._tasks[name] = task
            logger.info(f"[IntelScheduler] Scheduled {name} every {interval // 3600}h")
    
    async def _start_cryptorank_tasks(self):
        """
        CryptoRank is a scraper source - no automatic sync.
        Data must be ingested via POST /api/intel/ingest/cryptorank/{entity}
        """
        logger.info("[IntelScheduler] CryptoRank is a scraper source - no automatic sync scheduled")
        logger.info("[IntelScheduler] Use POST /api/intel/ingest/cryptorank/{entity} to ingest data")
    
    async def _run_loop(self, name: str, sync_func, interval: int):
        """Run sync function in a loop with interval"""
        # Initial delay with jitter to spread out startup load
        initial_delay = random.randint(10, self._jitter_seconds)
        await asyncio.sleep(initial_delay)
        
        while self._running:
            try:
                logger.info(f"[IntelScheduler] Running {name}...")
                start = asyncio.get_event_loop().time()
                
                result = await sync_func()
                
                duration = asyncio.get_event_loop().time() - start
                logger.info(f"[IntelScheduler] {name} completed in {duration:.1f}s: {result}")
                
                # Record health
                await self._record_health(name, 'ok', result, duration)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[IntelScheduler] {name} failed: {e}")
                await self._record_health(name, 'error', {'error': str(e)}, 0)
            
            # Wait for next interval (with small jitter)
            jitter = random.randint(0, 60)
            await asyncio.sleep(interval + jitter)
    
    async def _record_health(self, name: str, status: str, result: Dict, duration: float):
        """Record sync health to database"""
        try:
            await self.db.scraper_health.update_one(
                {'scraper': name},
                {'$set': {
                    'scraper': name,
                    'source': name.split('_')[0],  # dropstab or cryptorank
                    'entity': '_'.join(name.split('_')[1:]),
                    'last_run': datetime.now(timezone.utc),
                    'status': status,
                    'result': result,
                    'duration': duration
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"[IntelScheduler] Failed to record health for {name}: {e}")
    
    async def stop(self):
        """Stop the scheduler"""
        if not self._running:
            return
        
        self._running = False
        
        for name, task in self._tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._tasks.clear()
        logger.info("[IntelScheduler] Stopped")
    
    def status(self) -> Dict:
        """Get scheduler status"""
        return {
            'running': self._running,
            'active_tasks': len(self._tasks),
            'tasks': list(self._tasks.keys())
        }


# Global scheduler instance
_scheduler: Optional[IntelSyncScheduler] = None


def get_intel_scheduler(db) -> IntelSyncScheduler:
    """Get or create Intel scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = IntelSyncScheduler(db)
    return _scheduler


async def start_intel_scheduler(db, enable_dropstab: bool = True, enable_cryptorank: bool = True):
    """Start the Intel sync scheduler"""
    scheduler = get_intel_scheduler(db)
    await scheduler.start(enable_dropstab, enable_cryptorank)
    return scheduler


async def stop_intel_scheduler():
    """Stop the Intel sync scheduler"""
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
