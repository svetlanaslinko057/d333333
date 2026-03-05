"""
RAW Data Store
Stores unprocessed scraped data for later parsing
"""

import os
import json
import time
import uuid
import gzip
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

RAW_BASE_DIR = Path("/app/data/raw")


class RawStore:
    """
    Storage for raw scraped data.
    
    Structure:
    /data/raw/
      {source}/
        {target}/
          {YYYYMMDD}/
            {timestamp}_{uuid}.json.gz
    
    Features:
    - Compressed JSON storage
    - Date-based organization
    - Metadata preservation
    - Easy replay/reparse
    """
    
    def __init__(self, base_dir: Path = RAW_BASE_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def put(
        self,
        source: str,
        target: str,
        payload: Any,
        meta: Dict[str, Any] = None,
        compress: bool = True
    ) -> str:
        """
        Store raw data.
        
        Args:
            source: Data source (dropstab, cryptorank)
            target: Target type (unlocks, funding, etc)
            payload: The actual data
            meta: Additional metadata
            compress: Use gzip compression
        
        Returns:
            Path to stored file
        """
        ts = int(time.time())
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        rid = str(uuid.uuid4())[:8]
        
        # Build path
        dir_path = self.base_dir / source / target / date_str
        dir_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"{ts}_{rid}.json"
        if compress:
            filename += ".gz"
        
        file_path = dir_path / filename
        
        # Build document
        doc = {
            "id": rid,
            "source": source,
            "target": target,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "meta": meta or {},
            "payload": payload
        }
        
        # Write
        content = json.dumps(doc, ensure_ascii=False)
        
        if compress:
            with gzip.open(file_path, "wt", encoding="utf-8") as f:
                f.write(content)
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        
        logger.info(f"[RawStore] Saved: {file_path}")
        return str(file_path)
    
    def get(self, path: str) -> Dict[str, Any]:
        """Read raw file"""
        if path.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    
    def list_files(
        self,
        source: str = None,
        target: str = None,
        date: str = None,
        limit: int = 100
    ) -> List[str]:
        """List raw files"""
        if source and target and date:
            dir_path = self.base_dir / source / target / date
        elif source and target:
            dir_path = self.base_dir / source / target
        elif source:
            dir_path = self.base_dir / source
        else:
            dir_path = self.base_dir
        
        if not dir_path.exists():
            return []
        
        files = []
        for p in dir_path.rglob("*.json*"):
            files.append(str(p))
            if len(files) >= limit:
                break
        
        # Sort by modification time (newest first)
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        return files[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        stats = {
            "total_files": 0,
            "total_size_mb": 0,
            "by_source": {}
        }
        
        for source_dir in self.base_dir.iterdir():
            if not source_dir.is_dir():
                continue
            
            source = source_dir.name
            stats["by_source"][source] = {"files": 0, "size_mb": 0}
            
            for f in source_dir.rglob("*.json*"):
                stats["total_files"] += 1
                stats["by_source"][source]["files"] += 1
                size = f.stat().st_size / (1024 * 1024)
                stats["total_size_mb"] += size
                stats["by_source"][source]["size_mb"] += size
        
        stats["total_size_mb"] = round(stats["total_size_mb"], 2)
        for src in stats["by_source"]:
            stats["by_source"][src]["size_mb"] = round(stats["by_source"][src]["size_mb"], 2)
        
        return stats


# Singleton
raw_store = RawStore()
