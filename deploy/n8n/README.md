# n8n Workflow Exports

This directory contains importable n8n workflow JSON files for ClawMind:

- `daily-greeting.json`
- `nightly-summary.json`
- `weekly-system-check.json`

## Workflow assumptions

- OpenClaw is reachable at `http://openclaw:8080`
- Memory API is reachable at `http://memory-api:8081`
- Notification webhook defaults can be overridden with environment variables:
  - `NOTIFICATION_WEBHOOK_URL`
  - `OPS_WEBHOOK_URL`

## Memory behavior

Each workflow reads memory before invoking OpenClaw.

If OpenClaw returns `memory_proposals`, the workflow fans the proposals out and submits them to:

- `POST http://memory-api:8081/memory/proposals`

This keeps long-term memory writes inside the memory service boundary.
