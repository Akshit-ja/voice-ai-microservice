"""
Background task processor with retry mechanism for AI processing.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models import Call, CallState, CallPacket
from app.ai_service import ai_service, AIServiceException
from app.config import settings
from app.websocket import connection_manager

logger = logging.getLogger(__name__)


class AIProcessor:
    """
    Background processor for AI transcription and sentiment analysis.
    Implements exponential backoff retry strategy for handling service failures.
    """
    
    def __init__(self):
        self.processing_queue = asyncio.Queue()
        self.is_running = False
        
    async def start(self):
        """Start the background processor."""
        if self.is_running:
            logger.warning("AI Processor already running")
            return
            
        self.is_running = True
        logger.info("AI Processor started")
        
        # Start background worker
        asyncio.create_task(self._process_queue())
    
    async def stop(self):
        """Stop the background processor."""
        self.is_running = False
        logger.info("AI Processor stopped")
    
    async def enqueue_call(self, call_id: str):
        """
        Add a call to the processing queue.
        
        Args:
            call_id: Call identifier to process
        """
        await self.processing_queue.put(call_id)
        logger.info(f"Call {call_id} enqueued for AI processing")
    
    async def _process_queue(self):
        """
        Continuously process calls from the queue.
        """
        from app.database import AsyncSessionLocal
        
        while self.is_running:
            try:
                # Get call from queue with timeout
                try:
                    call_id = await asyncio.wait_for(
                        self.processing_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process the call
                async with AsyncSessionLocal() as session:
                    try:
                        await self._process_call_with_retry(session, call_id)
                    except Exception as e:
                        logger.error(f"Failed to process call {call_id}: {e}")
                        # Update call state to FAILED
                        await self._mark_call_failed(session, call_id, str(e))
                
            except Exception as e:
                logger.error(f"Error in queue processor: {e}")
                await asyncio.sleep(1)
    
    @retry(
        retry=retry_if_exception_type(AIServiceException),
        stop=stop_after_attempt(settings.MAX_RETRY_ATTEMPTS),
        wait=wait_exponential(
            multiplier=1,
            min=settings.RETRY_MIN_WAIT,
            max=settings.RETRY_MAX_WAIT
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO)
    )
    async def _process_call_with_retry(
        self,
        session: AsyncSession,
        call_id: str
    ):
        """
        Process a call with exponential backoff retry.
        
        Args:
            session: Database session
            call_id: Call identifier
            
        Raises:
            AIServiceException: If AI service fails after all retries
        """
        # Fetch call with packets
        result = await session.execute(
            select(Call).where(Call.call_id == call_id)
        )
        call = result.scalar_one_or_none()
        
        if not call:
            logger.error(f"Call {call_id} not found")
            return
        
        # Update attempt count
        call.ai_processing_attempts += 1
        call.last_ai_attempt = datetime.utcnow()
        
        # Transition to PROCESSING_AI state
        if call.state == CallState.COMPLETED:
            call.transition_to(CallState.PROCESSING_AI)
        
        await session.commit()
        
        # Fetch all packets for this call
        packets_result = await session.execute(
            select(CallPacket)
            .where(CallPacket.call_id == call_id)
            .order_by(CallPacket.sequence)
        )
        packets = packets_result.scalars().all()
        
        # Concatenate audio data
        audio_data = " ".join(p.data for p in packets)
        
        logger.info(
            f"Processing call {call_id} (attempt {call.ai_processing_attempts})"
        )
        
        # Call AI service (may raise AIServiceException)
        result = await ai_service.transcribe_and_analyze(call_id, audio_data)
        
        # Update call with results
        call.transcription = result.transcription
        call.sentiment = result.sentiment
        call.transition_to(CallState.ARCHIVED)
        
        await session.commit()
        await session.refresh(call)
        
        logger.info(
            f"Successfully processed call {call_id} after "
            f"{call.ai_processing_attempts} attempts"
        )
        
        # Notify via WebSocket
        await connection_manager.broadcast({
            "event_type": "call_processed",
            "call_id": call_id,
            "data": {
                "state": call.state.value,
                "transcription": call.transcription,
                "sentiment": call.sentiment,
                "attempts": call.ai_processing_attempts
            }
        })
    
    async def _mark_call_failed(
        self,
        session: AsyncSession,
        call_id: str,
        error: str
    ):
        """
        Mark a call as failed after all retry attempts.
        
        Args:
            session: Database session
            call_id: Call identifier
            error: Error message
        """
        try:
            result = await session.execute(
                select(Call).where(Call.call_id == call_id)
            )
            call = result.scalar_one_or_none()
            
            if call:
                call.state = CallState.FAILED
                await session.commit()
                
                logger.error(
                    f"Call {call_id} marked as FAILED after "
                    f"{call.ai_processing_attempts} attempts: {error}"
                )
                
                # Notify via WebSocket
                await connection_manager.broadcast({
                    "event_type": "call_failed",
                    "call_id": call_id,
                    "data": {
                        "state": CallState.FAILED.value,
                        "error": error,
                        "attempts": call.ai_processing_attempts
                    }
                })
        except Exception as e:
            logger.error(f"Failed to mark call {call_id} as failed: {e}")


# Global processor instance
ai_processor = AIProcessor()
