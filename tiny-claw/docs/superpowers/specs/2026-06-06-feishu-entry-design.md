# Feishu Python Entry Design

## Goal

Replace the Go-like placeholder content in `cmd/claw/main_feishu.py` with a runnable Python entrypoint that starts a Feishu webhook HTTP server for the existing Tiny Claw engine.

## Scope

In scope:
- Reuse existing Python modules in `cmd/claw/common.py` and `internal/feishu/bot.py`.
- Build an `AgentEngine` with the same tool set used by the current script-style entrypoints.
- Expose a `POST /webhook/event` HTTP endpoint.
- Parse the incoming JSON payload and forward it to the Feishu bot dispatcher.
- Add startup logging and basic environment validation.

Out of scope:
- Rewriting `internal/feishu/bot.py`.
- Adding third-party web frameworks such as Flask or FastAPI.
- Implementing Feishu request signature verification in this change.

## Approach

Use the existing `common.py` helpers to keep initialization consistent with the rest of the Python codebase:
- `configure_logging()` handles log setup.
- `build_engine()` constructs the provider, registry, and tools.

`main_feishu.py` will focus only on entrypoint concerns:
- validate required environment variables,
- construct the engine and `FeishuBot`,
- host a small HTTP server using Python standard library components,
- route `POST /webhook/event` requests into `bot.get_event_dispatcher()`.

## Request Flow

1. Process starts in `main()`.
2. Logging is configured.
3. Required environment variables are checked:
   - `ZHIPU_API_KEY`
   - `FEISHU_APP_ID`
   - `FEISHU_APP_SECRET`
4. Engine is built with:
   - read file tool
   - write file tool
   - bash tool
   - edit file tool
5. `FeishuBot` is created from the engine.
6. An HTTP server listens on `0.0.0.0:${PORT}`, defaulting to `48080`.
7. On `POST /webhook/event`, the server:
   - reads the request body,
   - decodes JSON,
   - forwards the parsed event to the Feishu dispatcher,
   - returns a success response.

## Error Handling

- Unknown routes return `404`.
- Unsupported methods return `405`.
- Invalid JSON returns `400`.
- Unexpected server-side failures return `500` and are logged.
- Missing environment variables fail fast during startup with a clear error message.

## Testing

Verification for this change should focus on:
- Python syntax/import validation for `cmd/claw/main_feishu.py`.
- Diagnostics on the edited file.
- Optional manual smoke test by launching the server and sending a sample JSON request to `POST /webhook/event`.
