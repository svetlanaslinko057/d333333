"""
Scraper Worker - Processes jobs from the queue
"""

import asyncio
import logging
import signal
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from .queue import job_queue, Job
from .runner import scraper_runner
from .models import CapturedRequest

logger = logging.getLogger(__name__)


class ScraperWorker:
    """
    Worker that processes scraper jobs from the queue.
    
    Features:
    - Graceful shutdown
    - Job timeout handling
    - Error recovery
    - Stats tracking
    """
    
    def __init__(self, worker_id: str = "worker-1"):
        self.worker_id = worker_id
        self.running = False
        self.current_job: Optional[Job] = None
        self.stats = {
            "started_at": None,
            "jobs_processed": 0,
            "jobs_failed": 0,
            "last_job_at": None
        }
    
    async def start(self):
        """Start the worker loop"""
        self.running = True
        self.stats["started_at"] = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"[Worker:{self.worker_id}] Starting...")
        
        while self.running:
            try:
                # Pop job from queue (blocking)
                job = job_queue.pop()
                
                if not job:
                    # No job available, wait and retry
                    await asyncio.sleep(2)
                    continue
                
                self.current_job = job
                self.stats["last_job_at"] = datetime.now(timezone.utc).isoformat()
                
                logger.info(f"[Worker:{self.worker_id}] Processing: {job.id}")
                
                # Process job
                try:
                    result = await self._process_job(job)
                    job_queue.complete(job.id, result)
                    self.stats["jobs_processed"] += 1
                    
                except Exception as e:
                    logger.error(f"[Worker:{self.worker_id}] Job failed: {job.id} -> {e}")
                    job_queue.fail(job.id, str(e), retry=True)
                    self.stats["jobs_failed"] += 1
                
                self.current_job = None
                
                # Small delay between jobs
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"[Worker:{self.worker_id}] Error in worker loop: {e}")
                await asyncio.sleep(5)
        
        logger.info(f"[Worker:{self.worker_id}] Stopped")
    
    async def _process_job(self, job: Job) -> Dict[str, Any]:
        """
        Process a single job.
        
        Job kinds:
        - discover: Run browser discovery for endpoints
        - sync: Sync data using registered endpoints
        - parse: Parse raw data (TODO)
        """
        if job.kind == "discover":
            return await self._process_discover(job)
        elif job.kind == "sync":
            return await self._process_sync(job)
        elif job.kind == "parse":
            return await self._process_parse(job)
        else:
            raise ValueError(f"Unknown job kind: {job.kind}")
    
    async def _process_discover(self, job: Job) -> Dict[str, Any]:
        """Process discovery job"""
        headless = job.payload.get("headless", True)
        
        if job.source == "dropstab":
            result = await scraper_runner.discover_dropstab(
                targets=[job.target],
                headless=headless
            )
        elif job.source == "cryptorank":
            result = await scraper_runner.discover_cryptorank(
                targets=[job.target],
                headless=headless
            )
        else:
            raise ValueError(f"Unknown source: {job.source}")
        
        return result
    
    async def _process_sync(self, job: Job) -> Dict[str, Any]:
        """Process sync job"""
        result = await scraper_runner.sync(job.source, job.target)
        return result
    
    async def _process_parse(self, job: Job) -> Dict[str, Any]:
        """
        Process parse job.
        
        Reads raw data from storage, parses it, and stores to normalized tables.
        """
        raw_file = job.payload.get("raw_file")
        
        if not raw_file:
            return {"error": "No raw_file specified"}
        
        # Import dependencies
        from ..scraper_engine.raw_store import raw_store
        from ..normalization import create_normalization_engine
        from server import db
        
        # Read raw data
        raw_doc = raw_store.get(raw_file)
        payload = raw_doc.get("payload", [])
        
        if not payload:
            return {"error": "Empty payload"}
        
        # Get parser based on source
        if job.source == "dropstab":
            from ..sources.dropstab.parsers import parse_auto
        elif job.source == "cryptorank":
            from ..sources.cryptorank.adapters import parse_auto
        else:
            return {"error": f"Unknown source: {job.source}"}
        
        # Parse the data
        parsed = parse_auto(payload, target_hint=job.target)
        
        # Store to normalized tables
        engine = create_normalization_engine(db)
        
        results = {}
        
        if parsed.get("unlocks"):
            results["unlocks"] = await engine.store_unlocks(parsed["unlocks"])
        
        if parsed.get("funding"):
            results["funding"] = await engine.store_funding(parsed["funding"])
        
        if parsed.get("investors"):
            results["investors"] = await engine.store_investors(parsed["investors"])
        
        if parsed.get("sales"):
            results["sales"] = await engine.store_sales(parsed["sales"])
        
        return {
            "status": "parsed",
            "source": job.source,
            "target": job.target,
            "raw_file": raw_file,
            "results": results
        }
    
    def stop(self):
        """Signal worker to stop"""
        self.running = False
        logger.info(f"[Worker:{self.worker_id}] Stop signal received")
    
    def get_status(self) -> Dict[str, Any]:
        """Get worker status"""
        return {
            "worker_id": self.worker_id,
            "running": self.running,
            "current_job": self.current_job.id if self.current_job else None,
            **self.stats
        }


# Global worker instance
_worker: Optional[ScraperWorker] = None
_worker_task: Optional[asyncio.Task] = None


async def start_worker(worker_id: str = "worker-1") -> Dict[str, Any]:
    """Start a worker in background"""
    global _worker, _worker_task
    
    if _worker and _worker.running:
        return {"error": "Worker already running", "worker": _worker.get_status()}
    
    _worker = ScraperWorker(worker_id)
    _worker_task = asyncio.create_task(_worker.start())
    
    return {"ok": True, "message": f"Worker {worker_id} started"}


async def stop_worker() -> Dict[str, Any]:
    """Stop the running worker"""
    global _worker, _worker_task
    
    if not _worker or not _worker.running:
        return {"error": "No worker running"}
    
    _worker.stop()
    
    if _worker_task:
        # Wait for graceful shutdown
        try:
            await asyncio.wait_for(_worker_task, timeout=10)
        except asyncio.TimeoutError:
            _worker_task.cancel()
    
    status = _worker.get_status()
    _worker = None
    _worker_task = None
    
    return {"ok": True, "message": "Worker stopped", "final_stats": status}


def get_worker_status() -> Dict[str, Any]:
    """Get current worker status"""
    if not _worker:
        return {"running": False, "message": "No worker initialized"}
    return _worker.get_status()
