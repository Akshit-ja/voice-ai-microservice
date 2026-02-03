"""
Mock AI Service with configurable failure rate and latency.
This simulates an unreliable external AI API for transcription and sentiment analysis.
"""
import asyncio
import random
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from app.config import settings
from app.schemas import AITranscriptionResult

logger = logging.getLogger(__name__)


class AIServiceException(Exception):
    """Custom exception for AI service failures."""
    pass


class MockAIService:
    """
    Mock AI Transcription and Sentiment Analysis Service.
    
    This service intentionally simulates real-world API unreliability:
    - 25% failure rate (503 Service Unavailable)
    - Variable latency between 1-3 seconds
    """
    
    def __init__(
        self,
        failure_rate: float = None,
        min_latency: float = None,
        max_latency: float = None
    ):
        """
        Initialize the mock AI service.
        
        Args:
            failure_rate: Probability of service failure (0.0 to 1.0)
            min_latency: Minimum response latency in seconds
            max_latency: Maximum response latency in seconds
        """
        self.failure_rate = failure_rate or settings.AI_SERVICE_FAILURE_RATE
        self.min_latency = min_latency or settings.AI_SERVICE_MIN_LATENCY
        self.max_latency = max_latency or settings.AI_SERVICE_MAX_LATENCY
        
        # Sample transcriptions for simulation
        self.sample_transcriptions = [
            "Thank you for calling customer support. How can I help you today?",
            "I understand your concern about the billing issue. Let me check that for you.",
            "Your account has been successfully updated. Is there anything else I can assist with?",
            "I apologize for the inconvenience. Let me transfer you to a specialist.",
            "Your order has been confirmed and will be delivered within 3-5 business days.",
        ]
        
        # Sample sentiments
        self.sample_sentiments = ["positive", "neutral", "negative", "mixed"]
        
        logger.info(
            f"MockAIService initialized: failure_rate={self.failure_rate}, "
            f"latency={self.min_latency}-{self.max_latency}s"
        )
    
    async def transcribe_and_analyze(
        self,
        call_id: str,
        audio_data: str
    ) -> AITranscriptionResult:
        """
        Simulate AI transcription and sentiment analysis.
        
        Args:
            call_id: Unique call identifier
            audio_data: Concatenated audio packet data
            
        Returns:
            AITranscriptionResult: Transcription and sentiment analysis
            
        Raises:
            AIServiceException: If the service fails (503)
        """
        start_time = datetime.utcnow()
        
        # Simulate variable latency
        latency = random.uniform(self.min_latency, self.max_latency)
        await asyncio.sleep(latency)
        
        # Simulate service failure
        if random.random() < self.failure_rate:
            logger.warning(
                f"AI Service failure (503) for call_id={call_id} after {latency:.2f}s"
            )
            raise AIServiceException("503 Service Unavailable: AI Service temporarily down")
        
        # Generate mock transcription and sentiment
        transcription = random.choice(self.sample_transcriptions)
        sentiment = random.choice(self.sample_sentiments)
        confidence = random.uniform(0.75, 0.99)
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(
            f"AI Service success for call_id={call_id}: "
            f"sentiment={sentiment}, confidence={confidence:.2f}, time={processing_time:.2f}s"
        )
        
        return AITranscriptionResult(
            transcription=transcription,
            sentiment=sentiment,
            confidence=confidence,
            processing_time=processing_time
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check service health status.
        
        Returns:
            dict: Health status information
        """
        return {
            "status": "operational",
            "failure_rate": self.failure_rate,
            "latency_range": f"{self.min_latency}-{self.max_latency}s"
        }


# Global service instance
ai_service = MockAIService()
