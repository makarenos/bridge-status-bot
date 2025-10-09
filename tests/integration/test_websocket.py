"""
Integration tests for WebSocket functionality
Testing real-time updates
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from app.api.routes.websocket import ConnectionManager


@pytest.mark.asyncio
class TestWebSocket:
    """Tests for WebSocket connection manager"""

    async def test_connect_websocket(self):
        """Client can connect to WebSocket"""
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        await manager.connect(mock_ws)

        assert mock_ws in manager.active_connections
        assert mock_ws in manager.subscriptions
        assert mock_ws.accept.called

    async def test_disconnect_websocket(self):
        """Client can disconnect from WebSocket"""
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        await manager.connect(mock_ws)
        manager.disconnect(mock_ws)

        assert mock_ws not in manager.active_connections
        assert mock_ws not in manager.subscriptions

    async def test_send_personal_message(self):
        """Manager can send message to specific client"""
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await manager.connect(mock_ws)

        message = {"type": "test", "data": "hello"}
        await manager.send_personal_message(message, mock_ws)

        mock_ws.send_json.assert_called_once_with(message)

    async def test_broadcast_to_all(self):
        """Manager can broadcast to all connected clients"""
        manager = ConnectionManager()

        # connect multiple clients
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()

        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)

        message = {"type": "broadcast", "data": "everyone"}
        await manager.broadcast(message)

        # both should receive message
        assert ws1.send_json.called
        assert ws2.send_json.called

    async def test_subscribe_to_bridges(self):
        """Client can subscribe to specific bridges"""
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        await manager.connect(mock_ws)

        bridge_ids = [1, 2, 3]
        manager.subscribe(mock_ws, bridge_ids)

        assert manager.subscriptions[mock_ws] == bridge_ids

    async def test_broadcast_only_to_subscribed(self):
        """Broadcast sends only to subscribed clients"""
        manager = ConnectionManager()

        # client subscribed to bridge 1
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        await manager.connect(ws1)
        manager.subscribe(ws1, [1])

        # client subscribed to bridge 2
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        await manager.connect(ws2)
        manager.subscribe(ws2, [2])

        # broadcast for bridge 1
        message = {"type": "bridge_status", "bridge_id": 1}
        await manager.broadcast(message, bridge_id=1)

        # only ws1 should receive
        assert ws1.send_json.called
        assert not ws2.send_json.called

    async def test_broadcast_bridge_status(self):
        """Manager can broadcast bridge status update"""
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await manager.connect(mock_ws)
        manager.subscribe(mock_ws, [1])

        await manager.broadcast_bridge_status(
            bridge_id=1,
            bridge_name="Test Bridge",
            status="UP",
            response_time=2500
        )

        # check message was sent
        assert mock_ws.send_json.called
        call_args = mock_ws.send_json.call_args[0][0]

        assert call_args['type'] == 'bridge_status'
        assert call_args['data']['bridge_id'] == 1
        assert call_args['data']['status'] == 'UP'

    async def test_broadcast_incident(self):
        """Manager can broadcast incident notification"""
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await manager.connect(mock_ws)

        await manager.broadcast_incident(
            bridge_id=1,
            bridge_name="Test Bridge",
            incident_type="created",
            severity="HIGH",
            title="Bridge is DOWN"
        )

        assert mock_ws.send_json.called
        call_args = mock_ws.send_json.call_args[0][0]

        assert call_args['type'] == 'incident'
        assert call_args['data']['severity'] == 'HIGH'

    async def test_handle_subscribe_action(self):
        """Client can send subscribe action"""
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        await manager.connect(mock_ws)
        mock_ws.send_json = AsyncMock()

        data = {
            "action": "subscribe",
            "bridge_ids": [1, 2, 3]
        }

        await manager.handle_client_message(mock_ws, data)

        # check subscription was set
        assert manager.subscriptions[mock_ws] == [1, 2, 3]

        # check confirmation was sent
        assert mock_ws.send_json.called

    async def test_handle_ping_action(self):
        """Client can send ping action"""
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await manager.connect(mock_ws)

        data = {"action": "ping"}
        await manager.handle_client_message(mock_ws, data)

        # should send pong
        assert mock_ws.send_json.called
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args['type'] == 'pong'

    async def test_failed_send_disconnects_client(self):
        """Failed send removes client from connections"""
        manager = ConnectionManager()
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=Exception("Connection lost"))

        await manager.connect(mock_ws)

        # try to send message (will fail)
        await manager.send_personal_message({"test": "fail"}, mock_ws)

        # client should be disconnected
        assert mock_ws not in manager.active_connections