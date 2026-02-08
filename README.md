# Leave Policy Assistant Agent

Tool-augmented agent that answers employee leave questions while enforcing company policy through deterministic business logic.

The LLM is used only for reasoning and conversation — policy decisions are executed by verified backend tools.

---

## Features

### Agent Capabilities

* Multi-turn conversations with memory
* Tool selection via reasoning (ReAct-style)
* Context aware follow-ups
* Graceful handling of missing or invalid data

### Tools Implemented

* `get_leave_policy(country, leave_type)`
* `check_leave_eligibility(employee_id, dates, leave_type)`
* `get_employee_leave_summary(employee_id)`

### Safety Controls

**Before model**

* prompt sanitization
* PII detection
* guardrail instruction injection

**After model**

* output validation
* PII redaction
* audit logging

### External Integration

* Snowflake client via Snowpark
* circuit breaker (CLOSED / OPEN / HALF_OPEN)
* mock fallback when unavailable

### Service Layer

* FastAPI REST interface
* session handling
* structured logging
* health endpoint

---

## Operational Guarantees

The system is designed to prevent unsafe or incorrect decisions:

- eligibility is never determined by the LLM
- all policy validation happens inside tools
- invalid or ambiguous requests are rejected, not guessed
- external dependency failures degrade to mock data instead of crashing
- unsafe prompts are blocked before reaching the model
- unsafe outputs are filtered after generation

The agent prioritizes correctness over helpfulness.

---

## Architecture Diagram
````
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT REQUEST                           │
│            POST /chat {"message": "...", ...}               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  FASTAPI REST API                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Endpoints:                                          │   │
│  │  - POST /chat                                        │   │
│  │  - GET /health                                       │   │
│  │  - GET /metrics                                      │   │
│  │  - POST /reset-conversation/{id}                     │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              SECURITY LAYER (Callbacks)                     │
│  ┌────────────────────────────────────────────────┐         │
│  │  BEFORE MODEL CALLBACK                         │         │
│  │  ├─ PII Detection (SSN, Email, Phone)          │         │
│  │  ├─ Malicious Prompt Filtering                 │         │
│  │  ├─ SQL Injection Prevention                   │         │
│  │  └─ Safety Instructions Injection              │         │
│  └────────────────────────────────────────────────┘         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  GOOGLE ADK AGENT                           │
│  ┌────────────────────────────────────────────────┐         │
│  │  Agent Components:                             │         │
│  │  ├─ LiteLLM (GPT-4 / Claude / Gemini)          │         │
│  │  ├─ ReAct Pattern (Reason → Act → Observe)     │         │
│  │  ├─ Tool Selection Logic                       │         │
│  │  └─ Conversation Memory (Session-based)        │         │
│  └────────────────────────────────────────────────┘         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    AGENT TOOLS                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. get_leave_policy(country, leave_type)            │   │
│  │     → Returns policy rules and allowances            │   │
│  │                                                      │   │
│  │  2. check_leave_eligibility(emp_id, dates, type)     │   │
│  │     → Validates: Balance, Notice, Blackouts          │   │
│  │                                                      │   │
│  │  3. get_employee_leave_summary(emp_id)               │   │
│  │     → Returns all balances and employee info         │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│          SNOWFLAKE CLIENT (Circuit Breaker Protected)       │
│  ┌────────────────────────────────────────────────┐         │
│  │  Circuit Breaker States:                       │         │
│  │  ┌──────────┐  5 failures  ┌──────────┐        │         │
│  │  │  CLOSED  │─────────────→│   OPEN    │       │         │
│  │  │ (Normal) │              │ (Blocking)│       │         │
│  │  └──────────┘              └──────────┘        │         │
│  │       ↑                         │              │         │
│  │       │ success            60s timeout         │         │
│  │       │                         ↓              │         │
│  │  ┌──────────┐              ┌──────────┐        │         │
│  │  │HALF_OPEN │←─────────────│  Testing  │       │         │
│  │  │(Testing) │              │           │       │         │
│  │  └──────────┘              └──────────┘        │         │
│  └────────────────────────────────────────────────┘         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              DATA SOURCES                                   │
│  ┌──────────────────────┬──────────────────────┐            │
│  │  Snowflake Database  │  Mock Data (Fallback)│            │
│  │  - employees table   │  - LEAVE_POLICIES    │            │
│  │  - leave_balances    │  - MOCK_EMPLOYEES    │            │
│  │  (Production)        │  (Development)       │            │
│  └──────────────────────┴──────────────────────┘            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              SECURITY LAYER (Callbacks)                     │
│  ┌────────────────────────────────────────────────┐         │
│  │  AFTER MODEL CALLBACK                          │         │
│  │  ├─ PII Redaction (SSN → XXX-XX-XXXX)          │         │
│  │  ├─ Email Masking (user@domain → ****@domain)  │         │
│  │  ├─ Audit Logging                              │         │
│  │  └─ Response Validation                        │         │
│  └────────────────────────────────────────────────┘         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT RESPONSE                          │
│     {"response": "...", "session_id": "..."}                │
└─────────────────────────────────────────────────────────────┘
````

---

## Architecture Overview

Client → FastAPI → ADK Agent → Tools → Snowflake / Mock Data

Execution flow:

1. request received
2. pre-model callback sanitizes input
3. LLM decides tool usage
4. tool executes business logic
5. post-model callback validates output
6. response returned

Failure paths:

* Snowflake failure → circuit breaker → mock data
* invalid request → handled gracefully
* unsafe response → filtered

**Important:**
The model cannot approve or deny leave directly.
It must call tools which implement business rules.
This prevents hallucinated policy decisions.

---

## Tech Stack

| Layer           | Technology         |
| --------------- | ------------------ |
| Agent Framework | Google ADK         |
| LLM Gateway     | LiteLLM            |
| API             | FastAPI            |
| Data            | Snowflake Snowpark |
| Observability   | OpenTelemetry      |
| Language        | Python 3.12        |
| Tests           | pytest             |

---

## Project Structure

```
leave-policy-agent/
│
├── pyproject.toml            # dependency source of truth
├── requirements.txt          # frozen deployment lock
├── Dockerfile
├── cloudbuild.yaml
├── .env.example
│
├── src/
│   ├── main.py               # FastAPI entrypoint
│   ├── agent.py              # ADK agent definition
│   ├── tools.py              # business tools
│   ├── callbacks.py          # guardrails
│   ├── snowflake_client.py   # data access
│   ├── circuit_breaker.py    # resilience logic
│   └── config.py             # settings
│
├── data/
│   └── leave_policies.py     # mock dataset
│
└── tests/
```

---

## Dependency Management Strategy

This project separates human-edited constraints from deployment locks.

| File             | Purpose                          |
| ---------------- | -------------------------------- |
| pyproject.toml   | editable dependency rules        |
| requirements.txt | exact resolved versions (Docker) |
| .venv            | local runtime                    |

After changing dependencies:

```
pip-compile pyproject.toml -o requirements.txt
```

---

## Quick Start

### 1) Clone

```
git clone <repo>
cd leave-policy-agent
```

### 2) Create environment

```
python -m venv .venv
source .venv/bin/activate
pip install -U pip
```

### 3) Install (developer mode)

```
pip install -e .[dev]
pre-commit install
```

### 4) Set env vars

```
cp .env.example .env
```

Edit .env and set at minimum (refer below section for more detail):

```
OPENAI_API_KEY=your_key_here
```


### 5) Run API

```
uvicorn src.main:app --reload --port 8080
```

Open:
[http://localhost:8080/docs](http://localhost:8080/docs)

---

## Environment Variables

Create `.env`:

```
OPENAI_API_KEY=
LITELLM_MODEL=gpt-4o-mini

SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_WAREHOUSE=
SNOWFLAKE_DATABASE=
SNOWFLAKE_SCHEMA=

ENVIRONMENT=development
LOG_LEVEL=INFO
```

Snowflake is optional — mock data is used if not configured.

---

## API Endpoints

### POST /chat

```
{
  "message": "Can I take 5 days leave next week?",
  "employee_id": "E001",
  "session_id": "abc"
}
```

Returns agent response with preserved conversation context.

---

### GET /health

Shows service status and circuit breaker state.

---

### POST /reset-conversation/{session_id}

Clears conversation history.

---

## Developer Workflow

Run service

```
uvicorn src.main:app --reload
```

Run tests

```
pytest
```

Coverage:

```
pytest --cov=src --cov-report=term-missing
```

Format & lint

```
ruff check . --fix
black .
```

Update dependency lock after changing pyproject.toml

```
pip-compile pyproject.toml -o requirements.txt
```

All checks run automatically on commit via pre-commit.

---

### Run all tests:
```bash
# Run tests with coverage
pytest --cov=src --cov-report=term-missing --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```
````

---

## Docker

Container installs only runtime dependencies from the frozen lockfile.

```
docker build -t leave-agent .
docker run -p 8080:8080 --env-file .env leave-agent
```

The container intentionally installs only runtime dependencies.
Developer tools are excluded to keep the image minimal and deterministic.

The container starts the service using:
```
uvicorn src.main:app --host 0.0.0.0 --port 8080
```
---

## Deployment (Cloud Run)

```
gcloud builds submit --config cloudbuild.yaml
```

Secrets should be stored in Google Secret Manager and injected at runtime.

---

## Known Limitations

- conversation memory is session-scoped (not persistent storage)
- mock data is used when Snowflake is unavailable
- date parsing assumes ISO or natural English dates

These tradeoffs keep the system deterministic for evaluation and local development.

---

## Example Conversations

**Policy**

> What is the PTO policy for India?

**Eligibility**

> Can I take 4 days casual leave tomorrow?

**Multi-turn**

> How many leaves do I have left?
> Ok book 2 next Monday

---

## Design Notes

Important implementation decisions:

* tools contain business rules, not prompts
* agent orchestrates, tools validate
* LLM never trusted for policy enforcement
* external systems wrapped in circuit breaker
* failures degrade gracefully instead of crashing

---

## License

[MIT License](LICENSE)

## Author

[**Sanskar Modi**](sanskarmodi8)
