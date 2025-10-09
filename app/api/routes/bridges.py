"""
API endpoints for working with bridges
CRUD operations and status retrieval
"""

from typing import List
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from app.core.database import get_db, async_session_maker
from app.models.bridge import Bridge, BridgeStatus, Incident
from app.services.bridge_monitor import BridgeMonitor
from app.core.redis import redis_client

router = APIRouter(prefix="/api/v1/bridges", tags=["bridges"])


@router.get("/")
async def get_all_bridges(
        active_only: bool = True,
        db: AsyncSession = Depends(get_db)
):
    """
    Get all bridges with their latest status

    Query params:
        active_only: show only active bridges (default: True)
    """

    query = select(Bridge)

    if active_only:
        query = query.where(Bridge.is_active == True)

    result = await db.execute(query)
    bridges = result.scalars().all()

    # add latest status for each bridge
    bridges_with_status = []
    for bridge in bridges:
        # get latest status
        status_result = await db.execute(
            select(BridgeStatus)
                .where(BridgeStatus.bridge_id == bridge.id)
                .order_by(desc(BridgeStatus.checked_at))
                .limit(1)
        )
        latest_status = status_result.scalar_one_or_none()

        bridges_with_status.append({
            "id": bridge.id,
            "name": bridge.name,
            "api_endpoint": bridge.api_endpoint,
            "is_active": bridge.is_active,
            "latest_status": {
                "status": latest_status.status if latest_status else "UNKNOWN",
                "response_time": latest_status.response_time if latest_status else None,
                "checked_at": latest_status.checked_at.isoformat() if latest_status else None
            } if latest_status else None
        })

    return bridges_with_status


@router.get("/{bridge_id}")
async def get_bridge(
        bridge_id: int,
        db: AsyncSession = Depends(get_db)
):
    """Get detailed info about specific bridge"""

    result = await db.execute(
        select(Bridge).where(Bridge.id == bridge_id)
    )
    bridge = result.scalar_one_or_none()

    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    return bridge


@router.get("/{bridge_id}/status")
async def get_bridge_status_history(
        bridge_id: int,
        hours: int = Query(default=24, ge=1, le=168),  # from 1 hour to week
        db: AsyncSession = Depends(get_db)
):
    """
    Get bridge status history

    Path params:
        bridge_id: bridge ID

    Query params:
        hours: how many hours of history to show (default: 24, max: 168)
    """

    # check that bridge exists
    bridge_result = await db.execute(
        select(Bridge).where(Bridge.id == bridge_id)
    )
    bridge = bridge_result.scalar_one_or_none()

    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    # get statuses for period
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await db.execute(
        select(BridgeStatus)
            .where(
            BridgeStatus.bridge_id == bridge_id,
            BridgeStatus.checked_at >= cutoff_time
        )
            .order_by(desc(BridgeStatus.checked_at))
    )
    statuses = result.scalars().all()

    return {
        "bridge": {
            "id": bridge.id,
            "name": bridge.name
        },
        "period_hours": hours,
        "status_count": len(statuses),
        "statuses": [
            {
                "status": s.status,
                "response_time": s.response_time,
                "error_message": s.error_message,
                "checked_at": s.checked_at.isoformat()
            }
            for s in statuses
        ]
    }


@router.get("/{bridge_id}/incidents")
async def get_bridge_incidents(
        bridge_id: int,
        active_only: bool = True,
        db: AsyncSession = Depends(get_db)
):
    """
    Get bridge incidents

    Query params:
        active_only: show only active incidents (default: True)
    """

    query = select(Incident).where(Incident.bridge_id == bridge_id)

    if active_only:
        query = query.where(Incident.status == "ACTIVE")

    query = query.order_by(desc(Incident.started_at))

    result = await db.execute(query)
    incidents = result.scalars().all()

    return {
        "bridge_id": bridge_id,
        "incident_count": len(incidents),
        "incidents": [
            {
                "id": i.id,
                "title": i.title,
                "description": i.description,
                "status": i.status,
                "severity": i.severity,
                "started_at": i.started_at.isoformat(),
                "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None
            }
            for i in incidents
        ]
    }


@router.post("/{bridge_id}/check")
async def trigger_bridge_check(
        bridge_id: int,
        db: AsyncSession = Depends(get_db)
):
    """
    Trigger manual bridge check (don't wait for schedule)
    Useful for debugging or manual testing
    """

    # get bridge
    result = await db.execute(
        select(Bridge).where(Bridge.id == bridge_id)
    )
    bridge = result.scalar_one_or_none()

    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    # import WebSocket manager for real-time updates
    from app.api.routes.websocket import manager as ws_manager

    # run check with WebSocket support
    # NOTE: using session_maker instead of db session to avoid conflicts
    monitor = BridgeMonitor(
        session_maker=async_session_maker,
        redis_client=redis_client,
        websocket_manager=ws_manager
    )
    await monitor.initialize()

    try:
        status = await monitor.check_bridge_health(bridge)

        return {
            "bridge": bridge.name,
            "status": status.status,
            "response_time": status.response_time,
            "checked_at": status.checked_at.isoformat(),
            "message": "Manual check completed"
        }

    finally:
        await monitor.close()


@router.get("/incidents/active")
async def get_all_active_incidents(db: AsyncSession = Depends(get_db)):
    """Get all active incidents across all bridges"""

    result = await db.execute(
        select(Incident)
            .options(selectinload(Incident.bridge))
            .where(Incident.status == "ACTIVE")
            .order_by(desc(Incident.severity), desc(Incident.started_at))
    )
    incidents = result.scalars().all()

    return {
        "active_incident_count": len(incidents),
        "incidents": [
            {
                "id": i.id,
                "bridge": {
                    "id": i.bridge.id,
                    "name": i.bridge.name
                },
                "title": i.title,
                "severity": i.severity,
                "started_at": i.started_at.isoformat()
            }
            for i in incidents
        ]
    }