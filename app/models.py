"""
Database models with state machine implementation.
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Enum as SQLEnum, Index, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
from app.database import Base


class CallState(str, Enum):
    """
    State machine for Call lifecycle.
    Transition flow: IN_PROGRESS -> COMPLETED -> PROCESSING_AI -> ARCHIVED
                     IN_PROGRESS -> FAILED
    """
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PROCESSING_AI = "PROCESSING_AI"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"
    
    @classmethod
    def can_transition(cls, from_state: "CallState", to_state: "CallState") -> bool:
        """
        Validate state transitions.
        
        Args:
            from_state: Current state
            to_state: Target state
            
        Returns:
            bool: True if transition is valid
        """
        valid_transitions = {
            cls.IN_PROGRESS: [cls.COMPLETED, cls.FAILED],
            cls.COMPLETED: [cls.PROCESSING_AI, cls.FAILED],
            cls.PROCESSING_AI: [cls.ARCHIVED, cls.FAILED],
            cls.FAILED: [cls.IN_PROGRESS],  # Allow retry
            cls.ARCHIVED: []  # Terminal state
        }
        return to_state in valid_transitions.get(from_state, [])


class Call(Base):
    """
    Call model representing a voice call session.
    
    Attributes:
        call_id: Unique call identifier
        state: Current call state (state machine)
        started_at: Call start timestamp
        completed_at: Call completion timestamp
        total_packets: Total number of packets received
        expected_sequence: Next expected packet sequence number
        transcription: AI-generated transcription
        sentiment: AI sentiment analysis result
        ai_processing_attempts: Number of AI processing attempts
        last_ai_attempt: Timestamp of last AI processing attempt
        created_at: Record creation timestamp
        updated_at: Record last update timestamp
    """
    __tablename__ = "calls"
    
    call_id = Column(String(100), primary_key=True, index=True)
    state = Column(
        SQLEnum(CallState),
        nullable=False,
        default=CallState.IN_PROGRESS,
        index=True
    )
    started_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    total_packets = Column(Integer, default=0, nullable=False)
    expected_sequence = Column(Integer, default=0, nullable=False)
    
    # AI Processing fields
    transcription = Column(Text, nullable=True)
    sentiment = Column(String(50), nullable=True)
    ai_processing_attempts = Column(Integer, default=0, nullable=False)
    last_ai_attempt = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    packets = relationship("CallPacket", back_populates="call", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_call_state_updated', 'state', 'updated_at'),
    )
    
    def transition_to(self, new_state: CallState) -> bool:
        """
        Transition call to a new state if valid.
        
        Args:
            new_state: Target state
            
        Returns:
            bool: True if transition successful
            
        Raises:
            ValueError: If transition is invalid
        """
        if not CallState.can_transition(self.state, new_state):
            raise ValueError(
                f"Invalid state transition from {self.state} to {new_state}"
            )
        self.state = new_state
        return True


class CallPacket(Base):
    """
    CallPacket model representing individual audio data packets.
    
    Attributes:
        id: Auto-incrementing primary key
        call_id: Foreign key to Call
        sequence: Packet sequence number
        data: Audio metadata/data
        timestamp: Packet timestamp
        received_at: Server receipt timestamp
    """
    __tablename__ = "call_packets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(
        String(100),
        ForeignKey("calls.call_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    sequence = Column(Integer, nullable=False)
    data = Column(Text, nullable=False)
    timestamp = Column(Float, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    
    # Relationships
    call = relationship("Call", back_populates="packets")
    
    # Indexes for query performance
    __table_args__ = (
        Index('idx_call_sequence', 'call_id', 'sequence', unique=True),
    )
