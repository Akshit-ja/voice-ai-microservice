# Voice AI Microservice - FastAPI Backend

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A production-ready microservice for handling voice call processing with AI transcription and sentiment analysis. Built for the Articence Voice & AI Team evaluation task.

## 📋 Table of Contents

- [Overview](#overview)
- [Methodology](#methodology)
- [Technical Architecture](#technical-architecture)
- [Features](#features)
- [Setup Instructions](#setup-instructions)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Technical Decisions](#technical-decisions)

## 🎯 Overview

This microservice handles thousands of concurrent voice calls in a PBX (Private Branch Exchange) system. When an agent is unavailable, calls are routed to an AI Voice-Bot, and this service:

1. **Ingests** audio metadata streams in real-time
2. **Orchestrates** background AI processing for transcription and sentiment analysis
3. **Stores** results for supervisor dashboard access
4. **Handles** unreliable external AI APIs with retry mechanisms
5. **Streams** real-time updates via WebSockets

## 🔬 Methodology

### Problem Analysis

The core challenge is building a **non-blocking**, **fault-tolerant** system that can:
- Accept audio packets with <50ms latency
- Validate packet ordering without blocking ingestion
- Process AI transcriptions asynchronously with retry logic
- Handle database race conditions gracefully
- Provide real-time visibility to supervisors

### Solution Approach

1. **Async-First Architecture**: Built entirely on `asyncio` and `async/await` patterns
2. **State Machine Pattern**: Enforced call lifecycle with validated state transitions
3. **Queue-Based Processing**: Decoupled ingestion from AI processing
4. **Exponential Backoff**: Resilient retry mechanism for flaky AI service
5. **Row-Level Locking**: Prevented race conditions in concurrent packet writes
6. **WebSocket Broadcasting**: Real-time updates without polling

## 🏗️ Technical Architecture

### System Components

```
┌─────────────────┐
│  Client/PBX     │
└────────┬────────┘
         │
         │ HTTP/WebSocket
         ▼
┌─────────────────────────────────────┐
│      FastAPI Application            │
│  ┌──────────────────────────────┐   │
│  │  POST /v1/call/stream/{id}   │   │ <50ms response
│  │  (Non-blocking ingestion)    │   │
│  └────────────┬─────────────────┘   │
│               │                      │
│               ▼                      │
│  ┌──────────────────────────────┐   │
│  │   PostgreSQL with Async      │   │
│  │   Row-level locking          │   │
│  └────────────┬─────────────────┘   │
│               │                      │
│               ▼                      │
│  ┌──────────────────────────────┐   │
│  │  Background AI Processor     │   │
│  │  (Queue + Retry Logic)       │   │
│  └────────────┬─────────────────┘   │
│               │                      │
│               ▼                      │
│  ┌──────────────────────────────┐   │
│  │  Mock AI Service             │   │
│  │  (25% failure, 1-3s latency) │   │
│  └──────────────────────────────┘   │
│                                     │
│  ┌──────────────────────────────┐   │
│  │  WebSocket Manager           │   │
│  │  (Real-time updates)         │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
```

### State Machine Flow

```
IN_PROGRESS ──► COMPLETED ──► PROCESSING_AI ──► ARCHIVED
    │                │               │
    ▼                ▼               ▼
  FAILED ◄────────FAILED ◄─────── FAILED
```

### Data Flow

1. **Packet Arrives** → Validate sequence → Insert with lock → Return 202 within 50ms
2. **Call Completed** → Transition state → Enqueue for AI processing
3. **Background Worker** → Dequeue → Retry with exponential backoff → Update state
4. **WebSocket** → Broadcast state changes to all connected clients

## ✨ Features

### ✅ Core Requirements

- [x] **Non-blocking ingestion** with <50ms response time
- [x] **Packet ordering validation** with missing packet warnings
- [x] **Async PostgreSQL** with SQLAlchemy 2.0+
- [x] **State machine** with enforced transitions
- [x] **Flaky AI service** simulation (25% failure rate, 1-3s latency)
- [x] **Exponential backoff retry** (up to 5 attempts)
- [x] **Race condition handling** with database locking
- [x] **Integration tests** including concurrent packet scenarios
- [x] **WebSocket support** for real-time updates

### 🚀 Additional Features

- [x] Comprehensive error handling and logging
- [x] Health check endpoint
- [x] Pagination for call listings
- [x] Docker and Docker Compose support
- [x] OpenAPI/Swagger documentation
- [x] CORS middleware
- [x] Graceful shutdown handling
- [x] WebSocket subscriptions per call

## 📦 Setup Instructions

### Prerequisites

- **Python 3.11+**
- **PostgreSQL 15+** (or Docker)
- **Git**

### Option 1: Docker Setup (Recommended)

The fastest way to get started:

```bash
# Clone the repository
git clone <repository-url>
cd voice-ai-microservice

# Copy environment file
cp .env.example .env

# Start all services (PostgreSQL + Application)
docker-compose up --build

# Application will be available at:
# - API: http://localhost:8000
# - Docs: http://localhost:8000/docs
# - WebSocket: ws://localhost:8000/v1/ws
```

### Option 2: Local Development Setup

For development with hot-reload:

```bash
# Clone the repository
git clone <repository-url>
cd voice-ai-microservice

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env

# Edit .env with your PostgreSQL credentials
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/voice_ai_db

# Start PostgreSQL (if not using Docker)
# Make sure PostgreSQL is running on port 5432

# Run database migrations (creates tables)
python -c "import asyncio; from app.database import init_db; asyncio.run(init_db())"

# Start the application
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Environment Variables

Key configuration options in `.env`:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/voice_ai_db

# AI Service Configuration
AI_SERVICE_FAILURE_RATE=0.25      # 25% failure rate
AI_SERVICE_MIN_LATENCY=1.0        # Minimum 1 second
AI_SERVICE_MAX_LATENCY=3.0        # Maximum 3 seconds

# Retry Configuration
MAX_RETRY_ATTEMPTS=5               # Maximum retry attempts
RETRY_MIN_WAIT=1                   # Minimum wait between retries (seconds)
RETRY_MAX_WAIT=60                  # Maximum wait between retries (seconds)
```

## 📚 API Documentation

### Interactive Documentation

Once the application is running, access interactive API docs:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Core Endpoints

#### 1. Ingest Audio Packet

```http
POST /v1/call/stream/{call_id}
Content-Type: application/json

{
  "sequence": 0,
  "data": "base64_encoded_audio_data",
  "timestamp": 1706745600.123
}
```

**Response** (202 Accepted):
```json
{
  "call_id": "call-12345",
  "sequence": 0,
  "status": "accepted",
  "message": "Packet 0 accepted",
  "received_at": "2026-02-01T10:30:00.123Z"
}
```

**Features**:
- ⚡ Responds within 50ms
- 🔒 Handles concurrent requests with database locking
- ⚠️ Logs warnings for missing packets
- ✅ Validates sequence ordering

#### 2. Complete Call

```http
POST /v1/call/{call_id}/complete
```

**Response** (200 OK):
```json
{
  "call_id": "call-12345",
  "state": "COMPLETED",
  "started_at": "2026-02-01T10:30:00Z",
  "completed_at": "2026-02-01T10:35:00Z",
  "total_packets": 150,
  "expected_sequence": 150,
  "transcription": null,
  "sentiment": null,
  "ai_processing_attempts": 0,
  "created_at": "2026-02-01T10:30:00Z",
  "updated_at": "2026-02-01T10:35:00Z"
}
```

#### 3. Get Call Details

```http
GET /v1/call/{call_id}
```

**Response** (200 OK):
```json
{
  "call_id": "call-12345",
  "state": "ARCHIVED",
  "total_packets": 150,
  "transcription": "Thank you for calling customer support...",
  "sentiment": "positive",
  "ai_processing_attempts": 2
}
```

#### 4. List Calls

```http
GET /v1/calls?state=COMPLETED&page=1&page_size=10
```

**Response** (200 OK):
```json
{
  "calls": [...],
  "total": 45,
  "page": 1,
  "page_size": 10
}
```

#### 5. WebSocket Real-Time Updates

```javascript
const ws = new WebSocket('ws://localhost:8000/v1/ws');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log(message);
  // {
  //   "event_type": "call_completed",
  //   "call_id": "call-12345",
  //   "data": {...},
  //   "timestamp": "2026-02-01T10:35:00Z"
  // }
};

// Subscribe to specific call
ws.send(JSON.stringify({
  "action": "subscribe",
  "call_id": "call-12345"
}));
```

**WebSocket Events**:
- `call_started` - New call created
- `packet_received` - Packet ingested
- `call_completed` - Call marked complete
- `call_processed` - AI processing successful
- `call_failed` - Processing failed after retries

#### 6. Health Check

```http
GET /health
```

**Response** (200 OK):
```json
{
  "status": "healthy",
  "timestamp": "2026-02-01T10:30:00Z",
  "version": "1.0.0",
  "dependencies": {
    "database": "connected",
    "ai_service": {
      "status": "operational",
      "failure_rate": 0.25
    }
  }
}
```

## 🧪 Testing

### Run All Tests

```bash
# Activate virtual environment first
pytest tests/ -v --asyncio-mode=auto

# With coverage
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/test_integration.py::TestRaceConditions -v
```

### Test Coverage

The test suite includes:

1. **Packet Ingestion Tests**
   - Sequential packet ordering
   - Missing packet detection
   - Duplicate packet handling
   - Response time validation

2. **Race Condition Tests**
   - Concurrent identical packets (database locking)
   - Concurrent different sequences
   - Multiple simultaneous calls

3. **State Machine Tests**
   - Valid state transitions
   - Invalid transition rejection
   - Call completion workflow

4. **AI Processing Tests**
   - Successful processing flow
   - Retry mechanism with failures
   - Exponential backoff verification

5. **Integration Tests**
   - End-to-end call lifecycle
   - WebSocket event broadcasting
   - Pagination and filtering

### Sample Test Output

```bash
tests/test_integration.py::TestPacketIngestion::test_create_new_call_with_first_packet PASSED
tests/test_integration.py::TestPacketIngestion::test_sequential_packet_ingestion PASSED
tests/test_integration.py::TestRaceConditions::test_concurrent_packet_arrival PASSED
tests/test_integration.py::TestRaceConditions::test_concurrent_different_sequences PASSED
tests/test_integration.py::TestCallStateManagement::test_complete_call_transition PASSED
tests/test_integration.py::TestAIProcessing::test_ai_processing_success PASSED

======================== 15 passed in 5.23s ========================
```

## 📂 Project Structure

```
voice-ai-microservice/
│
├── app/
│   ├── __init__.py              # Application package
│   ├── main.py                  # FastAPI application & endpoints
│   ├── config.py                # Configuration management
│   ├── database.py              # Database setup & session management
│   ├── models.py                # SQLAlchemy models & state machine
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── ai_service.py            # Mock AI service with failures
│   ├── background_tasks.py      # AI processor with retry logic
│   └── websocket.py             # WebSocket connection manager
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures
│   └── test_integration.py     # Integration tests
│
├── .env.example                 # Environment variable template
├── .gitignore                   # Git ignore rules
├── docker-compose.yml           # Docker Compose configuration
├── Dockerfile                   # Docker image definition
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

## 🎓 Technical Decisions

### 1. Why FastAPI?

- **Async Native**: Built-in support for `async/await`
- **Performance**: Among the fastest Python frameworks
- **Auto Documentation**: Swagger UI out of the box
- **Type Safety**: Pydantic validation
- **WebSocket Support**: First-class WebSocket implementation

### 2. Database Design Choices

**Row-Level Locking**:
```python
# Prevents race conditions on concurrent packet writes
result = await db.execute(
    select(Call)
    .where(Call.call_id == call_id)
    .with_for_update()  # 🔒 Row-level lock
)
```

**State Machine Enforcement**:
```python
# Prevents invalid transitions programmatically
def can_transition(from_state, to_state):
    valid_transitions = {
        IN_PROGRESS: [COMPLETED, FAILED],
        COMPLETED: [PROCESSING_AI, FAILED],
        ...
    }
    return to_state in valid_transitions[from_state]
```

**Composite Index for Performance**:
```python
Index('idx_call_sequence', 'call_id', 'sequence', unique=True)
# Ensures O(log n) lookups and prevents duplicate packets
```

### 3. Retry Strategy

Using **Tenacity** library for declarative retries:

```python
@retry(
    retry=retry_if_exception_type(AIServiceException),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)
async def process_call_with_retry(session, call_id):
    # Automatically retries with exponential backoff:
    # Attempt 1: Immediate
    # Attempt 2: Wait 1s
    # Attempt 3: Wait 2s
    # Attempt 4: Wait 4s
    # Attempt 5: Wait 8s
    ...
```

### 4. Queue-Based Processing

**Why not process AI synchronously?**

- **Non-blocking**: Ingestion returns immediately
- **Scalable**: Can add multiple worker processes
- **Resilient**: Failures don't block new calls
- **Prioritizable**: Can implement priority queues later

**Implementation**:
```python
# Enqueue (fast)
await ai_processor.enqueue_call(call_id)

# Background worker processes queue
while True:
    call_id = await queue.get()
    await process_with_retry(call_id)
```

### 5. WebSocket vs Polling

**Chosen WebSocket because**:
- **Real-time**: Zero latency updates
- **Efficient**: Single persistent connection
- **Scalable**: No repeated HTTP overhead
- **Bidirectional**: Clients can subscribe to specific calls

### 6. Mock AI Service Design

**Intentionally unreliable** to test resilience:

```python
async def transcribe_and_analyze(call_id, audio_data):
    # Simulate variable latency (1-3s)
    await asyncio.sleep(random.uniform(1.0, 3.0))
    
    # Simulate 25% failure rate
    if random.random() < 0.25:
        raise AIServiceException("503 Service Unavailable")
    
    return transcription_result
```

This forces the retry mechanism to be battle-tested.

### 7. Logging Strategy

**Structured logging** for production observability:

```python
logger.info(
    f"Packet {sequence} ingested for call {call_id} in {elapsed_ms:.2f}ms"
)
logger.warning(
    f"Missing packets for call {call_id}: expected={expected}, received={received}"
)
logger.error(
    f"Call {call_id} marked as FAILED after {attempts} attempts: {error}"
)
```

Enables:
- Performance monitoring (response times)
- Anomaly detection (missing packets)
- Debugging (failure traces)

## 🚀 Performance Considerations

### Response Time Optimization

- **Async I/O**: Non-blocking database operations
- **Connection Pooling**: Reuse database connections
- **Early Returns**: 202 Accepted before background processing
- **Index Optimization**: Query performance via composite indexes

### Scalability

**Horizontal Scaling**:
- Stateless API instances
- Shared PostgreSQL with connection pooling
- Background workers can run on separate instances

**Database Optimization**:
- Indexes on `(call_id, sequence)` and `(state, updated_at)`
- Row-level locking instead of table locks
- Async connection pool with 10 connections + 20 overflow

## 🔒 Security Considerations

Current implementation is for evaluation purposes. Production enhancements would include:

- **Authentication**: JWT tokens or API keys
- **Rate Limiting**: Prevent abuse
- **Input Sanitization**: SQL injection prevention (Pydantic helps)
- **TLS/SSL**: Encrypted connections
- **CORS Configuration**: Restrict origins in production

## 📈 Future Enhancements

- [ ] Kafka/RabbitMQ for distributed queue
- [ ] Redis caching for call metadata
- [ ] Prometheus metrics export
- [ ] Distributed tracing (OpenTelemetry)
- [ ] Call recording storage (S3/Azure Blob)
- [ ] Real AI service integration (OpenAI Whisper, Azure Speech)
- [ ] Authentication & authorization
- [ ] Rate limiting per client
- [ ] Advanced supervisor analytics dashboard

## 🤝 Contributing

This is an evaluation project, but feedback is welcome!

## 📄 License

MIT License - See LICENSE file

## 👤 Author

**Backend Developer Candidate**  
Articence Voice & AI Team Evaluation Task  
February 2026

---

## 📞 Support

For questions about this submission:
- Review the code comments
- Check the interactive API docs at `/docs`
- Run the test suite for examples

**Thank you for reviewing this submission!** 🙏
