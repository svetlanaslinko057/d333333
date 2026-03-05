"""
Scraper Engine Package

Iron-clad scraper with:
- Multi-layer fetching (Direct API -> Browser -> DOM)
- Request blueprint capture and replay
- Redis job queue with workers
- Raw data storage for reparse
- Endpoint registry with scoring
"""

from .models import CapturedRequest, Job, RawRecord
from .registry import endpoint_registry
from .raw_store import raw_store
from .replay import replay_client
from .discovery import browser_discovery
from .runner import scraper_runner, DROPSTAB_TARGETS, CRYPTORANK_TARGETS
from .queue import job_queue
from .worker import start_worker, stop_worker, get_worker_status

__all__ = [
    # Models
    "CapturedRequest",
    "Job",
    "RawRecord",
    # Core components
    "endpoint_registry",
    "raw_store",
    "replay_client",
    "browser_discovery",
    "scraper_runner",
    # Queue & Worker
    "job_queue",
    "start_worker",
    "stop_worker",
    "get_worker_status",
    # Constants
    "DROPSTAB_TARGETS",
    "CRYPTORANK_TARGETS"
]
