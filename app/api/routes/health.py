"""
Health check endpoints
Quick checks to see if everything's alive and kicking
"""

from fastapi import APIRouter, status
from datetime import datetime, timezone
from sqlalchemy import text

from app.core.database import engine
from app.core.redis import redis_client
from app.services.scheduler import bridge_scheduler

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """
    Basic health check - are we up?
    Returns status of database, redis, and scheduler
    """

    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {}
    }

    # check if PostgreSQL is alive
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health_status["components"]["database"] = "healthy"
    except Exception as e:
        health_status["components"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    # check if Redis is responding
    try:
        if redis_client.redis:
            await redis_client.redis.ping()
            health_status["components"]["redis"] = "healthy"
        else:
            health_status["components"]["redis"] = "not connected"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["components"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    # check if scheduler is running (handle case when not initialized yet)
    if bridge_scheduler and bridge_scheduler.is_running:
        health_status["components"]["scheduler"] = "running"
    elif bridge_scheduler:
        health_status["components"]["scheduler"] = "stopped"
    else:
        health_status["components"]["scheduler"] = "not initialized"

    return health_status


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness probe for Kubernetes
    Are we ready to handle requests?
    """

    try:
        # make sure DB is reachable
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        # make sure Redis is up
        if redis_client.redis:
            await redis_client.redis.ping()
        else:
            return {"ready": False, "reason": "Redis not connected"}

        return {"ready": True}

    except Exception as e:
        return {"ready": False, "reason": str(e)}


@router.get("/health/live")
async def liveness_check():
    """
    Liveness probe for Kubernetes
    Quick check - is the app still running or did it hang?
    """
    return {"alive": True, "timestamp": datetime.now(timezone.utc).isoformat()}