"""
Intel Scheduler & Health Monitor
Automated sync jobs with cron-like scheduling
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class SyncStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"


@dataclass
class SyncJob:
    """Sync job definition"""
    name: str
    source: str
    entity: str
    interval_minutes: int
    priority: int = 0  # Lower = higher priority
    enabled: bool = True
    last_run: Optional[datetime] = None
    last_status: SyncStatus = SyncStatus.IDLE
    last_result: Optional[Dict] = None
    last_error: Optional[str] = None
    run_count: int = 0
    error_count: int = 0


@dataclass
class HealthStatus:
    """System health status"""
    ts: int
    scheduler_running: bool
    jobs_total: int
    jobs_enabled: int
    sources: Dict[str, Dict]
    last_syncs: Dict[str, Dict]
    errors_24h: List[Dict]
    database_stats: Dict[str, int]


class IntelScheduler:
    """
    Scheduler for intel sync jobs.
    
    Cron-like scheduling:
    - markets_full: daily 03:00 UTC
    - top_coins: every 10 min
    - trending: every 30 min
    - categories: daily 04:00 UTC
    - unlocks: every 1h
    - fundraising: every 2h
    """
    
    def __init__(self, db=None):
        self.db = db
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
        # Job definitions
        self.jobs: Dict[str, SyncJob] = {
            # ═══════════════════════════════════════════════════════════════
            # MARKET DATA - CoinGecko ONLY (primary source for prices/mcap)
            # ═══════════════════════════════════════════════════════════════
            "coingecko_markets_full": SyncJob(
                name="CoinGecko Full Market",
                source="coingecko",
                entity="markets_full",
                interval_minutes=1440,  # Daily
                priority=1
            ),
            "coingecko_top_coins": SyncJob(
                name="CoinGecko Top 100",
                source="coingecko",
                entity="top_coins",
                interval_minutes=10,
                priority=0
            ),
            "coingecko_trending": SyncJob(
                name="CoinGecko Trending",
                source="coingecko",
                entity="trending",
                interval_minutes=30,
                priority=2
            ),
            "coingecko_categories": SyncJob(
                name="CoinGecko Categories",
                source="coingecko",
                entity="categories",
                interval_minutes=1440,  # Daily
                priority=3
            ),
            
            # ═══════════════════════════════════════════════════════════════
            # ANALYTICS - CryptoRank (source 1 for redundancy)
            # ═══════════════════════════════════════════════════════════════
            "cryptorank_fundraising": SyncJob(
                name="CryptoRank Fundraising",
                source="cryptorank_browser",
                entity="fundraising",
                interval_minutes=60,  # 1h
                priority=4,
                enabled=False  # Requires browser
            ),
            "cryptorank_unlocks": SyncJob(
                name="CryptoRank Unlocks",
                source="cryptorank_browser",
                entity="unlocks",
                interval_minutes=60,  # 1h
                priority=5,
                enabled=False  # Requires browser
            ),
            "cryptorank_investors": SyncJob(
                name="CryptoRank Investors",
                source="cryptorank_browser",
                entity="investors",
                interval_minutes=360,  # 6h
                priority=6,
                enabled=False  # Requires browser
            ),
            
            # ═══════════════════════════════════════════════════════════════
            # ANALYTICS - Dropstab (source 2 for redundancy)
            # ═══════════════════════════════════════════════════════════════
            "dropstab_fundraising": SyncJob(
                name="Dropstab Fundraising",
                source="dropstab_browser",
                entity="funding",
                interval_minutes=60,  # 1h
                priority=4,
                enabled=False  # Requires browser
            ),
            "dropstab_unlocks": SyncJob(
                name="Dropstab Unlocks",
                source="dropstab_browser",
                entity="unlocks",
                interval_minutes=60,  # 1h
                priority=5,
                enabled=False  # Requires browser  
            ),
            "dropstab_investors": SyncJob(
                name="Dropstab Investors",
                source="dropstab_browser",
                entity="investors",
                interval_minutes=360,  # 6h
                priority=6,
                enabled=False  # Requires browser
            ),
        }
    
    def _get_sync_service(self, source: str):
        """Get appropriate sync service for source"""
        if source == "coingecko":
            from modules.intel.sources.coingecko.sync import CoinGeckoSync
            return CoinGeckoSync(self.db)
        elif source == "dropstab_browser":
            from modules.intel.dropstab.browser_scraper import dropstab_browser
            return dropstab_browser
        elif source == "cryptorank_browser":
            from modules.intel.sources.cryptorank.discovery import cryptorank_sync
            return cryptorank_sync
        else:
            raise ValueError(f"Unknown source: {source}")
    
    async def _run_job(self, job: SyncJob) -> Dict[str, Any]:
        """Execute single sync job"""
        logger.info(f"[Scheduler] Running: {job.name}")
        job.last_status = SyncStatus.RUNNING
        
        try:
            service = self._get_sync_service(job.source)
            
            # Execute based on source type
            if job.source == "coingecko":
                if job.entity == "markets_full":
                    result = await service.sync_markets_full(max_pages=60)
                elif job.entity == "top_coins":
                    result = await service.sync_top_coins(limit=100)
                elif job.entity == "trending":
                    result = await service.sync_trending()
                elif job.entity == "categories":
                    result = await service.sync_categories()
                else:
                    result = {"error": f"Unknown entity: {job.entity}"}
            
            elif job.source == "dropstab_browser":
                # Browser scraper for analytics
                result = await service.scrape_single(job.entity, headless=True)
                
            elif job.source == "cryptorank_browser":
                # Browser sync for analytics
                result = await service.sync_by_kind(job.entity)
                
            else:
                result = {"error": f"Unknown source: {job.source}"}
            
            # Update job status
            job.last_run = datetime.now(timezone.utc)
            job.last_result = result
            job.last_status = SyncStatus.SUCCESS
            job.run_count += 1
            job.last_error = None
            
            logger.info(f"[Scheduler] Completed: {job.name} - {result.get('total', result.get('count', 'OK'))}")
            return result
            
        except Exception as e:
            job.last_status = SyncStatus.FAILED
            job.last_error = str(e)
            job.error_count += 1
            
            if "429" in str(e) or "rate" in str(e).lower():
                job.last_status = SyncStatus.RATE_LIMITED
            
            logger.error(f"[Scheduler] Failed: {job.name} - {e}")
            return {"error": str(e)}
    
    def _should_run(self, job: SyncJob) -> bool:
        """Check if job should run based on interval"""
        if not job.enabled:
            return False
        
        if job.last_run is None:
            return True
        
        next_run = job.last_run + timedelta(minutes=job.interval_minutes)
        return datetime.now(timezone.utc) >= next_run
    
    async def _scheduler_loop(self):
        """Main scheduler loop"""
        logger.info("[Scheduler] Starting scheduler loop...")
        
        while self.running:
            try:
                # Get jobs that should run, sorted by priority
                due_jobs = [
                    job for job in self.jobs.values()
                    if self._should_run(job)
                ]
                due_jobs.sort(key=lambda j: j.priority)
                
                # Run due jobs sequentially (to respect rate limits)
                for job in due_jobs:
                    if not self.running:
                        break
                    
                    await self._run_job(job)
                    
                    # Small delay between jobs
                    await asyncio.sleep(2)
                
                # Check every 30 seconds
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Scheduler] Loop error: {e}")
                await asyncio.sleep(60)
        
        logger.info("[Scheduler] Scheduler loop stopped")
    
    async def start(self) -> Dict[str, Any]:
        """Start the scheduler"""
        if self.running:
            return {"status": "already_running"}
        
        self.running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        
        logger.info("[Scheduler] Started")
        return {
            "status": "started",
            "jobs": len(self.jobs),
            "enabled": len([j for j in self.jobs.values() if j.enabled])
        }
    
    async def stop(self) -> Dict[str, Any]:
        """Stop the scheduler"""
        if not self.running:
            return {"status": "not_running"}
        
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("[Scheduler] Stopped")
        return {"status": "stopped"}
    
    async def run_now(self, job_name: str) -> Dict[str, Any]:
        """Run specific job immediately"""
        if job_name not in self.jobs:
            return {"error": f"Unknown job: {job_name}"}
        
        job = self.jobs[job_name]
        return await self._run_job(job)
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status"""
        return {
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "running": self.running,
            "jobs": {
                name: {
                    "name": job.name,
                    "source": job.source,
                    "entity": job.entity,
                    "interval_minutes": job.interval_minutes,
                    "enabled": job.enabled,
                    "status": job.last_status.value,
                    "last_run": job.last_run.isoformat() if job.last_run else None,
                    "run_count": job.run_count,
                    "error_count": job.error_count,
                    "last_error": job.last_error
                }
                for name, job in self.jobs.items()
            }
        }
    
    def enable_job(self, job_name: str) -> Dict[str, Any]:
        """Enable a job"""
        if job_name not in self.jobs:
            return {"error": f"Unknown job: {job_name}"}
        self.jobs[job_name].enabled = True
        return {"job": job_name, "enabled": True}
    
    def disable_job(self, job_name: str) -> Dict[str, Any]:
        """Disable a job"""
        if job_name not in self.jobs:
            return {"error": f"Unknown job: {job_name}"}
        self.jobs[job_name].enabled = False
        return {"job": job_name, "enabled": False}


class IntelHealthMonitor:
    """
    Health monitoring for intel system.
    Tracks source availability, sync status, and data freshness.
    """
    
    def __init__(self, db=None, scheduler: IntelScheduler = None):
        self.db = db
        self.scheduler = scheduler
    
    async def get_health(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        now = datetime.now(timezone.utc)
        
        # Database stats
        db_stats = {}
        if self.db is not None:
            try:
                db_stats = {
                    "intel_projects": await self.db.intel_projects.count_documents({}),
                    "intel_categories": await self.db.intel_categories.count_documents({}),
                    "intel_funding": await self.db.intel_funding.count_documents({}),
                    "intel_unlocks": await self.db.intel_unlocks.count_documents({}),
                    "intel_investors": await self.db.intel_investors.count_documents({})
                }
            except Exception as e:
                db_stats = {"error": str(e)}
        
        # Source status
        sources = {
            "coingecko": {
                "status": "healthy",
                "type": "api",
                "endpoints": ["markets", "categories", "trending", "coin"]
            },
            "dropstab": {
                "status": "limited",
                "type": "ssr_scraper",
                "note": "Most pages blocked (404) from server IP"
            },
            "cryptorank": {
                "status": "ready",
                "type": "browser_discovery",
                "note": "Requires Playwright for discovery"
            }
        }
        
        # Last syncs from scheduler
        last_syncs = {}
        if self.scheduler:
            for name, job in self.scheduler.jobs.items():
                if job.last_run:
                    last_syncs[name] = {
                        "source": job.source,
                        "entity": job.entity,
                        "last_run": job.last_run.isoformat(),
                        "status": job.last_status.value,
                        "age_minutes": int((now - job.last_run).total_seconds() / 60)
                    }
        
        # Errors in last 24h
        errors_24h = []
        if self.scheduler:
            for name, job in self.scheduler.jobs.items():
                if job.last_error and job.last_run:
                    if (now - job.last_run).total_seconds() < 86400:
                        errors_24h.append({
                            "job": name,
                            "error": job.last_error,
                            "time": job.last_run.isoformat()
                        })
        
        return {
            "ts": int(now.timestamp() * 1000),
            "scheduler_running": self.scheduler.running if self.scheduler else False,
            "jobs_total": len(self.scheduler.jobs) if self.scheduler else 0,
            "jobs_enabled": len([j for j in self.scheduler.jobs.values() if j.enabled]) if self.scheduler else 0,
            "sources": sources,
            "last_syncs": last_syncs,
            "errors_24h": errors_24h,
            "database_stats": db_stats
        }


# Singleton instances (initialized with db in server.py)
intel_scheduler: Optional[IntelScheduler] = None
intel_health: Optional[IntelHealthMonitor] = None


def init_scheduler(db):
    """Initialize scheduler with database"""
    global intel_scheduler, intel_health
    intel_scheduler = IntelScheduler(db)
    intel_health = IntelHealthMonitor(db, intel_scheduler)
    return intel_scheduler, intel_health
