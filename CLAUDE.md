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
uv run miniclaw              # Primary method - CLI agent loop
python -m coder.main         # Alternative
```

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
├── agent/                # Agent loop (s01) - core REPL with stop_reason flow
│   └── loop.py           # AgentLoop class
├── tools/                # Tool use (s02) - TOOLS schema + TOOL_HANDLERS dispatch
├── session/              # Session & context (s03) - JSONL persistence, ContextGuard overflow protection
├── channels/             # Multi-channel (s04) - Channel ABC, CLI/Telegram/Feishu implementations
├── gateway/              # Gateway & routing (s05) - BindingTable 5-tier routing, WebSocket gateway
├── intelligence/         # Intelligence layer (s06) - 8-layer prompt assembly, skills, memory
├── scheduler/            # Scheduler (s07) - HeartbeatRunner, CronService
├── delivery/             # Message delivery (s08) - Persistent queue with retry
├── resilience/           # Resilience (s09) - 3-layer retry, fallback models
├── concurrency/          # Concurrency (s10) - LaneQueue, CommandQueue
├── cli/                  # CLI utilities (colors, input/output)
├── prompts/              # System prompt management
├── settings.py           # Pydantic Settings configuration
└── main.py               # Entry point

scripts/dev/              # Development scripts (setup_dev, check_dev, format_code)
workspace/                # Runtime workspace (sessions, agents, bootstrap files, skills)
tests/                    # Test suite
```

### Core Philosophy
**Agent = while True + stop_reason**

The agent loop continuously processes messages until `stop_reason` indicates completion:
- `"stop"` → Print response and end
- `"tool_calls"` → Execute tools, append results, continue loop

### Running Agent Loop
```python
from coder.agent import AgentLoop, run_agent_loop
from coder.tools import TOOLS

# Quick start with default settings
run_agent_loop()

# With tools
run_agent_loop(tools=TOOLS)

# With tools and session persistence
run_agent_loop(tools=TOOLS, enable_session=True)

# With intelligence layer (8-layer prompt assembly)
run_agent_loop(tools=TOOLS, enable_intelligence=True)

# Custom configuration
loop = AgentLoop(
    model_id="gpt-4",
    api_key="your-key",
    system_prompt="You are a code reviewer.",
    tools=TOOLS,
    enable_session=True,
    enable_intelligence=True,
    agent_id="my-agent",
)
loop.run()
```

### Request Flow
```
User Input → messages[] → LLM API → stop_reason?
                                       ↓
                    "stop"           "tool_calls"
                       ↓                  ↓
                  Print response    Execute tools
                                         ↓
                                    Tool results
                                         ↓
                                    Back to LLM → (loop until "stop")
```

### Configuration
Environment variables in `.env` (copy from `.env.example`):
- `LOG_LEVEL` - DEBUG, INFO, WARNING, ERROR, CRITICAL
- `API_KEY` - LLM API key (required)
- `MODEL_ID` - Model identifier (default: claude-sonnet-4-20250514)
- `API_BASE_URL` - Custom API endpoint (optional)
- `MAX_TOKENS` - Max tokens per response (default: 8096)

Key feature toggles (see `.env.example` for full list):
- Session: `CONTEXT_SAFE_LIMIT`, `SESSION_WORKSPACE`
- Channels: `TELEGRAM_BOT_TOKEN`, `FEISHU_APP_ID`
- Gateway: `GATEWAY_ENABLED`, `GATEWAY_PORT`
- Intelligence: `WORKSPACE_DIR`, `MAX_SKILLS`, `MEMORY_TOP_K`
- Scheduler: `HEARTBEAT_INTERVAL`, `CRON_AUTO_DISABLE_THRESHOLD`

Settings class in `coder/settings.py` uses Pydantic Settings with automatic env var loading.

## Code Style

- **Formatter**: Ruff (120 char line length, double quotes, spaces)
- **Imports**: isort-style ordering (first-party: coder, extended, scripts, tests)
- **Type hints**: Required (Pyright for type checking, many checks relaxed for flexibility)
- **Commits**: Conventional commits format (`<type>(<scope>): <subject>`)
- **Pre-commit hooks**: Automatic linting, formatting, and commit message validation

## Key Dependencies

- **pydantic-settings 2.8.1** - Configuration management
- **litellm >=1.50.0** - LLM API integration
- **croniter >=3.0.0** - Cron scheduling
- **pytest ~=8.3.5** - Testing framework
- **ruff 0.11.2** - Linting and formatting
- **pyright 1.1.391** - Type checking
