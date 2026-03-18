<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Create virtual environment and install dependencies
uv venv --python 3.11
source ./.venv/bin/activate  # Windows: .\.venv\Scripts\activate
uv sync --all-extras

# Setup development environment (installs pre-commit hooks)
uv run setup-dev
```

### Running the Application
```bash
python manage.py runserver    # Primary method
uv run runserver              # Alternative via UV script
```
Default: http://127.0.0.1:8000 | API Docs: http://127.0.0.1:8000/docs

### Testing
```bash
uv run pytest                 # Run all tests
uv run pytest tests/test_specific.py  # Run specific file
uv run pytest -v              # Verbose output
uv run pytest -m "unit"       # Run tests by marker (unit/integration/slow/api/db)
```

### Linting and Formatting
```bash
uv run ruff check coder/ extended/ manage.py    # Check issues
uv run ruff check --fix coder/ extended/ manage.py  # Auto-fix
uv run ruff format coder/ extended/ manage.py   # Format code
uv run format-code             # Combined lint + format
uv run format-code --check-only  # Check only, no fixes
```

### Type Checking
```bash
uv run pyright coder/
```

### Pre-commit and Commits
```bash
uv run pre-commit run --all-files  # Run all hooks manually
uv run cz commit                    # Conventional commit (format: <type>(<scope>): <subject>)
```

## Architecture

### Project Structure
```
coder/                    # Core application module
├── application.py        # FastAPI app factory, middleware registration
├── settings.py           # Pydantic Settings configuration
├── run.py                # Uvicorn entry point
├── common/               # Utilities: logger, exception_handler, bgtask, singleton
├── middleware/           # Custom middleware (Trace, UseTime, BackGroundTask)
├── controllers/v1/       # API v1 endpoints
├── schemas/              # Pydantic models (base.py has response wrappers)
└── services/             # Business logic layer

extended/fastapi/         # Framework extensions (custom ORJSONResponse)
static/swagger/           # Offline Swagger UI assets
scripts/dev/              # Development scripts
tests/                    # Test suite
manage.py                 # Click-based CLI
```

### Application Bootstrap Flow
1. `coder/__init__.py` → setup_logger()
2. `coder/run.py` → imports app from application.py, reads settings
3. `coder/application.py` → creates FastAPI app, registers middleware (CORS, Trace, UseTime, BG tasks), mounts static files, configures Jinja2 templates, sets up offline API docs, includes routers

### Request Flow
```
Request → BackGroundTaskMiddleware → CORSMiddleware → TraceMiddleware → UseTimeMiddleware → Route Handler → Response
```

### Response Patterns
```python
from coder.schemas.base import Success, SuccessExtra, Fail

# Success response
return Success(data={"key": "value"}, msg="Success")
# {"code": 200, "msg": "Success", "data": {"key": "value"}}

# Paginated response
return SuccessExtra(data=items, total=100, page=1, page_size=20)

# Error response
from starlette.status import HTTP_400_BAD_REQUEST
return Fail(code=HTTP_400_BAD_REQUEST, msg="Invalid input")
```

### Middleware Utilities
```python
from coder.middleware.middlewares import get_trace_id
trace_id = get_trace_id()  # Get current request trace ID

from coder.common.bgtask import BgTasks
BgTasks.add_task(lambda: print("Background work"))  # Schedule background task
```

### Configuration
Environment variables in `.env` (copy from `.env.example`):
- `LOG_LEVEL` - DEBUG, INFO, WARNING, ERROR, CRITICAL
- `API_DOCS_ENABLED` - Enable/disable Swagger UI
- `HOST`, `PORT`, `WORKERS` - Server configuration
- `CORS_*` - CORS settings
- `API_KEY`, `MODEL_ID`, `API_BASE_URL`, `MAX_TOKENS` - Agent configuration

Settings class in `coder/settings.py` uses Pydantic Settings with automatic env var loading.

### Agent Components (s01+)
```
coder/components/
├── cli/                    # CLI tools (colors, input/output)
├── prompts/                # System prompt management
├── agent/                  # Agent loop implementation
└── channels/               # Channel implementations (s04+)
```

Running Agent Loop:
```python
from coder.components.agent import AgentLoop, run_agent_loop

# Quick start
run_agent_loop()

# With custom config
loop = AgentLoop(model_id="gpt-4", api_key="your-key")
loop.run()
```

### Adding New Routes
1. Create controller in `coder/controllers/my_controller.py`
2. Register in `coder/application.py`: `app.include_router(my_router)`

## Code Style

- **Formatter**: Ruff (120 char line length, double quotes, spaces)
- **Imports**: isort-style ordering
- **Type hints**: Required (Pyright for type checking)
- **Commits**: Conventional commits format (`<type>(<scope>): <subject>`)
- **Pre-commit hooks**: Automatic linting, formatting, and commit message validation

## Key Dependencies

- FastAPI 0.115.12 with standard extras
- Pydantic Settings 2.8.1 for configuration
- ORJSON for fast JSON serialization
- Uvicorn as ASGI server
- Ruff for linting/formatting
- Pytest for testing
