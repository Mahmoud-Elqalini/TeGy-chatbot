# TeGy-Chatbot Backend Audit Report

## 1. Project Structure
The project follows a standard, modular FastAPI architecture with distinct layers for API, core configuration, database, models, repositories, and services.

- `app/ai/`: AI logic, orchestrators, prompt builders, intent routing, tools, and provider integrations.
- `app/api/`: FastAPI route definitions and dependencies.
- `app/core/`: Application-wide configurations, security, exceptions, and middleware.
- `app/db/`: Database connection setups, Redis setup, and raw SQL schemas/migrations.
- `app/infrastructure/`: Low-level adapters for caching, locking, and tokens.
- `app/models/`: SQLAlchemy ORM models, separated into `chatbot` and `main`.
- `app/repositories/`: Database abstraction layer handling CRUD operations.
- `app/schemas/`: Pydantic models for data validation, serialization, and API schemas.
- `app/services/`: Core business logic connecting APIs, AI, and Repositories.
- `app/workers/`: Background task definitions using `arq` (Redis queue).
- `docs/`: Project documentation.
- `scripts/`: Initialization and checking scripts.
- `tests/`: Unit and integration tests.

## 2. API Endpoints

| Method | Path | File | Purpose |
|---|---|---|---|
| POST | `/chat/message` | `app/api/v1/routes/chat.py (lines 43-60)` | Main endpoint to send a message to the chatbot. Handles auth and delegates to Application Layer. |
| POST | `/chat/session` | `app/api/v1/routes/chat.py (lines 62-71)` | Creates a new chat session in PostgreSQL and initializes context in Redis. |
| GET | `/chat/history/{session_id}` | `app/api/v1/routes/chat.py (lines 73-84)` | Returns paginated message history for a specific session. |
| GET | `/health` | `app/api/v1/routes/health.py (lines 14-57)` | System health check (DBs, Redis, Queue). |
| GET | `/health/cache/status` | `app/api/v1/routes/health.py (lines 64-81)` | Returns comprehensive cache statistics and status. |
| GET | `/health/cache/health` | `app/api/v1/routes/health.py (lines 84-92)` | Returns overall cache health status. |
| POST | `/health/cache/clear/sessions` | `app/api/v1/routes/health.py (lines 95-108)` | Clears all session-related Redis data. |
| POST | `/health/cache/clear/prompts` | `app/api/v1/routes/health.py (lines 111-128)` | Clears the in-memory prompt cache. |
| POST | `/health/cache/warm` | `app/api/v1/routes/health.py (lines 131-160)` | Pre-loads cached data (prompts) into memory. |
| POST | `/health/cache/reset` | `app/api/v1/routes/health.py (lines 163-187)` | Performs a complete destructive cache reset. |
| POST | `/health/cache/reload-prompt/{prompt_name}`| `app/api/v1/routes/health.py (lines 190-216)`| Hot-reloads a single prompt from disk. |
| GET | `/sessions` | `app/api/v1/routes/sessions.py (lines 25-32)` | Lists paginated user sessions. |
| DELETE | `/sessions/{session_id}` | `app/api/v1/routes/sessions.py (lines 35-42)` | Deletes a specific user session. |
| PATCH | `/sessions/{session_id}` | `app/api/v1/routes/sessions.py (lines 46-54)` | Updates a specific user session. |

## 3. AI Providers Integrated

Managed via a Factory and Registry pattern.
**File:** `app/ai/providers/factory.py (lines 15-70)`
- **Providers:**
  - **Groq** (`app/ai/providers/groq_provider.py`)
  - **Fireworks** (`app/ai/providers/fireworks_provider.py`)
  - **Gemini** (`app/ai/providers/gemini_provider.py`)
- **Fallback Logic:** Defined in `ProviderFactory.PRIORITY_LIST = ["groq", "fireworks", "gemini"]`. The factory attempts to instantiate them in this order. If multiple are configured, it wraps them in a `FallbackProvider` (`app/ai/providers/fallback_provider.py`), which catches exceptions on the primary and cascades down the priority list.

## 4. Background Workers / Scheduled Jobs

Uses `arq` (Redis-based queue).
**File:** `app/workers/arq_jobs.py` and `app/workers/summarization_worker.py`
- **Name:** `summarize_session_job` (`arq_jobs.py`, lines 58-68)
- **Trigger:** Likely triggered when a session reaches a certain message threshold (managed by `ChatApplicationService` or similar).
- **Purpose:** Calls `run_summarization_job` (`summarization_worker.py`) to summarize old messages using the primary AI provider and store the summary in the database, reducing token usage for long conversations.

## 5. Repositories / Data Access Layer

Located in `app/repositories/`. Each inherits from a base repository (`base_repo.py`).
- **`ChatbotUserRepo`** (`chatbot_user_repo.py`): Manages `chatbot_users` table.
- **`SessionRepo`** (`session_repo.py`): Manages `sessions` table.
- **`MessageRepo`** (`message_repo.py`): Manages `messages` table.
- **`MemoryRepo`** (`memory_repo.py`): Manages `session_memory` table.
- **`SummaryRepo`** (`summary_repo.py`): Manages `conv_summaries` table.
- **`ModelSettingsRepo`** (`model_settings_repo.py`): Manages `model_settings` table.

## 6. Database Models

Located in `app/models/chatbot/`. Use SQLAlchemy ORM.
- **`Message`** (`message.py`, lines 25-38):
  - **Table:** `messages`
  - **Key Fields:** `message_id`, `session_id`, `role`, `content`, `token_count`.
  - **Relationships:** Belongs to `Session`.
- **`Session`** (`session.py`, lines 28-47):
  - **Table:** `sessions`
  - **Key Fields:** `session_id`, `user_id`, `model_setting_id`, `status`, `current_intent`.
  - **Relationships:** Has many `Message`, `SessionMemory`, `ConvSummary`. Belongs to `ModelSettings`.
- **`ChatbotUser`** (`user.py`, lines 13-36):
  - **Table:** `chatbot_users`
  - **Key Fields:** `user_id`, `name`, `email`, `gender`.

## 7. Middleware

- **`RequestContextMiddleware`** (`app/core/middleware.py`, lines 15-34):
  - **Purpose:** Extracts or generates an `X-Request-ID` (Trace ID), attaches it to the request state, tracks the duration of the request processing, logs the completed request (`request.completed`), and adds the Trace ID to the response headers.

## 8. Configuration Files

**File:** `app/core/config.py` using `pydantic-settings`.
**Key Values/Constants:**
- **Database URLs:** `DATABASE_URL_CHATBOT`, `MAIN_DATABASE_URL` (Includes normalization logic for asyncpg and SSL).
- **Redis:** `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_SSL`.
- **AI API Keys & Settings:** `GEMINI_API_KEY`, `GROQ_API_KEY`, `FIREWORKS_API_KEY`.
- **Timeouts:** `GEMINI_CONNECT_TIMEOUT_SECONDS = 5`, `GEMINI_READ_TIMEOUT_SECONDS = 30`, `AI_REQUEST_TIMEOUT = 45`.
- **Cache TTLs:** `SEMANTIC_CACHE_TTL_DAYS = 7`.
- **Resilience/Retry Counts:** `LLM_MAX_RETRIES = 2`, `CIRCUIT_BREAKER_THRESHOLD = 5`.
- **Rate Limiting:** `RATE_LIMIT_FREE = 5`, `RATE_LIMIT_PREMIUM = 20`.

## 9. Deployment Files

- **`Dockerfile`** (`Dockerfile`): Uses `python:3.11-slim`. Installs Microsoft ODBC drivers (`msodbcsql17`) suggesting connection to SQL Server for the main DB. Exposes port 8000. Runs via `uvicorn`.
- **`docker-compose.yml`** (`docker-compose.yml`): Defines 4 services:
  - `app`: The main FastAPI backend.
  - `arq-worker`: Background worker running `arq app.workers.arq_jobs.WorkerSettings`.
  - `redis`: Redis server for caching and queues.
  - `postgres`: PostgreSQL 15 database.
- **CI/CD (`.github/workflows/deploy.yml`)**: GitHub Actions workflow. Triggers on pushes to `main`. Logs into Azure Container Registry, builds the Docker image, pushes it, and deploys it to Azure Container Apps (`az containerapp update`) injecting all necessary environment secrets (DB URLs, API keys).

## 10. Tests

**Directory:** `tests/`
- **What exists:**
  - `tests/unit/`: Testing individual components (`test_chat_service.py`, `test_intent_detector.py`, `test_safety.py`, `test_cache_management.py`, etc.).
  - `tests/integration/`: End-to-end and component integration tests (`test_e2e.py`, `test_postgres_sync_integration.py`, `test_redis_integration.py`, `test_worker_execution.py`).
- **Covered:** Appears to have comprehensive coverage across AI routing, caching, DB sync, orchestrator metrics, workers, and health endpoints.
- **Missing (Assumed):** Load testing or heavy performance testing scripts are not visibly present in the standard structure.

## 11. Architectural / Design Patterns

- **Repository Pattern:** Confirmed in `app/repositories/base_repo.py` and `app/repositories/session_repo.py`. Abstraction over raw DB queries using SQLAlchemy ORM.
- **Dependency Injection / IoC Container:** Confirmed in `app/core/container.py` and used in routers (e.g., `app/api/v1/routes/chat.py`, lines 25-38, `ServiceContainer.build_chat_application_service`).
- **Factory Pattern:** Confirmed in `app/ai/providers/factory.py` (`ProviderFactory.initialize_provider_chain()`).
- **Chain of Responsibility / Fallback Pattern:** Confirmed in `app/ai/providers/fallback_provider.py`. If `groq` fails, it falls back to `fireworks`, etc.
- **Service Layer Pattern:** Confirmed in `app/services/` (`chat_application_service.py`, `session_service.py`). Isolates business logic from API controllers.
