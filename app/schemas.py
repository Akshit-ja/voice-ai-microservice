"""
Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, List
from app.models import CallState


class PacketInput(BaseModel):
    """Schema for incoming audio packet data."""
    sequence: int = Field(..., ge=0, description="Packet sequence number")
    data: str = Field(..., min_length=1, description="Audio metadata/data")
    timestamp: float = Field(..., gt=0, description="Packet timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "sequence": 0,
                "data": "base64_encoded_audio_data",
                "timestamp": 1706745600.123
            }
        }


class PacketResponse(BaseModel):
    """Schema for packet ingestion response."""
    call_id: str
    sequence: int
    status: str
    message: str
    received_at: datetime
    
    class Config:
        from_attributes = True


class CallResponse(BaseModel):
    """Schema for call information response."""
    call_id: str
    state: CallState
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_packets: int
    expected_sequence: int
    transcription: Optional[str] = None
    sentiment: Optional[str] = None
    ai_processing_attempts: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CallListResponse(BaseModel):
    """Schema for list of calls."""
    calls: List[CallResponse]
    total: int
    page: int
    page_size: int


class AITranscriptionResult(BaseModel):
    """Schema for AI transcription result."""
    transcription: str
    sentiment: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    processing_time: float


class ErrorResponse(BaseModel):
    """Schema for error responses."""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WebSocketMessage(BaseModel):
    """Schema for WebSocket messages."""
    event_type: str
    call_id: str
    data: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)
