# ClawMind Memory API Implementation

This repository now includes a runnable Markdown-backed Memory API implementation for ClawMind.

## Layout

```text
memory_api/
  app.py
  models.py
  service.py
examples/memory/
  users/user_001/
    profile.md
    preferences.md
    active_projects.md
    routines.md
    inbox/
      proposals/
      committed/
      rejected/
    logs/2026/03/2026-03-19.md
    history/
tests/
  test_memory_service.py
```

## Run the API

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn memory_api.app:app --reload
```

The API reads from `examples/memory` by default. Override with:

```bash
export CLAWMIND_MEMORY_ROOT=/absolute/path/to/memory-root
```

## Endpoints

- `GET /memory/{user_id}/profile`
- `GET /memory/{user_id}/preferences`
- `GET /memory/{user_id}/search?query=telegram&scopes=preferences&top_k=5`
- `POST /memory/proposals`
- `POST /memory/commit`

## Example Proposal

```json
{
  "user_id": "user_001",
  "request_id": "req_2026_03_19_001",
  "proposed_by": "openclaw",
  "memory_type": "preferences",
  "operation": "update",
  "target_path": "communication",
  "evidence": [
    "User said: please use Telegram for reminders; email is too noisy."
  ],
  "candidate_value": [
    "Prefers Telegram for reminders.",
    "Avoid email reminders when possible."
  ],
  "confidence": "high",
  "reason": "Direct explicit user instruction",
  "observed_at": "2026-03-19T08:00:00Z"
}
```
