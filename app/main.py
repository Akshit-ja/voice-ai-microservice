"""
Main FastAPI application with call ingestion and management endpoints.
"""
import time
import logging
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    status,
    WebSocket,
    WebSocketDisconnect,
    Query
)
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import get_db, init_db, close_db
from app.models import Call, CallPacket, CallState
from app.schemas import (
    PacketInput,
    PacketResponse,
    CallResponse,
    CallListResponse,
    ErrorResponse
)
from app.background_tasks import ai_processor
from app.websocket import connection_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.
    """
    # Startup
    logger.info("Starting Voice AI Microservice...")
    await init_db()
    await ai_processor.start()
    logger.info("Application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Voice AI Microservice...")
    await ai_processor.stop()
    await close_db()
    logger.info("Application shut down successfully")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Microservice for handling voice call processing with AI transcription and sentiment analysis",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post(
    f"{settings.API_V1_PREFIX}/call/stream/{{call_id}}",
    response_model=PacketResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Packet accepted for processing"},
        400: {"model": ErrorResponse, "description": "Invalid packet data"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Ingest audio packet stream",
    description="""
    Non-blocking endpoint for ingesting audio packet metadata.
    
    **Requirements:**
    - Packets must arrive in sequential order
    - Missing packets are logged as warnings
    - Returns 202 Accepted within <50ms
    - Validates packet sequence numbers
    
    **State Machine:**
    - Creates new call in IN_PROGRESS state if doesn't exist
    - Tracks expected sequence numbers
    - Handles concurrent packet arrivals with database locking
    """
)
async def stream_audio_packet(
    call_id: str,
    packet: PacketInput,
    db: AsyncSession = Depends(get_db)
) -> PacketResponse:
    """
    Ingest an audio packet for a call.
    
    This endpoint must respond within 50ms to meet real-time requirements.
    It validates packet ordering and logs warnings for missing packets.
    
    Args:
        call_id: Unique call identifier
        packet: Audio packet metadata
        db: Database session
        
    Returns:
        PacketResponse: Acknowledgment with packet details
        
    Raises:
        HTTPException: If packet validation fails
    """
    start_time = time.time()
    
    try:
        # Get or create call with row-level locking to prevent race conditions
        result = await db.execute(
            select(Call)
            .where(Call.call_id == call_id)
            .with_for_update()
        )
        call = result.scalar_one_or_none()
        
        if not call:
            # Create new call
            call = Call(
                call_id=call_id,
                state=CallState.IN_PROGRESS,
                started_at=datetime.utcnow(),
                expected_sequence=0
            )
            db.add(call)
            await db.flush()
            
            logger.info(f"Created new call: {call_id}")
            
            # Notify via WebSocket
            await connection_manager.broadcast({
                "event_type": "call_started",
                "call_id": call_id,
                "data": {"state": CallState.IN_PROGRESS.value}
            })
        
        # Validate packet sequence
        if packet.sequence < call.expected_sequence:
            logger.warning(
                f"Duplicate packet for call {call_id}: "
                f"received={packet.sequence}, expected={call.expected_sequence}"
            )
            return PacketResponse(
                call_id=call_id,
                sequence=packet.sequence,
                status="duplicate",
                message=f"Packet {packet.sequence} already received",
                received_at=datetime.utcnow()
            )
        
        if packet.sequence > call.expected_sequence:
            logger.warning(
                f"Missing packets for call {call_id}: "
                f"expected={call.expected_sequence}, received={packet.sequence}, "
                f"missing={packet.sequence - call.expected_sequence} packets"
            )
        
        # Insert packet (may raise IntegrityError on race condition)
        try:
            call_packet = CallPacket(
                call_id=call_id,
                sequence=packet.sequence,
                data=packet.data,
                timestamp=packet.timestamp,
                received_at=datetime.utcnow()
            )
            db.add(call_packet)
            
            # Update call metadata
            call.total_packets += 1
            call.expected_sequence = packet.sequence + 1
            
            await db.commit()
            
            # Notify via WebSocket
            await connection_manager.broadcast_to_call(call_id, {
                "event_type": "packet_received",
                "call_id": call_id,
                "data": {
                    "sequence": packet.sequence,
                    "total_packets": call.total_packets
                }
            })
            
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Packet {packet.sequence} ingested for call {call_id} "
                f"in {elapsed_ms:.2f}ms"
            )
            
            return PacketResponse(
                call_id=call_id,
                sequence=packet.sequence,
                status="accepted",
                message=f"Packet {packet.sequence} accepted",
                received_at=call_packet.received_at
            )
            
        except IntegrityError:
            await db.rollback()
            logger.warning(
                f"Race condition: Duplicate packet {packet.sequence} for call {call_id}"
            )
            return PacketResponse(
                call_id=call_id,
                sequence=packet.sequence,
                status="duplicate",
                message=f"Packet {packet.sequence} already processed by concurrent request",
                received_at=datetime.utcnow()
            )
    
    except Exception as e:
        await db.rollback()
        logger.error(f"Error ingesting packet for call {call_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest packet: {str(e)}"
        )


@app.post(
    f"{settings.API_V1_PREFIX}/call/{{call_id}}/complete",
    response_model=CallResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark call as completed",
    description="Transition call to COMPLETED state and trigger AI processing"
)
async def complete_call(
    call_id: str,
    db: AsyncSession = Depends(get_db)
) -> CallResponse:
    """
    Mark a call as completed and enqueue for AI processing.
    
    Args:
        call_id: Unique call identifier
        db: Database session
        
    Returns:
        CallResponse: Updated call information
        
    Raises:
        HTTPException: If call not found or state transition invalid
    """
    try:
        result = await db.execute(
            select(Call).where(Call.call_id == call_id)
        )
        call = result.scalar_one_or_none()
        
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Call {call_id} not found"
            )
        
        # Transition to COMPLETED
        try:
            call.transition_to(CallState.COMPLETED)
            call.completed_at = datetime.utcnow()
            await db.commit()
            await db.refresh(call)
            
            logger.info(f"Call {call_id} marked as COMPLETED")
            
            # Enqueue for AI processing
            await ai_processor.enqueue_call(call_id)
            
            # Notify via WebSocket
            await connection_manager.broadcast({
                "event_type": "call_completed",
                "call_id": call_id,
                "data": {
                    "state": CallState.COMPLETED.value,
                    "total_packets": call.total_packets
                }
            })
            
            return CallResponse.model_validate(call)
            
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error completing call {call_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete call: {str(e)}"
        )


@app.get(
    f"{settings.API_V1_PREFIX}/call/{{call_id}}",
    response_model=CallResponse,
    summary="Get call information",
    description="Retrieve detailed information about a specific call"
)
async def get_call(
    call_id: str,
    db: AsyncSession = Depends(get_db)
) -> CallResponse:
    """
    Get call details by ID.
    
    Args:
        call_id: Unique call identifier
        db: Database session
        
    Returns:
        CallResponse: Call information
        
    Raises:
        HTTPException: If call not found
    """
    result = await db.execute(
        select(Call).where(Call.call_id == call_id)
    )
    call = result.scalar_one_or_none()
    
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call {call_id} not found"
        )
    
    return CallResponse.model_validate(call)


@app.get(
    f"{settings.API_V1_PREFIX}/calls",
    response_model=CallListResponse,
    summary="List all calls",
    description="Retrieve a paginated list of all calls with optional state filtering"
)
async def list_calls(
    state: Optional[CallState] = Query(None, description="Filter by call state"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
) -> CallListResponse:
    """
    List calls with pagination and filtering.
    
    Args:
        state: Optional state filter
        page: Page number (1-indexed)
        page_size: Number of items per page
        db: Database session
        
    Returns:
        CallListResponse: Paginated list of calls
    """
    # Build query
    query = select(Call)
    if state:
        query = query.where(Call.state == state)
    
    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()
    
    # Get paginated results
    query = query.order_by(Call.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    calls = result.scalars().all()
    
    return CallListResponse(
        calls=[CallResponse.model_validate(call) for call in calls],
        total=total,
        page=page,
        page_size=page_size
    )


@app.websocket(f"{settings.API_V1_PREFIX}/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time call updates.
    
    Clients can connect to receive real-time updates about:
    - New calls starting
    - Packets being received
    - Calls completing
    - AI processing results
    - Call failures
    
    Args:
        websocket: WebSocket connection
    """
    await connection_manager.connect(websocket)
    
    try:
        while True:
            # Receive messages from client (for subscriptions)
            data = await websocket.receive_json()
            
            if data.get("action") == "subscribe" and "call_id" in data:
                call_id = data["call_id"]
                await connection_manager.subscribe_to_call(websocket, call_id)
                await connection_manager.send_personal_message(
                    {
                        "event_type": "subscribed",
                        "call_id": call_id,
                        "message": f"Subscribed to updates for call {call_id}"
                    },
                    websocket
                )
    
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        connection_manager.disconnect(websocket)


@app.get(
    "/health",
    summary="Health check",
    description="Check service health and dependencies"
)
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        dict: Service health status
    """
    from app.ai_service import ai_service
    
    ai_health = await ai_service.health_check()
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.APP_VERSION,
        "dependencies": {
            "database": "connected",
            "ai_service": ai_health
        }
    }


@app.get(
    "/",
    summary="Root endpoint",
    description="API information"
)
async def root():
    """
    Root endpoint with API information.
    
    Returns:
        dict: API details
    """
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "websocket": f"{settings.API_V1_PREFIX}/ws"
    }
