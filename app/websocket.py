"""
WebSocket connection manager for real-time updates to supervisor dashboard.
"""
import logging
import json
from typing import Dict, Set
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time call updates.
    Broadcasts call state changes and AI processing results to all connected clients.
    """
    
    def __init__(self):
        """Initialize the connection manager."""
        self.active_connections: Set[WebSocket] = set()
        self.call_subscriptions: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket):
        """
        Accept and register a new WebSocket connection.
        
        Args:
            websocket: WebSocket connection to register
        """
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection.
        
        Args:
            websocket: WebSocket connection to remove
        """
        self.active_connections.discard(websocket)
        
        # Remove from call subscriptions
        for call_id, subscribers in list(self.call_subscriptions.items()):
            subscribers.discard(websocket)
            if not subscribers:
                del self.call_subscriptions[call_id]
        
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def subscribe_to_call(self, websocket: WebSocket, call_id: str):
        """
        Subscribe a WebSocket to updates for a specific call.
        
        Args:
            websocket: WebSocket connection
            call_id: Call identifier to subscribe to
        """
        if call_id not in self.call_subscriptions:
            self.call_subscriptions[call_id] = set()
        
        self.call_subscriptions[call_id].add(websocket)
        logger.info(f"WebSocket subscribed to call {call_id}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """
        Send a message to a specific WebSocket connection.
        
        Args:
            message: Message dictionary to send
            websocket: Target WebSocket connection
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: dict):
        """
        Broadcast a message to all connected WebSocket clients.
        
        Args:
            message: Message dictionary to broadcast
        """
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat()
        
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
        
        if self.active_connections:
            logger.info(
                f"Broadcasted {message.get('event_type', 'unknown')} event "
                f"to {len(self.active_connections)} connections"
            )
    
    async def broadcast_to_call(self, call_id: str, message: dict):
        """
        Broadcast a message to all clients subscribed to a specific call.
        
        Args:
            call_id: Call identifier
            message: Message dictionary to send
        """
        if call_id not in self.call_subscriptions:
            return
        
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat()
        
        disconnected = set()
        subscribers = self.call_subscriptions[call_id]
        
        for connection in subscribers:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to subscriber: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
        
        if subscribers:
            logger.info(
                f"Sent {message.get('event_type', 'unknown')} event for call {call_id} "
                f"to {len(subscribers)} subscribers"
            )


# Global connection manager instance
connection_manager = ConnectionManager()
