"""
WebSocket endpoint for real-time bridge status updates
Clients connect and get live updates when bridge status changes
"""

import json
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from app.utils.logger import logger


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts updates

    Pretty straightforward - keeps track of who's connected
    and sends them updates when bridges change status
    """

    def __init__(self):
        # list of active WebSocket connections
        self.active_connections: List[WebSocket] = []

        # keep track of what each client is subscribed to
        # format: {websocket: [bridge_id1, bridge_id2, ...]}
        self.subscriptions: Dict[WebSocket, List[int]] = {}

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.subscriptions[websocket] = []  # starts with no subscriptions

        logger.info(
            f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove connection when client disconnects"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        if websocket in self.subscriptions:
            del self.subscriptions[websocket]

        logger.info(
            f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict, bridge_id: int = None):
        """
        Broadcast message to all connected clients

        If bridge_id is provided, only send to clients subscribed to that bridge
        Otherwise send to everyone
        """
        disconnected = []

        for connection in self.active_connections:
            # if bridge_id specified, check if client wants updates for this bridge
            if bridge_id is not None:
                subscribed_bridges = self.subscriptions.get(connection, [])
                # if they have subscriptions but this bridge isn't in them, skip
                if subscribed_bridges and bridge_id not in subscribed_bridges:
                    continue

            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to connection: {e}")
                disconnected.append(connection)

        # cleanup dead connections
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_bridge_status(
            self,
            bridge_id: int,
            bridge_name: str,
            status: str,
            response_time: int = None,
            extra_data: dict = None
    ):
        """
        Broadcast bridge status update to relevant clients

        This is the main method used by BridgeMonitor to send updates
        """
        message = {
            "type": "bridge_status",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "bridge_id": bridge_id,
                "bridge_name": bridge_name,
                "status": status,
                "response_time": response_time,
                "extra_data": extra_data or {}
            }
        }

        await self.broadcast(message, bridge_id=bridge_id)

        logger.debug(
            f"Broadcasted {bridge_name} status: {status} to {len(self.active_connections)} clients")

    async def broadcast_incident(
            self,
            bridge_id: int,
            bridge_name: str,
            incident_type: str,  # "created" or "resolved"
            severity: str,
            title: str
    ):
        """Broadcast incident creation/resolution"""
        message = {
            "type": "incident",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "bridge_id": bridge_id,
                "bridge_name": bridge_name,
                "incident_type": incident_type,
                "severity": severity,
                "title": title
            }
        }

        await self.broadcast(message, bridge_id=bridge_id)

    def subscribe(self, websocket: WebSocket, bridge_ids: List[int]):
        """
        Subscribe client to specific bridges
        If empty list, they get updates for all bridges
        """
        self.subscriptions[websocket] = bridge_ids
        logger.debug(f"Client subscribed to bridges: {bridge_ids}")

    async def handle_client_message(self, websocket: WebSocket, data: dict):
        """
        Handle incoming messages from clients

        Supported actions:
        - subscribe: {"action": "subscribe", "bridge_ids": [1, 2, 3]}
        - ping: {"action": "ping"}
        """
        action = data.get("action")

        if action == "subscribe":
            bridge_ids = data.get("bridge_ids", [])
            self.subscribe(websocket, bridge_ids)

            await self.send_personal_message({
                "type": "subscription_confirmed",
                "bridge_ids": bridge_ids
            }, websocket)

        elif action == "ping":
            # simple ping/pong for keepalive
            await self.send_personal_message({
                "type": "pong",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }, websocket)

        else:
            logger.warning(f"Unknown WebSocket action: {action}")


# global connection manager instance
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint at /ws

    Clients connect here and can:
    - Subscribe to specific bridges
    - Get real-time status updates
    - Receive incident notifications
    """
    await manager.connect(websocket)

    try:
        # send welcome message
        await manager.send_personal_message({
            "type": "connected",
            "message": "Connected to Bridge Status Bot WebSocket",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, websocket)

        # keep connection alive and handle incoming messages
        while True:
            # wait for client messages
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                await manager.handle_client_message(websocket, message)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {data}")
                await manager.send_personal_message({
                    "type": "error",
                    "message": "Invalid JSON format"
                }, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected normally")

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)