"""
Job Queue - Redis-based task queue for scraper workers
"""

import os
import json
import time
import logging
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import asdict
import redis

from .models import Job

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
QUEUE_KEY = "intel:scraper:jobs"
PROCESSING_KEY = "intel:scraper:processing"
COMPLETED_KEY = "intel:scraper:completed"
FAILED_KEY = "intel:scraper:failed"


class JobQueue:
    """
    Redis-based job queue for scraper workers.
    
    Features:
    - FIFO queue with priority support
    - Job deduplication
    - Processing tracking
    - Failed job handling
    """
    
    def __init__(self, redis_url: str = REDIS_URL):
        self._redis_url = redis_url
        self._client: Optional[redis.Redis] = None
    
    @property
    def client(self) -> redis.Redis:
        """Lazy Redis connection"""
        if self._client is None:
            self._client = redis.Redis.from_url(
                self._redis_url,
                decode_responses=True
            )
        return self._client
    
    def _generate_job_id(self, source: str, kind: str, target: str) -> str:
        """Generate unique job ID"""
        return f"{source}:{kind}:{target}:{int(time.time())}"
    
    # ═══════════════════════════════════════════════════════════════
    # PUSH JOBS
    # ═══════════════════════════════════════════════════════════════
    
    def push(self, job: Job) -> str:
        """
        Add job to queue.
        
        Returns:
            Job ID
        """
        if not job.id:
            job.id = self._generate_job_id(job.source, job.kind, job.target)
        if not job.created_at:
            job.created_at = time.time()
        
        data = json.dumps(asdict(job), ensure_ascii=False)
        
        # Use priority score for sorted set (lower = higher priority)
        score = (10 - job.priority) * 1e10 + job.created_at
        
        self.client.zadd(QUEUE_KEY, {data: score})
        logger.info(f"[Queue] Pushed job: {job.id}")
        
        return job.id
    
    def push_discover(self, source: str, targets: List[str] = None, priority: int = 5) -> List[str]:
        """
        Push discovery jobs for a source.
        
        Args:
            source: dropstab or cryptorank
            targets: Specific targets or all
            priority: Job priority (1-10)
        
        Returns:
            List of job IDs
        """
        from .runner import DROPSTAB_TARGETS, CRYPTORANK_TARGETS
        
        if source == "dropstab":
            all_targets = list(DROPSTAB_TARGETS.keys())
        elif source == "cryptorank":
            all_targets = list(CRYPTORANK_TARGETS.keys())
        else:
            raise ValueError(f"Unknown source: {source}")
        
        targets = targets or all_targets
        job_ids = []
        
        for target in targets:
            job = Job(
                id="",
                source=source,
                kind="discover",
                target=target,
                payload={"headless": True},
                priority=priority
            )
            job_id = self.push(job)
            job_ids.append(job_id)
        
        return job_ids
    
    def push_sync(self, source: str, targets: List[str] = None, priority: int = 5) -> List[str]:
        """Push sync jobs for a source"""
        from .runner import DROPSTAB_TARGETS, CRYPTORANK_TARGETS
        
        if source == "dropstab":
            all_targets = list(DROPSTAB_TARGETS.keys())
        elif source == "cryptorank":
            all_targets = list(CRYPTORANK_TARGETS.keys())
        else:
            raise ValueError(f"Unknown source: {source}")
        
        targets = targets or all_targets
        job_ids = []
        
        for target in targets:
            job = Job(
                id="",
                source=source,
                kind="sync",
                target=target,
                payload={},
                priority=priority
            )
            job_id = self.push(job)
            job_ids.append(job_id)
        
        return job_ids
    
    def push_parse(self, source: str, target: str, raw_file: str, priority: int = 5) -> str:
        """
        Push parse job for a raw data file.
        
        Args:
            source: dropstab or cryptorank
            target: Data type hint (unlocks, funding, etc)
            raw_file: Path to raw JSON file
            priority: Job priority
        
        Returns:
            Job ID
        """
        job = Job(
            id="",
            source=source,
            kind="parse",
            target=target,
            payload={"raw_file": raw_file},
            priority=priority
        )
        return self.push(job)
    
    # ═══════════════════════════════════════════════════════════════
    # POP JOBS
    # ═══════════════════════════════════════════════════════════════
    
    def pop(self, timeout_s: int = 5) -> Optional[Job]:
        """
        Pop highest priority job from queue.
        
        Uses ZPOPMIN for priority ordering.
        Moves job to processing set.
        """
        # Try to get job with priority
        result = self.client.zpopmin(QUEUE_KEY, count=1)
        
        if not result:
            return None
        
        data, score = result[0]
        job_dict = json.loads(data)
        job = Job(**job_dict)
        
        # Track in processing set
        self.client.hset(PROCESSING_KEY, job.id, data)
        
        logger.info(f"[Queue] Popped job: {job.id}")
        return job
    
    def pop_blocking(self, timeout_s: int = 30) -> Optional[Job]:
        """
        Pop job with blocking wait.
        
        Uses BZPOPMIN for efficient waiting.
        """
        result = self.client.bzpopmin(QUEUE_KEY, timeout=timeout_s)
        
        if not result:
            return None
        
        key, data, score = result
        job_dict = json.loads(data)
        job = Job(**job_dict)
        
        # Track in processing set
        self.client.hset(PROCESSING_KEY, job.id, data)
        
        logger.info(f"[Queue] Popped job: {job.id}")
        return job
    
    # ═══════════════════════════════════════════════════════════════
    # JOB COMPLETION
    # ═══════════════════════════════════════════════════════════════
    
    def complete(self, job_id: str, result: Dict[str, Any] = None):
        """Mark job as completed"""
        # Remove from processing
        job_data = self.client.hget(PROCESSING_KEY, job_id)
        self.client.hdel(PROCESSING_KEY, job_id)
        
        # Add to completed with result
        completed_data = {
            "job_id": job_id,
            "completed_at": time.time(),
            "result": result or {}
        }
        self.client.lpush(COMPLETED_KEY, json.dumps(completed_data))
        self.client.ltrim(COMPLETED_KEY, 0, 999)  # Keep last 1000
        
        logger.info(f"[Queue] Completed job: {job_id}")
    
    def fail(self, job_id: str, error: str, retry: bool = False):
        """Mark job as failed"""
        job_data = self.client.hget(PROCESSING_KEY, job_id)
        self.client.hdel(PROCESSING_KEY, job_id)
        
        failed_data = {
            "job_id": job_id,
            "failed_at": time.time(),
            "error": error
        }
        self.client.lpush(FAILED_KEY, json.dumps(failed_data))
        self.client.ltrim(FAILED_KEY, 0, 999)
        
        if retry and job_data:
            # Re-queue with lower priority
            job_dict = json.loads(job_data)
            job_dict["priority"] = max(1, job_dict.get("priority", 5) - 1)
            job_dict["payload"]["retry_count"] = job_dict.get("payload", {}).get("retry_count", 0) + 1
            
            if job_dict["payload"]["retry_count"] < 3:
                self.client.zadd(QUEUE_KEY, {json.dumps(job_dict): time.time()})
                logger.info(f"[Queue] Re-queued failed job: {job_id}")
        
        logger.warning(f"[Queue] Failed job: {job_id} -> {error}")
    
    # ═══════════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════════
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            "pending": self.client.zcard(QUEUE_KEY),
            "processing": self.client.hlen(PROCESSING_KEY),
            "completed": self.client.llen(COMPLETED_KEY),
            "failed": self.client.llen(FAILED_KEY)
        }
    
    def get_pending_jobs(self, limit: int = 50) -> List[Dict]:
        """Get pending jobs"""
        items = self.client.zrange(QUEUE_KEY, 0, limit - 1)
        return [json.loads(item) for item in items]
    
    def get_processing_jobs(self) -> List[Dict]:
        """Get jobs currently processing"""
        items = self.client.hgetall(PROCESSING_KEY)
        return [json.loads(v) for v in items.values()]
    
    def get_recent_completed(self, limit: int = 20) -> List[Dict]:
        """Get recently completed jobs"""
        items = self.client.lrange(COMPLETED_KEY, 0, limit - 1)
        return [json.loads(item) for item in items]
    
    def get_recent_failed(self, limit: int = 20) -> List[Dict]:
        """Get recently failed jobs"""
        items = self.client.lrange(FAILED_KEY, 0, limit - 1)
        return [json.loads(item) for item in items]
    
    def clear_queue(self):
        """Clear all pending jobs"""
        self.client.delete(QUEUE_KEY)
        logger.info("[Queue] Cleared pending jobs")
    
    def clear_all(self):
        """Clear all queue data"""
        self.client.delete(QUEUE_KEY, PROCESSING_KEY, COMPLETED_KEY, FAILED_KEY)
        logger.info("[Queue] Cleared all queue data")


# Singleton
job_queue = JobQueue()
