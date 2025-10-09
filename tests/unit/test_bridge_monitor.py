"""
Unit tests for bridge monitoring logic
Testing the core monitoring service
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from app.services.bridge_monitor import BridgeMonitor
from app.models.bridge import BridgeStatus, Incident


@pytest.mark.asyncio
class TestBridgeMonitor:
    """Tests for BridgeMonitor class"""

    async def test_initialize_creates_http_session(
            self,
            db_session,
            mock_redis_client
    ):
        """Monitor creates HTTP session on initialize"""
        monitor = BridgeMonitor(db_session, mock_redis_client)

        assert monitor.http_session is None

        await monitor.initialize()

        assert monitor.http_session is not None

        await monitor.close()

    async def test_close_cleans_up_session(
            self,
            db_session,
            mock_redis_client
    ):
        """Monitor closes HTTP session on cleanup"""
        monitor = BridgeMonitor(db_session, mock_redis_client)
        await monitor.initialize()

        assert monitor.http_session is not None

        await monitor.close()

        assert monitor.http_session is None

    async def test_check_bridge_health_success(
            self,
            db_session,
            mock_redis_client,
            sample_bridge,
            mock_http_response
    ):
        """Successful bridge check saves status to DB"""
        monitor = BridgeMonitor(db_session, mock_redis_client)
        await monitor.initialize()

        # mock HTTP response
        mock_response = mock_http_response(status=200,
                                           json_data={'healthy': True})

        with patch.object(monitor, '_check_api_endpoint',
                          return_value=mock_response):
            status = await monitor.check_bridge_health(sample_bridge)

        assert status is not None
        assert status.bridge_id == sample_bridge.id
        assert status.status in ["UP", "SLOW", "WARNING", "DOWN"]
        assert status.response_time is not None

        # verify saved to DB
        result = await db_session.execute(
            select(BridgeStatus).where(
                BridgeStatus.bridge_id == sample_bridge.id)
        )
        db_status = result.scalar_one_or_none()
        assert db_status is not None

        await monitor.close()

    async def test_check_bridge_health_timeout(
            self,
            db_session,
            mock_redis_client,
            sample_bridge
    ):
        """Timeout results in DOWN status"""
        monitor = BridgeMonitor(db_session, mock_redis_client)
        await monitor.initialize()

        # mock timeout
        with patch.object(
                monitor,
                '_check_api_endpoint',
                side_effect=TimeoutError("Request timeout")
        ):
            status = await monitor.check_bridge_health(sample_bridge)

        assert status.status == "DOWN"
        assert status.response_time is None
        assert status.error_message == "Request timeout"

        await monitor.close()

    async def test_check_bridge_health_http_error(
            self,
            db_session,
            mock_redis_client,
            sample_bridge,
            mock_http_response
    ):
        """HTTP errors result in DOWN status"""
        monitor = BridgeMonitor(db_session, mock_redis_client)
        await monitor.initialize()

        # mock 500 error
        mock_response = mock_http_response(status=500)

        with patch.object(monitor, '_check_api_endpoint',
                          return_value=mock_response):
            status = await monitor.check_bridge_health(sample_bridge)

        assert status.status == "DOWN"

        await monitor.close()

    async def test_status_change_creates_incident(
            self,
            db_session,
            mock_redis_client,
            sample_bridge,
            mock_http_response
    ):
        """Status change from UP to DOWN creates incident"""
        monitor = BridgeMonitor(db_session, mock_redis_client)
        await monitor.initialize()

        # set cached status to UP
        await mock_redis_client.set(f"bridge:{sample_bridge.id}:status", "UP")

        # mock response that will result in DOWN
        mock_response = mock_http_response(status=500)

        with patch.object(monitor, '_check_api_endpoint',
                          return_value=mock_response):
            await monitor.check_bridge_health(sample_bridge)

        # check incident was created
        result = await db_session.execute(
            select(Incident).where(
                Incident.bridge_id == sample_bridge.id,
                Incident.status == "ACTIVE"
            )
        )
        incident = result.scalar_one_or_none()

        assert incident is not None
        assert incident.severity in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

        await monitor.close()

    async def test_recovery_closes_incidents(
            self,
            db_session,
            mock_redis_client,
            sample_bridge,
            sample_incident,
            mock_http_response
    ):
        """Recovery from DOWN to UP closes active incidents"""
        monitor = BridgeMonitor(db_session, mock_redis_client)
        await monitor.initialize()

        # set cached status to DOWN
        await mock_redis_client.set(f"bridge:{sample_bridge.id}:status",
                                    "DOWN")

        # mock successful response
        mock_response = mock_http_response(status=200, json_data={'ok': True})

        with patch.object(monitor, '_check_api_endpoint',
                          return_value=mock_response):
            with patch('time.time', return_value=1000):  # fast response
                await monitor.check_bridge_health(sample_bridge)

        # refresh incident
        await db_session.refresh(sample_incident)

        # incident should be resolved
        assert sample_incident.status == "RESOLVED"
        assert sample_incident.resolved_at is not None

        await monitor.close()

    async def test_check_all_bridges(
            self,
            db_session,
            mock_redis_client,
            sample_bridges,
            mock_http_response
    ):
        """check_all_bridges processes all active bridges"""
        monitor = BridgeMonitor(db_session, mock_redis_client)
        await monitor.initialize()

        mock_response = mock_http_response(status=200)

        with patch.object(monitor, '_check_api_endpoint',
                          return_value=mock_response):
            results = await monitor.check_all_bridges()

        # should check only active bridges (2 out of 3)
        assert len(results) == 2

        # verify statuses were saved
        result = await db_session.execute(select(BridgeStatus))
        statuses = result.scalars().all()

        assert len(statuses) == 2

        await monitor.close()

    async def test_websocket_broadcast_on_status_change(
            self,
            db_session,
            mock_redis_client,
            sample_bridge,
            mock_http_response
    ):
        """Status change triggers WebSocket broadcast"""
        mock_ws_manager = MagicMock()
        mock_ws_manager.broadcast_bridge_status = AsyncMock()

        monitor = BridgeMonitor(
            db_session,
            mock_redis_client,
            websocket_manager=mock_ws_manager
        )
        await monitor.initialize()

        # set cached status
        await mock_redis_client.set(f"bridge:{sample_bridge.id}:status", "UP")

        # trigger status change
        mock_response = mock_http_response(status=500)

        with patch.object(monitor, '_check_api_endpoint',
                          return_value=mock_response):
            await monitor.check_bridge_health(sample_bridge)

        # verify broadcast was called
        assert mock_ws_manager.broadcast_bridge_status.called

        await monitor.close()

    async def test_notification_on_status_change(
            self,
            db_session,
            mock_redis_client,
            sample_bridge,
            mock_http_response
    ):
        """Status change triggers notification"""
        mock_notification = MagicMock()
        mock_notification.send_bridge_alert = AsyncMock()

        monitor = BridgeMonitor(
            db_session,
            mock_redis_client,
            notification_service=mock_notification
        )
        await monitor.initialize()

        # set cached status
        await mock_redis_client.set(f"bridge:{sample_bridge.id}:status", "UP")

        # trigger status change
        mock_response = mock_http_response(status=500)

        with patch.object(monitor, '_check_api_endpoint',
                          return_value=mock_response):
            await monitor.check_bridge_health(sample_bridge)

        # verify notification was sent
        assert mock_notification.send_bridge_alert.called

        await monitor.close()