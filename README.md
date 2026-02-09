# 🤖 Leave Policy Assistant Agent

> **Production-grade AI agent for employee leave management**  
> Built with Google ADK, deployed on Google Cloud Run

A tool-augmented conversational agent that helps employees understand leave policies, check balances, and verify eligibility—while enforcing company policy through deterministic business logic rather than LLM decisions.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Google ADK](https://img.shields.io/badge/Google-ADK-4285F4)](https://github.com/google/adk)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🚀 Live Demo

**Base URL:**
```
https://leave-policy-agent-641772618787.us-central1.run.app
```

**Try it now:**

```bash
# Check employee leave balance
curl -X POST https://leave-policy-agent-641772618787.us-central1.run.app/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is my leave balance?",
    "session_id": "demo_session",
    "employee_id": "E001"
  }'

# Get leave policy information
curl -X POST https://leave-policy-agent-641772618787.us-central1.run.app/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the US PTO policy?",
    "session_id": "demo_session_2",
    "employee_id": "E001"
  }'

# Check eligibility for leave request
curl -X POST https://leave-policy-agent-641772618787.us-central1.run.app/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Can I take 5 days PTO next week?",
    "session_id": "demo_session_3",
    "employee_id": "E001"
  }'
```

**Health & Monitoring:**

```bash
# Health check
curl https://leave-policy-agent-641772618787.us-central1.run.app/health

# Metrics
curl https://leave-policy-agent-641772618787.us-central1.run.app/metrics

# API documentation
open https://leave-policy-agent-641772618787.us-central1.run.app/docs
```

**Demo Employees:**
- `E001` - John Doe (US employee, Engineering)
- `E002` - Priya Sharma (India employee, Marketing)

---

## 📋 Table of Contents

- [Live Demo](#-live-demo)
- [Architecture Overview](#-architecture-overview)
- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [Quick Start](#-quick-start)
- [Cloud Deployment](#-cloud-deployment)
- [Design Philosophy](#-design-philosophy)
- [API Documentation](#-api-documentation)
- [Testing](#-testing)
- [Security](#-security)
- [Cost Characteristics](#-cost-characteristics)
- [Production Notes](#-production-notes)
- [Project Structure](#-project-structure)

---

## 🏗 Architecture Overview

### System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      CLIENT REQUEST                          │
│              POST /chat {"message": "...", ...}              │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    FASTAPI REST API                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Endpoints: /chat, /health, /metrics, /reset           │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│               SECURITY LAYER (Callbacks)                     │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  BEFORE MODEL: PII Detection, Prompt Sanitization      │  │
│  │  AFTER MODEL: PII Redaction, Audit Logging             │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    ROUTING LAYER                             │
│                  (Hybrid Architecture)                       │
└───────────────────────────┬──────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
                ▼                       ▼
    ┌──────────────────┐    ┌──────────────────┐
    │   FAST PATH      │    │  AGENTIC PATH    │
    │ (Deterministic)  │    │  (ADK Agent)     │
    │                  │    │                  │
    │ • Balance check  │    │ • Reasoning      │
    │ • Policy lookup  │    │ • Multi-turn     │
    │ • <100ms         │    │ • Eligibility    │
    │ • Zero LLM cost  │    │ • Explanations   │
    └──────────────────┘    └──────────────────┘
                │                       │
                └───────────┬───────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                      TOOL LAYER                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  • get_leave_policy(country, leave_type)               │  │
│  │  • check_leave_eligibility(emp_id, dates, type)        │  │
│  │  • get_employee_leave_summary(emp_id)                  │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│         SNOWFLAKE CLIENT (Circuit Breaker Protected)         │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Circuit States: CLOSED → OPEN → HALF_OPEN            │  │
│  │  Fallback: Mock data when Snowflake unavailable       │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                      DATA SOURCES                            │
│   • Snowflake Database (Production)                         │
│   • Mock Data (Development/Fallback)                        │
└──────────────────────────────────────────────────────────────┘
```

### Hybrid Architecture: Fast Path vs Agentic Path

This system implements a **two-path design** that balances reliability and intelligence:

#### 🚀 Fast Path (Deterministic)
**When:** Simple data lookups  
**How:** Direct tool execution, bypass LLM  
**Benefits:**
- ⚡ Sub-100ms latency
- 💰 Zero LLM cost
- ✅ 100% reliable responses
- 🎯 Predictable output

**Examples:**
- "What's my leave balance?"
- "What's the India PTO policy?"
- "Show my remaining leaves"

#### 🧠 Agentic Path (Reasoning)
**When:** Complex queries requiring reasoning  
**How:** Google ADK agent with ReAct pattern  
**Benefits:**
- 🤔 Handles edge cases intelligently
- 💬 Multi-turn context preservation
- 📊 Detailed eligibility explanations
- 🔄 Conversational follow-ups

**Examples:**
- "Can I take 5 days PTO during Christmas week?"
- "Am I eligible for parental leave?"
- "What happens if I exceed my leave balance?"

#### Why This Matters

Production AI systems must optimize for:
1. **Reliability** - Critical queries (balance, policy) must always work
2. **Cost** - Don't pay for LLM calls when deterministic logic suffices
3. **Latency** - Users expect instant responses for simple lookups
4. **Intelligence** - Complex scenarios benefit from LLM reasoning

This pattern is proven at scale by companies like **Intercom**, **Zendesk**, and **Stripe** for their customer support agents.

---

## ✨ Key Features

### Agent Capabilities
- ✅ **Multi-turn conversations** with session-based memory
- ✅ **Tool selection via reasoning** (ReAct pattern)
- ✅ **Context-aware follow-ups** within sessions
- ✅ **Graceful error handling** for missing/invalid data

### Tools Implemented
1. **get_leave_policy(country, leave_type)** - Retrieve official policy rules
2. **check_leave_eligibility(employee_id, dates, leave_type)** - Validate requests
3. **get_employee_leave_summary(employee_id)** - Get balance information

### Security Controls

**Before Model:**
- 🔒 Prompt sanitization
- 🔍 PII detection (SSN, email, phone)
- 🛡️ Malicious prompt filtering
- 📝 Safety instruction injection

**After Model:**
- 🔐 PII redaction in outputs
- 📊 Audit logging
- ✅ Response validation

### External Integrations
- **Snowflake Snowpark** - Secure data access via DataFrame API (prevents SQL injection)
- **Circuit Breaker Pattern** - Resilient error handling with automatic fallback
- **OpenTelemetry** - Distributed tracing for observability

### API Features
- **FastAPI** - High-performance REST endpoints
- **Session Management** - Conversation history with TTL-based cleanup
- **Health Checks** - `/health` endpoint with circuit breaker status
- **Metrics** - `/metrics` endpoint for monitoring

---

## 🛠 Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Agent Framework** | Google ADK | 1.24.0+ |
| **LLM Gateway** | LiteLLM | 1.81.9+ |
| **API Framework** | FastAPI | 0.128.4+ |
| **Data Warehouse** | Snowflake Snowpark | Latest |
| **Observability** | OpenTelemetry | 1.38.0+ |
| **Language** | Python | 3.12+ |
| **Testing** | pytest | 7.4.0+ |
| **Deployment** | Google Cloud Run | - |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Google Cloud account (for deployment)
- OpenAI API key (or other LLM provider)
- Snowflake account (optional - mock data available)

### Local Setup

#### 1. Clone Repository

```bash
git clone <repository-url>
cd leave-policy-agent
```

#### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install --upgrade pip
```

#### 3. Install Dependencies

```bash
# Development installation (includes testing tools)
pip install -e .[dev]

# Install pre-commit hooks
pre-commit install
```

#### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set required variables:

```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here
LITELLM_MODEL=gpt-4o-mini

# Optional - Snowflake (uses mock data if not provided)
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_WAREHOUSE=
SNOWFLAKE_DATABASE=
SNOWFLAKE_SCHEMA=

# Application
ENVIRONMENT=development
LOG_LEVEL=INFO
```

#### 5. Run Locally

```bash
uvicorn src.main:app --reload --port 8080
```

Open: [http://localhost:8080/docs](http://localhost:8080/docs)

### Test the Agent

```bash
# Example API call
curl -X POST "http://localhost:8080/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is my leave balance?",
    "session_id": "test_session_1",
    "employee_id": "E001"
  }'
```

**Expected Response:**
```json
{
  "response": "Here's your current leave balance:\n\n• PTO: 15 days\n• Sick Leave: 8 days",
  "session_id": "test_session_1"
}
```

---

## ☁️ Cloud Deployment

### First-Time Google Cloud Setup

#### 1. Prerequisites

```bash
# Install Google Cloud SDK
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com
```

#### 2. Create and Configure Secrets

```bash
# Create OpenAI API key secret
echo -n "your_openai_api_key" | gcloud secrets create openai-api-key --data-file=-

# Get your project number
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding openai-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

#### 3. Build and Push Container

```bash
# Build using Cloud Build
gcloud builds submit --config cloudbuild.yaml

# Or build locally and push
docker build -t gcr.io/$(gcloud config get-value project)/leave-policy-agent:latest .
docker push gcr.io/$(gcloud config get-value project)/leave-policy-agent:latest
```

#### 4. Deploy to Cloud Run

```bash
gcloud run deploy leave-policy-agent \
  --image gcr.io/$(gcloud config get-value project)/leave-policy-agent:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 5 \
  --set-env-vars=ENVIRONMENT=production,LOG_LEVEL=INFO \
  --update-secrets=OPENAI_API_KEY=openai-api-key:latest
```

#### 5. Get Service URL

```bash
gcloud run services describe leave-policy-agent \
  --region=us-central1 \
  --format='value(status.url)'
```

### Monitoring Deployment

```bash
# View logs
gcloud run services logs read leave-policy-agent --region=us-central1 --limit=50

# Check service status
gcloud run services describe leave-policy-agent --region=us-central1

# View metrics in Cloud Console
open "https://console.cloud.google.com/run/detail/us-central1/leave-policy-agent/metrics"
```

### Update Deployment

```bash
# Rebuild and redeploy
gcloud builds submit --config cloudbuild.yaml

# Or update specific settings
gcloud run services update leave-policy-agent \
  --region us-central1 \
  --memory 1Gi
```

---

## 💡 Design Philosophy

### Architectural Principles

#### 1. **LLM for Language, Backend for Decisions**

The language model generates natural language responses. The backend tools make all authoritative decisions.

**Anti-pattern:**
```python
# ❌ NEVER: Let LLM decide eligibility
response = llm("Can I take leave?")
if "yes" in response.lower():
    approve_leave()
```

**Correct pattern:**
```python
# ✅ ALWAYS: Backend tools decide, LLM explains
result = check_leave_eligibility(emp_id, dates, leave_type)
response = llm(f"Explain this result: {result}")
```

#### 2. **Deterministic When Possible, Intelligent When Necessary**

Not every query needs an LLM. Use the right tool for the job.

| Query Type | Approach | Reason |
|-----------|----------|--------|
| "What's my balance?" | Direct DB lookup | Factual, no reasoning needed |
| "Can I take leave during blackout?" | Agent reasoning | Needs policy interpretation |

#### 3. **Defense in Depth**

Security is layered, not single-point:
1. Input validation (before LLM)
2. Tool validation (during execution)
3. Output filtering (after LLM)
4. Session binding (prevents cross-employee access)

#### 4. **Graceful Degradation**

External dependencies fail. The system adapts:
- Snowflake down → Circuit breaker → Mock data
- LLM quota exceeded → Fast path still works
- Invalid input → Helpful error message, not crash

---

## 📚 API Documentation

### Endpoints

#### `POST /chat`

Send a message to the leave assistant.

**Request:**
```json
{
  "message": "Can I take 5 days PTO next week?",
  "session_id": "user123_session1",
  "employee_id": "E001"
}
```

**Response:**
```json
{
  "response": "Let me check your eligibility...",
  "session_id": "user123_session1"
}
```

#### `GET /health`

Check service health and dependencies.

**Response:**
```json
{
  "status": "healthy",
  "environment": "production",
  "snowflake_circuit_breaker": {
    "state": "closed",
    "failure_count": 0
  }
}
```

#### `GET /metrics`

Prometheus-compatible metrics.

**Response:**
```json
{
  "circuit_breaker": {...},
  "active_conversations": 15,
  "environment": "production"
}
```

#### `POST /reset-conversation/{session_id}`

Clear conversation history for a session.

**Response:**
```json
{
  "message": "Conversation reset for session abc123",
  "session_id": "abc123"
}
```

---

## 🧪 Testing

### Run All Tests

```bash
# Run tests with coverage
pytest --cov=src --cov-report=term-missing --cov-report=html

# View HTML coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Test Categories

#### Unit Tests
```bash
pytest tests/test_tools.py -v
pytest tests/test_callbacks.py -v
pytest tests/test_circuit_breaker.py -v
```

#### Integration Tests
```bash
pytest tests/test_api.py -v
```

#### Security Tests
```bash
pytest tests/test_security_attacks.py -v
```

#### Hybrid Architecture Tests
```bash
pytest tests/test_hybrid_architecture.py -v
```

### Coverage Goals

- **Target:** 90%+ overall coverage
- **Critical paths:** 95%+ (tools, callbacks, security)

### Example Test Scenarios

The agent handles these conversation flows:

**Scenario 1: Simple Balance Check**
```
User: "What's my leave balance?"
Agent: "Here's your current leave balance:
        • PTO: 15 days
        • Sick Leave: 8 days"
```

**Scenario 2: Eligibility Validation**
```
User: "Can I take 5 days PTO next week?"
Agent: "Yes, you're eligible! You have 15 days available..."
```

**Scenario 3: Multi-turn Conversation**
```
User: "What's the India leave policy?"
Agent: "Here are the policies for India employees..."
User: "How many privilege leave days do I have?"
Agent: "You have 12 days of Privilege Leave remaining."
```

---

## 🔒 Security

### Threat Model

We defend against:

| Attack Vector | Mitigation |
|--------------|------------|
| Prompt injection | Input sanitization + output validation |
| Cross-employee data access | Session binding + tool validation |
| PII leakage | PII detection + redaction |
| SQL injection | Snowpark DataFrame API (parameterized) |
| DoS via memory exhaustion | Session TTL + bounded history |
| Circuit breaker bypass | Hard failure thresholds |

### Security Testing

Run adversarial tests:
```bash
pytest tests/test_security_attacks.py -v
```

Validated attack scenarios:
- ❌ Cross-employee data retrieval
- ❌ Tool bypass attempts
- ❌ Prompt injection
- ❌ Identity impersonation

### Compliance

- **PII Handling:** Automatic detection and redaction
- **Audit Trail:** All requests logged with session_id
- **Data Isolation:** Employee data never crosses session boundaries
- **Secure Defaults:** Fail closed, not open

---

## 💰 Cost Characteristics

### Cost Optimization via Hybrid Architecture

| Query Type | Path | LLM Calls | Cost per Request |
|-----------|------|-----------|------------------|
| Balance check | Fast | 0 | $0.00 |
| Policy lookup | Fast | 0 | $0.00 |
| Eligibility check | Agentic | ~1 | ~$0.001 |
| Complex reasoning | Agentic | ~1-2 | ~$0.002 |

**Estimated Monthly Cost (1000 users, 10 queries/user/month):**

- 70% fast path queries → 7,000 queries × $0 = **$0**
- 30% agentic queries → 3,000 queries × $0.001 = **$3**

**Total:** ~$3/month for 10,000 queries

**Cloud Run Costs:**
- First 2M requests/month: Free tier
- CPU/Memory: ~$0.10/day with default settings

**Total Infrastructure:** ~$5-10/month for small-medium workloads

---

## 📊 Production Notes

### Session Memory Architecture

**Current Implementation:**
- Sessions stored in-memory using `InMemoryRunner`
- TTL-based cleanup (30 minutes default)
- Maximum 1000 concurrent sessions

**Production Considerations:**

⚠️ **Stateless Deployment:** Cloud Run instances are ephemeral. Conversations may reset during:
- Cold starts (first request after idle period)
- Auto-scaling events (traffic spikes)
- Deployments (rolling updates)

**Mitigation Strategies:**

1. **Session Stickiness** (Current):
   - Best-effort preservation within instance lifetime
   - Suitable for short conversations (<30 min)

2. **External State (Planned)**:
   - Firestore for persistent sessions
   - Redis for distributed caching
   - Allows cross-instance conversation continuity

**When to Add Persistence:**
- Multi-day conversations required
- Cross-device session continuity needed
- >1000 concurrent users expected

### Scaling Characteristics

**Current Settings:**
- Min instances: 0 (scales to zero)
- Max instances: 5
- Memory: 512Mi
- CPU: 1

**Performance:**
- Cold start: ~3-5 seconds
- Warm response (fast path): <100ms
- Warm response (agentic): 1-3 seconds

**Scaling Strategy:**
- Horizontal scaling for concurrent users
- Vertical scaling (memory/CPU) for complex queries

### Monitoring & Observability

**Built-in:**
- Structured JSON logging
- OpenTelemetry tracing
- Circuit breaker state tracking
- Request/response metrics

**Cloud Run Integration:**
- Automatic logging to Cloud Logging
- Metrics in Cloud Monitoring
- Request traces in Cloud Trace

**Alerts (Recommended):**
```bash
# High error rate
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="High Error Rate" \
  --condition-threshold-value=0.05 \
  --condition-threshold-duration=60s

# Circuit breaker open
# Monitor /metrics endpoint for circuit_breaker.state != "closed"
```

---

## 📁 Project Structure

```
leave-policy-agent/
│
├── README.md                 # This file
├── pyproject.toml            # Dependency source of truth
├── requirements.txt          # Frozen deployment lock
├── Dockerfile                # Container definition
├── cloudbuild.yaml           # CI/CD pipeline
├── .env.example              # Environment template
├── .pre-commit-config.yaml   # Code quality hooks
│
├── src/
│   ├── __init__.py
│   ├── main.py               # FastAPI entrypoint
│   ├── agent.py              # ADK agent + hybrid routing
│   ├── tools.py              # Business logic tools
│   ├── callbacks.py          # Security callbacks
│   ├── snowflake_client.py   # Data access layer
│   ├── circuit_breaker.py    # Resilience pattern
│   ├── config.py             # Settings management
│   ├── conversation_state.py # Request state tracking
│   ├── observability.py      # Tracing utilities
│   └── utils/
│       └── request_context.py # Thread-local context
│
├── data/
│   └── leave_policies.py     # Mock data + policy definitions
│
└── tests/
    ├── conftest.py           # Test fixtures
    ├── test_agent.py         # Agent behavior
    ├── test_tools.py         # Tool validation
    ├── test_api.py           # REST API endpoints
    ├── test_callbacks.py     # Security callbacks
    ├── test_circuit_breaker.py # Resilience
    ├── test_security_attacks.py # Adversarial tests
    └── test_hybrid_architecture.py # Fast path vs agentic path
```

---

## 🤝 Contributing

### Development Workflow

1. **Create branch:** `git checkout -b feature/my-feature`
2. **Make changes:** Edit code
3. **Run tests:** `pytest`
4. **Format code:** `ruff check . --fix && black .`
5. **Commit:** `git commit -m "feat: add feature"`
6. **Push:** `git push origin feature/my-feature`

Pre-commit hooks automatically run:
- Ruff (linting)
- Black (formatting)
- Tests (validation)

### Code Quality Standards

- **Test Coverage:** >90% required
- **Type Hints:** All function signatures
- **Docstrings:** All public functions
- **Naming:** Descriptive, not abbreviated
- **Comments:** Explain "why", not "what"

---

## 🎯 Future Enhancements

### Planned Features
- [ ] Firestore session persistence (cross-instance memory)
- [ ] Prometheus metrics exporter
- [ ] Retry with exponential backoff
- [ ] Multi-language support (i18n)
- [ ] Slack bot integration
- [ ] Email notification system
- [ ] Admin dashboard for HR

### Performance Optimizations
- [ ] Redis caching for policy data
- [ ] Request batching for bulk queries
- [ ] Async tool execution (parallel calls)
- [ ] Response streaming (SSE)

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

**Sanskar Modi**

- GitHub: [@sanskarmodi8](https://github.com/sanskarmodi8)