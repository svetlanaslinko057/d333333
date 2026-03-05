"""
Unlock API Routes
Layer 2: Token Unlocks
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/unlocks", tags=["unlocks"])


def get_unlock_service():
    """Dependency to get unlock service"""
    from server import db
    from ..services.unlock_service import UnlockService
    return UnlockService(db)


# ═══════════════════════════════════════════════════════════════
# PROJECTS
# ═══════════════════════════════════════════════════════════════

@router.get("/projects")
async def list_projects(
    search: Optional[str] = Query(None, description="Search by name or symbol"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service = Depends(get_unlock_service)
):
    """List all projects with unlock data"""
    projects = await service.list_projects(limit=limit, offset=offset, search=search)
    total = await service.count_projects()
    
    return {
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        "total": total,
        "limit": limit,
        "offset": offset,
        "projects": projects
    }


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    service = Depends(get_unlock_service)
):
    """Get project details"""
    project = await service.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return {
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        "project": project
    }


@router.get("/projects/{project_id}/summary")
async def get_project_summary(
    project_id: str,
    service = Depends(get_unlock_service)
):
    """Get unlock summary for a project"""
    summary = await service.get_project_summary(project_id)
    
    if not summary:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return {
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        **summary
    }


@router.get("/projects/{project_id}/unlocks")
async def get_project_unlocks(
    project_id: str,
    include_past: bool = Query(False, description="Include past unlocks"),
    limit: int = Query(50, ge=1, le=200),
    service = Depends(get_unlock_service)
):
    """Get all unlocks for a specific project"""
    # Check project exists
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    unlocks = await service.get_project_unlocks(
        project_id=project_id,
        include_past=include_past,
        limit=limit
    )
    
    return {
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        "project_id": project_id,
        "project_symbol": project.get('symbol'),
        "count": len(unlocks),
        "unlocks": unlocks
    }


# ═══════════════════════════════════════════════════════════════
# UNLOCKS
# ═══════════════════════════════════════════════════════════════

@router.get("")
async def list_unlocks(
    project_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description="ISO date string"),
    to_date: Optional[str] = Query(None, description="ISO date string"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service = Depends(get_unlock_service)
):
    """List all token unlocks with filters"""
    # Parse dates
    from_dt = datetime.fromisoformat(from_date) if from_date else None
    to_dt = datetime.fromisoformat(to_date) if to_date else None
    
    unlocks = await service.list_unlocks(
        project_id=project_id,
        category=category,
        from_date=from_dt,
        to_date=to_dt,
        limit=limit,
        offset=offset
    )
    
    return {
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        "count": len(unlocks),
        "limit": limit,
        "offset": offset,
        "unlocks": unlocks
    }


@router.get("/upcoming")
async def get_upcoming_unlocks(
    days: int = Query(30, ge=1, le=180, description="Days ahead"),
    min_value_usd: Optional[float] = Query(None, description="Minimum USD value"),
    min_percent: Optional[float] = Query(None, description="Minimum % of supply"),
    limit: int = Query(50, ge=1, le=200),
    service = Depends(get_unlock_service)
):
    """Get upcoming token unlocks"""
    unlocks = await service.get_upcoming_unlocks(
        days=days,
        min_value_usd=min_value_usd,
        min_percent=min_percent,
        limit=limit
    )
    
    return {
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        "days": days,
        "count": len(unlocks),
        "unlocks": unlocks
    }


@router.get("/{unlock_id}")
async def get_unlock(
    unlock_id: str,
    service = Depends(get_unlock_service)
):
    """Get specific unlock by ID"""
    unlock = await service.get_unlock(unlock_id)
    
    if not unlock:
        raise HTTPException(status_code=404, detail="Unlock not found")
    
    return {
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        "unlock": unlock
    }


# ═══════════════════════════════════════════════════════════════
# SYNC & STATS
# ═══════════════════════════════════════════════════════════════

@router.post("/sync")
async def sync_unlocks(
    source: str = Query("dropstab", description="Data source"),
    service = Depends(get_unlock_service)
):
    """Manually trigger unlock data sync"""
    from ..scraper.dropstab import dropstab_scraper
    
    try:
        if source == "dropstab":
            result = await dropstab_scraper.sync_all()
            
            # Save projects
            for project in result['projects']:
                await service.create_project(project)
            
            # Save unlocks
            count = await service.bulk_upsert_unlocks(result['unlocks'])
            
            return {
                "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
                "source": source,
                "success": True,
                "projects_synced": len(result['projects']),
                "unlocks_synced": count,
                "raw_fetched": result['raw_count']
            }
        else:
            raise HTTPException(status_code=400, detail=f"Unknown source: {source}")
            
    except Exception as e:
        logger.error(f"[Unlock Sync] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/overview")
async def get_stats(
    service = Depends(get_unlock_service)
):
    """Get unlock statistics"""
    stats = await service.stats()
    
    return {
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
        **stats
    }
