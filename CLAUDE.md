# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**tiny-claw** is a Python-based AI agent harness/engine that implements a complete ReAct (Reasoning + Acting) loop. It's a teaching project with 22 companion articles (in `article/` and `markdown/`) that explain each component. The codebase mirrors the architecture of production agent frameworks like OpenClaw, stripped to essentials.

## Commands

### Running the Agent (CLI mode)
```bash
cd tiny-claw
python cmd/claw/main.py                    # Basic read_file demo
python cmd/claw/main_bash.py               # Bash tool demo
python cmd/claw/main_parallel_tool.py      # Parallel tool calls
python cmd/claw/main_compact.py            # Context compaction demo
python cmd/claw/main_recovery.py           # Error recovery demo
python cmd/claw/main_reminder.py           # Dead-loop prevention demo
python cmd/claw/main_session.py            # Session management demo
python cmd/claw/main_subagent.py           # Subagent delegation demo
python cmd/claw/main_middleware.py          # Middleware interception demo
python cmd/claw/main_planmode.py           # Plan mode (TODO.md persistence)
python cmd/claw/main_cost.py              # Cost tracking demo
python cmd/claw/main_trace.py             # Tracing demo
python cmd/claw/main_terminal_reportor.py # Terminal reporter demo
python cmd/claw/main_feishu.py            # Feishu bot mode
```

### Running Tests
```bash
cd tiny-claw
python -m pytest tests/                    # Run all tests
python -m pytest tests/test_claude_provider.py  # Single test file
python -m pytest tests/test_bash_tool.py -v     # Verbose single test
```

### Environment Setup
Required env vars (set in project root `.env`):
- `ZHIPU_API_KEY` — LLM API key (used by both OpenAI and Claude providers)
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` — Only needed for Feishu bot mode

## Architecture

The codebase follows an **OS kernel metaphor**: the agent engine is a micro-kernel that orchestrates providers (brain), tools (extremities), and context (memory).

### Core Loop (`internal/engine/loop.py`)

`AgentEngine.run()` implements the ReAct cycle:
1. **System prompt assembly** — `PromptComposer` builds the system message from a base template + optional `AGENTS.md` + Skills
2. **Thinking phase** (optional) — calls LLM without tools to force deliberation
3. **Action phase** — calls LLM with tools attached; model returns `tool_calls` or plain text (task complete)
4. **Observation phase** — executes tool calls in parallel via `ThreadPoolExecutor`, feeds results back
5. **Loop** — repeats until model returns no tool calls, or error

The `run_sub()` method spawns a read-only subagent with a separate system prompt and turn limit (10 turns max).

### Provider Layer (`internal/provider/`)

`LLMProvider` is the abstract interface. Two implementations:
- `OpenAIProvider` — uses `openai` SDK, targets Zhipu-compatible endpoints
- `ClaudeProvider` — uses `anthropic` SDK, targets Zhipu's Anthropic-compatible endpoint

Both normalize the internal `Message`/`ToolCall`/`ToolDefinition` schema to their respective API formats. The default model is `xiaomi/mimo-v2.5`.

### Tool System (`internal/tools/`)

`BaseTool` defines the interface: `name()`, `definition()` (returns JSON Schema for the LLM), `execute(args)`.

Built-in tools: `read_file`, `write_file`, `edit_file`, `bash`, `spawn_subagent`.

`ToolRegistry` handles:
- O(1) routing by tool name
- Middleware chain execution before each tool call (for approval/interception)
- Tracing integration via `Span` context

The `edit_file` tool uses a **4-level fuzzy matching** strategy: exact → newline-normalized → trimmed → line-by-line sliding window.

### Context Management (`internal/context/`)

- `PromptComposer` — assembles system prompt from base identity + `AGENTS.md` + Skills (YAML frontmatter markdown in `.claw/skills/`)
- `Compactor` — compresses context when it exceeds `max_chars` by folding old tool outputs and assistant reasoning, protecting the last N messages
- `RecoveryManager` — pattern-matches known tool errors and injects recovery hints (e.g., "use read_file first" for edit failures)
- `SkillLoader` — loads skill definitions from `workspace/.claw/skills/*/SKILL.md`

### Session (`internal/engine/session.py`)

`Session` is thread-safe, stores full message history with token/cost accounting. `get_working_memory(N)` returns the last N messages, auto-dropping orphaned tool results at the slice boundary.

### Observability (`internal/observability/`)

- `Tracer` / `Span` — hierarchical span-based tracing, exports JSON to `workspace/.claw/traces/`
- `CostTracker` — LLMProvider decorator that logs latency, token usage, and cost per call

### Feishu Integration (`internal/feishu/`)

`FeishuBot` connects via WebSocket, dispatches messages to the engine, and streams results back. Supports interactive card-based approval for dangerous commands via `ApprovalManager`.

### Anti-Pattern Defenses

- `ReminderInjector` — detects consecutive identical tool failures (3+) and injects a system reminder to break the loop
- `is_dangerous_command()` — regex blacklist for `rm -rf`, `sudo`, etc., triggers approval flow
- Bash tool blocks interactive confirmation prompts automatically

## Key Patterns

- All tool factories follow `Callable[[str], BaseTool]` — the `str` arg is `work_dir`
- PascalCase aliases (e.g., `NewBashTool`, `GlobalSessionMgr`) exist for Go-style naming compatibility, but Python code should use snake_case
- The `workspace/` directory is the agent's sandbox; all file operations are relative to it
- `cmd/claw/common.py` provides the standard wiring: `configure_logging()`, `require_env_vars()`, `build_engine()`, `run_prompt_main()`
