# Project Context

## Purpose
Lowcode-Coder-Engine is a low-code code generation assistant engine built on FastAPI. It provides a scaffold for building APIs with built-in middleware, logging, exception handling, and offline API documentation support.

## Tech Stack
- **Language**: Python 3.10-3.12
- **Framework**: FastAPI 0.115.12 (with standard extras)
- **ASGI Server**: Uvicorn 0.34.3
- **Configuration**: Pydantic Settings 2.8.1
- **JSON Serialization**: ORJSON 3.10.15
- **Logging**: Loguru 0.7.3
- **Package Manager**: UV (with hatchling build backend)
- **Linting/Formatting**: Ruff 0.11.2
- **Type Checking**: Pyright 1.1.391
- **Testing**: Pytest 8.3.5 with pytest-asyncio, pytest-env, pytest-benchmark, pytest-mock
- **Pre-commit**: pre-commit 4.2.0 with Commitizen 4.9.1

## Project Conventions

### Code Style
- **Formatter**: Ruff (120 char line length, double quotes, space indentation)
- **Import Order**: isort-style with known-first-party: `coder`, `extended`, `scripts`, `tests`
- **Docstring Convention**: Google style
- **Max Complexity**: 10 (mccabe)
- **Naming**:
  - Variables: snake_case
  - Classes: PascalCase
  - Constants: UPPER_SNAKE_CASE
  - Private members: _leading_underscore

### Architecture Patterns
- **Layered Architecture**:
  - `controllers/` - API endpoints (v1 versioned)
  - `services/` - Business logic layer
  - `schemas/` - Pydantic models for request/response
  - `common/` - Utilities (logger, bgtask, singleton, ctx, path, time)
  - `middleware/` - Custom middleware (Trace, UseTime, BackGroundTask)
- **App Factory Pattern**: FastAPI app created in `application.py` with middleware registration
- **Response Patterns**: Standardized responses via `Success`, `SuccessExtra`, `Fail` classes in `schemas/base.py`
- **Configuration**: Environment-based via Pydantic Settings with `.env` file support

### Testing Strategy
- **Test Markers**: `unit`, `integration`, `slow`, `api`, `db`
- **Location**: `tests/` directory
- **Fixtures**: `conftest.py` for shared fixtures
- **Run Commands**:
  - `uv run pytest` - All tests
  - `uv run pytest -m "unit"` - By marker
  - `uv run pytest tests/test_specific.py` - Specific file

### Git Workflow
- **Commit Format**: Conventional commits (`<type>(<scope>): <subject>`)
  - Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build, revert
  - Example: `feat(auth): 添加XXX功能`
- **Commit Tool**: `uv run cz commit` for interactive commit creation
- **Pre-commit Hooks**:
  - check-merge-conflict, check-yaml, check-toml
  - check-added-large-files (max 1MB)
  - detect-private-key
  - ruff (lint + format)
  - commitizen (commit message validation)

## Domain Context
- **Timezone**: Asia/Shanghai (China timezone) - used throughout the application
- **Language**: Chinese comments and messages are acceptable
- **Response Format**: All API responses follow `{code, msg, data}` structure
- **Health Check**: Built-in `/actuator/health` endpoint
- **API Documentation**: Offline Swagger UI support (no CDN dependency)

## Important Constraints
- **Python Version**: >=3.10, <3.13
- **Max File Size**: 1MB for commits
- **Line Length**: 120 characters
- **Workers**: Default 1 worker for development
- **CORS**: Configured to allow all origins by default (production should restrict)

## External Dependencies
- **PyPI Index**: Custom nexus repository at `https://nexus.flydiysz.cn/repository/pypi-group/simple`
- **Static Files**: Swagger UI assets served locally from `static/swagger/`
- **Templates**: Jinja2 templates in `templates/` directory
