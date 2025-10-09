"""
Integration tests for API endpoints
Testing the REST API with real DB interactions
"""

import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta, timezone

from app.main import app
from app.models.bridge import Bridge, BridgeStatus, Incident


@pytest.mark.asyncio
class TestBridgeEndpoints:
    """Tests for /api/v1/bridges endpoints"""

    async def test_get_all_bridges(self, db_session, sample_bridges):
        """GET /api/v1/bridges returns all active bridges"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/bridges/")

        assert response.status_code == 200
        data = response.json()

        # should return only active bridges (2 out of 3 in fixture)
        assert len(data) == 2
        assert all(bridge["is_active"] for bridge in data)

    async def test_get_all_bridges_includes_status(
        self,
        db_session,
        sample_bridge,
        sample_status
    ):
        """Bridge list includes latest status"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/bridges/")

        assert response.status_code == 200
        data = response.json()

        bridge_data = next(b for b in data if b["id"] == sample_bridge.id)
        assert bridge_data["latest_status"] is not None
        assert bridge_data["latest_status"]["status"] == "UP"
        assert bridge_data["latest_status"]["response_time"] == 2500

    async def test_get_all_bridges_inactive_filter(
        self,
        db_session,
        sample_bridges
    ):
        """Can get inactive bridges with active_only=false"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/bridges/",
                params={"active_only": False}
            )

        assert response.status_code == 200
        data = response.json()

        # should return all 3 bridges
        assert len(data) == 3

    async def test_get_bridge_by_id(self, db_session, sample_bridge):
        """GET /api/v1/bridges/{id} returns bridge details"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(f"/api/v1/bridges/{sample_bridge.id}")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == sample_bridge.id
        assert data["name"] == sample_bridge.name
        assert data["api_endpoint"] == sample_bridge.api_endpoint

    async def test_get_bridge_not_found(self, db_session):
        """GET /api/v1/bridges/{id} returns 404 for non-existent bridge"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/bridges/99999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_get_bridge_status_history(
        self,
        db_session,
        sample_bridge
    ):
        """GET /api/v1/bridges/{id}/status returns status history"""
        # create some status records
        for i in range(5):
            status = BridgeStatus(
                bridge_id=sample_bridge.id,
                status="UP",
                response_time=2000 + i * 100,
                checked_at=datetime.now(timezone.utc) - timedelta(hours=i)
            )
            db_session.add(status)
        await db_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/bridges/{sample_bridge.id}/status"
            )

        assert response.status_code == 200
        data = response.json()

        assert data["bridge"]["id"] == sample_bridge.id
        assert data["status_count"] == 5
        assert len(data["statuses"]) == 5

        # should be ordered by time desc
        assert data["statuses"][0]["response_time"] == 2000

    async def test_get_bridge_status_custom_period(
        self,
        db_session,
        sample_bridge
    ):
        """Can filter status history by hours"""
        # create old status (25 hours ago)
        old_status = BridgeStatus(
            bridge_id=sample_bridge.id,
            status="DOWN",
            checked_at=datetime.now(timezone.utc) - timedelta(hours=25)
        )
        db_session.add(old_status)

        # create recent status (1 hour ago)
        recent_status = BridgeStatus(
            bridge_id=sample_bridge.id,
            status="UP",
            checked_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        db_session.add(recent_status)
        await db_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/bridges/{sample_bridge.id}/status",
                params={"hours": 24}
            )

        assert response.status_code == 200
        data = response.json()

        # should only return recent status
        assert data["status_count"] == 1
        assert data["statuses"][0]["status"] == "UP"

    async def test_get_bridge_incidents(
        self,
        db_session,
        sample_bridge,
        sample_incident
    ):
        """GET /api/v1/bridges/{id}/incidents returns incidents"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/bridges/{sample_bridge.id}/incidents"
            )

        assert response.status_code == 200
        data = response.json()

        assert data["bridge_id"] == sample_bridge.id
        assert data["incident_count"] == 1
        assert len(data["incidents"]) == 1
        assert data["incidents"][0]["title"] == sample_incident.title

    async def test_get_bridge_incidents_active_only(
        self,
        db_session,
        sample_bridge
    ):
        """Can filter for active incidents only"""
        # create active incident
        active = Incident(
            bridge_id=sample_bridge.id,
            title="Active Issue",
            status="ACTIVE",
            severity="HIGH"
        )
        db_session.add(active)

        # create resolved incident
        resolved = Incident(
            bridge_id=sample_bridge.id,
            title="Resolved Issue",
            status="RESOLVED",
            severity="MEDIUM",
            resolved_at=datetime.now(timezone.utc)
        )
        db_session.add(resolved)
        await db_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/bridges/{sample_bridge.id}/incidents",
                params={"active_only": True}
            )

        assert response.status_code == 200
        data = response.json()

        # should only return active
        assert data["incident_count"] == 1
        assert data["incidents"][0]["status"] == "ACTIVE"

    async def test_trigger_manual_check(
        self,
        db_session,
        sample_bridge,
        mock_http_response
    ):
        """POST /api/v1/bridges/{id}/check triggers manual check"""
        from unittest.mock import patch

        mock_response = mock_http_response(status=200, json_data={})

        with patch('app.services.bridge_monitor.BridgeMonitor._check_api_endpoint',
                   return_value=mock_response):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    f"/api/v1/bridges/{sample_bridge.id}/check"
                )

        assert response.status_code == 200
        data = response.json()

        assert data["bridge"] == sample_bridge.name
        assert data["status"] in ["UP", "DOWN", "SLOW", "WARNING"]
        assert "checked_at" in data

    async def test_get_all_active_incidents(
        self,
        db_session,
        sample_bridges
    ):
        """GET /api/v1/bridges/incidents/active returns all active incidents"""
        # create incidents for different bridges
        for bridge in sample_bridges[:2]:  # only active bridges
            incident = Incident(
                bridge_id=bridge.id,
                title=f"{bridge.name} incident",
                status="ACTIVE",
                severity="HIGH"
            )
            db_session.add(incident)
        await db_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/bridges/incidents/active")

        assert response.status_code == 200
        data = response.json()

        assert data["active_incident_count"] == 2
        assert len(data["incidents"]) == 2

        # should include bridge info
        assert all("bridge" in inc for inc in data["incidents"])


@pytest.mark.asyncio
class TestHealthEndpoints:
    """Tests for health check endpoints"""

    async def test_health_check(self, db_session, mock_redis_client):
        """GET /health returns health status"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] in ["healthy", "degraded"]
        assert "components" in data
        assert "database" in data["components"]
        assert "redis" in data["components"]
        assert "timestamp" in data

    async def test_readiness_check_success(self, db_session, mock_redis_client):
        """GET /health/ready returns ready when all services OK"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()

        assert data["ready"] is True

    async def test_liveness_check(self):
        """GET /health/live always returns alive"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health/live")

        assert response.status_code == 200
        data = response.json()

        assert data["alive"] is True
        assert "timestamp" in data


@pytest.mark.asyncio
class TestRootEndpoint:
    """Tests for root endpoint"""

    async def test_root_endpoint(self):
        """GET / returns API info"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "Bridge Status Bot API"
        assert data["status"] == "operational"
        assert "endpoints" in data
        assert "docs" in data["endpoints"]