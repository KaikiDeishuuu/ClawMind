# ClawMind Docker Compose Architecture

## Compose Topology

The repository root contains `docker-compose.yml` with three runtime services:

- `openclaw`: reasoning/agent runtime
- `memory-api`: Markdown-backed memory service from this repository
- `n8n`: workflow orchestration

All three services join the same bridge network: `clawmind_net`.

## On-Disk Directory Structure

Recommended host layout:

```text
/workspace/ClawMind/
  docker-compose.yml
  docker/
    memory-api.Dockerfile
  data/
    memory/
      users/
        user_001/
          profile.md
          preferences.md
          active_projects.md
          routines.md
          inbox/
            proposals/
            committed/
            rejected/
          logs/
          history/
    openclaw/
    n8n/
  examples/
    memory/
      users/
        user_001/
          ... sample seed files ...
```

### Volume Mounts

| Service | Host path | Container path | Purpose |
|---|---|---|---|
| `memory-api` | `./data/memory` | `/data/memory` | Canonical Markdown memory store |
| `openclaw` | `./data/openclaw` | `/var/lib/openclaw` | OpenClaw runtime state/config |
| `n8n` | `./data/n8n` | `/home/node/.n8n` | n8n workflows, credentials, and execution metadata |

## Service Communication

| Caller | Target | Internal URL | Internal port | Purpose |
|---|---|---|---|---|
| `openclaw` | `memory-api` | `http://memory-api:8081` | 8081 | Read/search/propose/commit memory |
| `openclaw` | `n8n` | `http://n8n:5678` | 5678 | Optional workflow callback/webhook interactions |
| `n8n` | `openclaw` | `http://openclaw:8080` | 8080 | Trigger reasoning, scheduled greetings, summaries |
| `n8n` | `memory-api` | `http://memory-api:8081` | 8081 | Read memory before flows or submit proposals |

## Exposed Host Ports

| Service | Host port | Container port | Notes |
|---|---|---|---|
| `openclaw` | `8080` | `8080` | Main agent API |
| `memory-api` | `8081` | `8081` | Memory service API |
| `n8n` | `5678` | `5678` | n8n UI + webhook ingress |

## Startup Notes

1. Create persistent directories:
   - `mkdir -p data/memory data/openclaw data/n8n`
2. Seed the memory volume if needed:
   - `cp -R examples/memory/* data/memory/`
3. Provide an OpenClaw image or local build tagged as `openclaw:local`, or override `OPENCLAW_IMAGE`.
4. Start the stack:
   - `docker compose up -d --build`

## Runtime Environment Variables

Common overrides for `.env`:

```env
OPENCLAW_IMAGE=openclaw:local
OPENCLAW_PORT=8080
OPENCLAW_MODEL_ENDPOINT=http://host.docker.internal:11434
N8N_VERSION=1.84.1
N8N_WEBHOOK_URL=http://localhost:5678/
GENERIC_TIMEZONE=UTC
```
