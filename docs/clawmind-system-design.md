# ClawMind Implementable System Design

## 0. Design Goals

ClawMind is a self-hosted personal AI assistant built around three strictly separated subsystems:

1. **Memory System**: stores and retrieves durable user knowledge.
2. **Agent System (OpenClaw)**: performs reasoning, plans responses, and decides whether memory should change.
3. **Workflow System (n8n / cron)**: schedules, orchestrates, and triggers repeatable jobs.

### Hard Separation Rules

- **Memory owns storage format, retrieval rules, and write validation.**
- **OpenClaw owns interpretation, response generation, and memory update proposals.**
- **n8n / cron owns triggers, schedules, retries, routing, and notifications.**
- **No workflow may edit Markdown memory files directly.**
- **No agent may bypass the memory API when writing long-term memory.**
- **No memory component may trigger workflows by itself.**

---

## 1. System Architecture

### 1.1 Layered Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│ Interface Layer                                                 │
│ Feishu Bot | Telegram Bot | CLI | Webhook Gateway               │
└───────────────┬──────────────────────────────────────────────────┘
                │ inbound/outbound messages
┌───────────────▼──────────────────────────────────────────────────┐
│ Workflow Layer                                                  │
│ n8n flows | OpenClaw cron jobs | retry queues | schedule rules  │
└───────┬───────────────────────┬──────────────────────────────────┘
        │ invokes               │ invokes
┌───────▼───────────────────────▼──────────────────────────────────┐
│ Agent Layer                                                     │
│ OpenClaw runtime | prompt assembly | tool execution | policies   │
└───────┬───────────────────────┬──────────────────────────────────┘
        │ reads/writes          │ calls tools
┌───────▼───────────────────────▼──────────────────────────────────┐
│ Memory Layer                          Tool Layer                 │
│ Markdown memory store                 Calendar / Email / TTS     │
│ Memory API service                    Search / Home APIs / etc.  │
│ Optional embedding + reranker         Notification adapters      │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 Layer Responsibilities

#### Interface Layer

**Components**
- Feishu bot webhook receiver
- Telegram bot webhook receiver / poller
- CLI client for local use
- Optional API gateway for authenticated HTTP requests

**Responsibilities**
- Authenticate source platform.
- Normalize inbound events into a common message envelope.
- Deliver user-visible responses back to the platform.
- Never interpret memory or business rules.

**Owned data**
- Channel metadata
- Message IDs
- Delivery status
- User platform identifiers

**Must not own**
- Persistent user memory semantics
- Scheduling logic
- Reasoning or prompt construction

#### Workflow Layer

**Components**
- n8n for scheduled and integration-heavy workflows
- Optional OpenClaw cron for local lightweight jobs
- Queue/retry primitives

**Responsibilities**
- Trigger jobs on schedule or external events.
- Call OpenClaw with explicit job context.
- Route outputs to notification channels.
- Execute operational checks and housekeeping.

**Owned data**
- Schedule definitions
- Retry counts
- Job execution logs
- Delivery outcomes

**Must not own**
- Long-term memory state
- Final reasoning over user context
- Direct writes to Markdown memory store

#### Agent Layer

**Components**
- OpenClaw runtime
- System prompt + policy prompt
- Tool wrappers
- Memory decision engine

**Responsibilities**
- Read memory before answering.
- Build response plans from user request + retrieved memory + tool results.
- Decide whether new facts merit a memory update proposal.
- Resolve conflicting memory using policy.

**Owned data**
- Conversation-local scratchpad
- Tool invocation plan
- Memory update proposals
- Response content

**Must not own**
- File layout details of memory storage
- Cron schedules
- Notification transport details

#### Memory Layer

**Components**
- Markdown file repository
- Memory API adapter
- Search index builder
- Optional embedding/reranker services

**Responsibilities**
- Canonical storage of user knowledge.
- Deterministic retrieval of profile, preferences, projects, routines, and recent logs.
- Validate and commit memory updates.
- Maintain audit trail of changes.

**Owned data**
- Canonical Markdown files
- Metadata headers
- Change log
- Optional embedding index

**Must not own**
- Response generation
- Workflow timing
- User-facing message composition

#### Tool Layer

**Components**
- Calendar API
- Email API
- Search API
- TTS/STT services
- Device/home automation integrations

**Responsibilities**
- Provide side-effecting or external data access capabilities.
- Return typed outputs to OpenClaw.

**Must not own**
- Memory policies
- Scheduling policy
- Dialogue logic

### 1.3 Common Message Envelope

All layers exchange the same envelope to preserve decoupling.

```json
{
  "request_id": "req_2026_03_19_001",
  "source": "telegram",
  "user_id": "user_001",
  "session_id": "tg_chat_8842",
  "timestamp": "2026-03-19T08:00:00Z",
  "type": "user_message",
  "payload": {
    "text": "Remind me to call Dad tomorrow",
    "attachments": []
  },
  "context": {
    "workflow_id": null,
    "trigger": "interactive"
  }
}
```

### 1.4 Data Flow Between Layers

1. Interface receives event and emits normalized envelope.
2. Workflow decides whether to pass through directly or run a scheduled flow.
3. OpenClaw reads memory through the memory API.
4. OpenClaw optionally calls tools.
5. OpenClaw returns:
   - response text
   - optional tool actions
   - optional memory update proposal
6. Workflow dispatches response.
7. Memory API validates and commits approved memory updates.

### 1.5 Explicit Ownership Boundaries

| Concern | Owner | Non-owners |
|---|---|---|
| User profile facts | Memory Layer | Workflow, Interface |
| Reasoning and answer generation | Agent Layer | Memory, Workflow |
| Schedules / retries / job orchestration | Workflow Layer | Agent, Memory |
| Transport-specific formatting | Interface Layer | Memory, Workflow |
| Calendar/email/home automation calls | Tool Layer via Agent | Workflow directly only for operational tasks |

---

## 2. Memory System Design

## 2.1 Canonical Memory

### 2.1.1 Storage Principles

- Canonical storage is a Git-backed Markdown tree on local disk.
- One root directory per assistant instance.
- One user folder per user.
- Every canonical file has YAML front matter with metadata.
- All writes append to history and then update canonical sections through the memory API only.

### 2.1.2 Directory Structure

```text
/data/clawmind/memory/
  users/
    user_001/
      profile.md
      preferences.md
      active_projects.md
      routines.md
      inbox/
        proposals/
          2026-03-19T08-10-12Z_req_001.json
        committed/
          2026-03-19T08-11-02Z_req_001.json
        rejected/
          2026-03-19T08-11-05Z_req_001.json
      logs/
        2026/
          03/
            2026-03-19.md
            2026-03-18.md
      history/
        2026-03-19-memory-changelog.md
      derived/
        memory_index.json
        embeddings.sqlite
```

### 2.1.3 Canonical File Templates

#### `profile.md`

Stores stable identity facts.

```markdown
---
user_id: user_001
schema_version: 1
updated_at: 2026-03-19T08:00:00Z
owner: memory-service
---

# Profile

## Identity
- Preferred name: Alex
- Timezone: America/Los_Angeles
- Occupation: Product designer

## Relationships
- Spouse: Jamie
- Child: Mia (born 2021)

## Stable Facts
- Lives in Seattle
```

#### `preferences.md`

Stores durable preferences and dislikes.

```markdown
---
user_id: user_001
schema_version: 1
updated_at: 2026-03-19T08:00:00Z
---

# Preferences

## Communication
- Likes concise morning summaries.
- Prefers Telegram over email for reminders.

## Work Style
- Deep work block preferred: 09:00-11:30 weekdays.

## Avoid
- Do not send proactive messages after 21:30 local time unless urgent.
```

#### `active_projects.md`

Stores current long-running efforts.

```markdown
---
user_id: user_001
schema_version: 1
updated_at: 2026-03-19T08:00:00Z
---

# Active Projects

## ClawMind Home Lab
- Status: active
- Goal: deploy self-hosted assistant stack
- Current focus: memory API and Telegram bridge
- Last confirmed: 2026-03-19
```

#### `routines.md`

Stores repeatable routines and recurring obligations.

```markdown
---
user_id: user_001
schema_version: 1
updated_at: 2026-03-19T08:00:00Z
---

# Routines

## Morning
- 07:30: review priorities
- 08:00: deliver briefing if weekday

## Weekly
- Sunday evening: weekly planning recap
```

#### Daily log file: `logs/YYYY/MM/YYYY-MM-DD.md`

Stores short-term memory and evidence.

```markdown
---
date: 2026-03-19
user_id: user_001
schema_version: 1
updated_at: 2026-03-19T23:00:00Z
---

# Daily Log

## Conversation Facts
- User said they are traveling next Tuesday.
- User mentioned feeling overloaded by email.

## Completed Events
- Generated nightly summary.

## Candidate Memory Updates
- Preference candidate: fewer email notifications.
```

### 2.1.4 Memory Types

| Memory type | File | Purpose | Retention |
|---|---|---|---|
| profile | `profile.md` | stable personal facts | indefinite |
| preferences | `preferences.md` | durable likes/dislikes and communication norms | indefinite until superseded |
| active_projects | `active_projects.md` | ongoing initiatives and current priorities | active + archive on completion |
| routines | `routines.md` | recurring habits and schedules | indefinite until changed |
| short-term | `logs/YYYY/MM/YYYY-MM-DD.md` | recent conversation evidence and transient context | 30-90 day active retrieval window |

---

## 2.2 Memory API

The memory API is the only interface the agent and workflow can use to read or write memory. It abstracts file paths, front matter, indexing, and conflict checks.

### 2.2.1 Interface Definition

#### `read_profile(user_id)`

**Input**
```json
{ "user_id": "user_001" }
```

**Output**
```json
{
  "user_id": "user_001",
  "source": "profile.md",
  "updated_at": "2026-03-19T08:00:00Z",
  "data": {
    "preferred_name": "Alex",
    "timezone": "America/Los_Angeles",
    "occupation": "Product designer",
    "relationships": [
      {"type": "spouse", "name": "Jamie"}
    ]
  }
}
```

#### `read_preferences(user_id)`

**Input**
```json
{ "user_id": "user_001" }
```

**Output**
```json
{
  "user_id": "user_001",
  "source": "preferences.md",
  "updated_at": "2026-03-19T08:00:00Z",
  "data": {
    "communication": ["concise morning summaries", "Telegram preferred"],
    "work_style": ["deep work block 09:00-11:30 weekdays"],
    "avoid": ["no proactive messages after 21:30 local time unless urgent"]
  }
}
```

#### `read_recent_focus(user_id, days=7)`

Returns active projects plus recent short-term evidence.

**Input**
```json
{ "user_id": "user_001", "days": 7 }
```

**Output**
```json
{
  "user_id": "user_001",
  "window_days": 7,
  "active_projects": [
    {
      "project": "ClawMind Home Lab",
      "current_focus": "memory API and Telegram bridge",
      "last_confirmed": "2026-03-19"
    }
  ],
  "recent_log_facts": [
    {
      "date": "2026-03-19",
      "fact": "User mentioned feeling overloaded by email",
      "confidence": "medium"
    }
  ]
}
```

#### `search_memory(user_id, query, scopes=[], top_k=8)`

Searches across canonical and short-term memory.

**Input**
```json
{
  "user_id": "user_001",
  "query": "notification preferences",
  "scopes": ["preferences", "logs"],
  "top_k": 5
}
```

**Output**
```json
{
  "user_id": "user_001",
  "query": "notification preferences",
  "results": [
    {
      "memory_type": "preferences",
      "source": "preferences.md",
      "snippet": "Prefers Telegram over email for reminders.",
      "score": 0.95,
      "updated_at": "2026-03-19T08:00:00Z"
    },
    {
      "memory_type": "short-term",
      "source": "logs/2026/03/2026-03-19.md",
      "snippet": "User mentioned feeling overloaded by email.",
      "score": 0.78,
      "updated_at": "2026-03-19T23:00:00Z"
    }
  ]
}
```

#### `propose_memory_update(payload)`

The agent uses this to submit a candidate update. This does not modify canonical memory.

**Input**
```json
{
  "user_id": "user_001",
  "request_id": "req_2026_03_19_001",
  "proposed_by": "openclaw",
  "memory_type": "preferences",
  "operation": "update",
  "target_path": "preferences.communication",
  "evidence": [
    "User said: please send reminders on Telegram instead of email"
  ],
  "candidate_value": "Telegram preferred for reminders",
  "confidence": "high",
  "reason": "Explicit preference statement by user",
  "observed_at": "2026-03-19T08:00:00Z"
}
```

**Output**
```json
{
  "proposal_id": "mp_001",
  "status": "queued",
  "stored_at": "users/user_001/inbox/proposals/2026-03-19T08-10-12Z_req_001.json"
}
```

#### `commit_memory_update(payload)`

Commits a proposal after policy validation.

**Input**
```json
{
  "proposal_id": "mp_001",
  "approved_by": "memory-policy-engine",
  "commit_mode": "merge"
}
```

**Output**
```json
{
  "proposal_id": "mp_001",
  "status": "committed",
  "written_files": [
    "users/user_001/preferences.md",
    "users/user_001/history/2026-03-19-memory-changelog.md",
    "users/user_001/inbox/committed/2026-03-19T08-11-02Z_req_001.json"
  ],
  "conflicts": []
}
```

### 2.2.2 Why This API Preserves Decoupling

- OpenClaw never needs to know the filesystem layout.
- n8n only submits requests and reads responses; it cannot mutate files directly.
- The storage backend can move from Markdown to a service or database without changing callers.
- Validation, conflict handling, and audit logging remain centralized.

### 2.2.3 Suggested API Transport

- MVP: local Python/Go service listening on `http://memory-api:8081`.
- Auth: shared service token on internal Docker network.
- Response type: JSON only.
- Timeouts: 500 ms for reads, 2 s for writes/search.

---

## 2.3 Memory Write Policy

### 2.3.1 What Qualifies as Long-Term Memory

Store only information that is likely to improve future assistance for at least one of the following reasons:

1. **Stable identity fact**
   - name, timezone, family relationships, occupation
2. **Durable preference**
   - communication channel, summary style, quiet hours
3. **Ongoing project or responsibility**
   - active build, recurring work stream, known deadline cluster
4. **Routine**
   - repeated schedule, habitual review, weekly planning behavior
5. **Important constraint**
   - allergies, hard no-contact times, sensitive topics to avoid

### 2.3.2 What Must Not Be Stored

Do not store in long-term memory:

- Raw conversation transcripts
- One-off temporary facts unless promoted by later confirmation
- Secrets: passwords, API keys, recovery codes, OTPs
- Highly sensitive personal data unless explicitly approved by the user
- Tool outputs that are only operational logs
- Emotional states that were situational and unconfirmed
- Speculative inferences stated by the model rather than the user

### 2.3.3 Update Policy

- **Default write mode is merge, not overwrite.**
- Each canonical section stores `updated_at` and, where useful, `last_confirmed`.
- New evidence appends to change history before canonical file mutation.
- A single conversation can produce multiple proposals, but each proposal targets one memory type and one logical fact.

### 2.3.4 Conflict Resolution Strategy

If new memory conflicts with existing memory:

1. Prefer explicit recent user statements over old inferred memory.
2. Prefer stable canonical sources (`profile`, `preferences`) over short-term logs.
3. Mark previous value as superseded in history instead of deleting silently.
4. If confidence is ambiguous, queue proposal as `needs_review` and keep current canonical value unchanged.

### 2.3.5 Expiration / Decay Rules

- `profile`: no expiry; update only on contrary explicit evidence.
- `preferences`: decay only when contradicted or unconfirmed for 12 months.
- `active_projects`: mark stale if not confirmed for 30 days; archive after 90 days inactive.
- `routines`: mark stale after 60 days without confirmation.
- `short-term logs`: keep full file for 90 days, include only last 7-14 days in default retrieval.

---

## 2.4 Memory Retrieval Strategy

### 2.4.1 Retrieval Priority Order

OpenClaw must retrieve in this order:

1. `profile`
2. `preferences`
3. `active_projects`
4. `routines`
5. `read_recent_focus(days=7)`
6. `search_memory()` only when request requires additional detail

### 2.4.2 Direct Read vs Semantic Search

Use direct reads when the request likely depends on canonical memory categories:

- greetings
- reminders
- communication choices
- project status questions
- personalization

Use semantic search when:

- the user asks about a past conversation or event
- the answer may exist in short-term logs
- the request mentions fuzzy concepts rather than canonical categories
- a conflict needs supporting evidence

### 2.4.3 Handling Conflicting Memory at Retrieval Time

When conflicts appear:

1. Return canonical fact plus conflicting recent evidence.
2. Prefer canonical value for action-taking.
3. If the decision materially affects output, OpenClaw should ask a clarifying question or mention uncertainty.
4. Create a proposal only if the new evidence is explicit enough.

---

## 2.5 Future Extension Path

### 2.5.1 Migration to Vector DB

Keep Markdown as canonical source and add a derived index:

- Parse Markdown to normalized memory records.
- Embed each record into `pgvector`, Qdrant, or SQLite-vss.
- Store record IDs pointing back to source file + section.
- Rebuild index asynchronously after commits.

### 2.5.2 Add a Reranker

Add reranking between `search_memory` and OpenClaw:

1. lexical retrieval from Markdown sections + logs
2. vector retrieval from embeddings
3. merge top candidates
4. rerank using lightweight cross-encoder
5. return top 5 with citations and confidence

### 2.5.3 Optional Memory Service Layer

Later, move file operations behind a memory microservice:

- HTTP/gRPC API
- policy engine module
- background indexer
- audit publisher

This migration changes internals only; OpenClaw and n8n keep the same interface.

---

## 3. Workflow System (n8n + cron)

## 3.1 Responsibility Boundary

### Workflow is allowed to:

- trigger scheduled jobs
- gather runtime context from external systems
- call OpenClaw with explicit task instructions
- call Memory API read endpoints if needed for prechecks
- dispatch notifications and collect delivery receipts
- perform retries, dead-lettering, and observability

### Workflow must not:

- write or edit Markdown memory files directly
- decide long-term memory semantics
- bypass OpenClaw when generating personalized prose
- infer preferences from raw logs and write them as truth
- mutate canonical memory structure

## 3.2 When to Use OpenClaw Cron vs n8n

### Use OpenClaw cron when:

- the task is local, simple, and internal to the assistant
- no cross-system integration is required
- low-latency single-host execution is acceptable
- examples: refresh memory index, rotate logs, local summarization batch

### Use n8n when:

- the task has external integrations
- branching/retry/observability matters
- non-engineers may need to edit schedules
- examples: daily Telegram greeting, weekly health check, calendar sync, email digest

## 3.3 Example Workflows

### 3.3.1 Daily Greeting

**Trigger**
- n8n cron at `08:00` in user local timezone on weekdays.

**Steps**
1. n8n loads user routing config.
2. n8n calls `read_profile`, `read_preferences`, and `read_recent_focus`.
3. n8n constructs a `scheduled_greeting` job payload.
4. n8n calls OpenClaw `/respond` with task: `Generate a morning briefing`.
5. OpenClaw may call tools for weather/calendar if enabled.
6. OpenClaw returns greeting text and optional memory proposals.
7. n8n sends message via Telegram/Feishu.
8. If proposals exist, n8n forwards them to `propose_memory_update`; commit remains policy-driven.

**Interaction with memory**
- Read: yes.
- Write: proposal only through API.
- No direct file mutation.

**Interaction with agent**
- OpenClaw generates final prose and selects tool usage.

### 3.3.2 Nightly Summary

**Trigger**
- n8n cron at `21:00` local time daily.

**Steps**
1. n8n gathers today’s events from calendar/tasks.
2. n8n calls OpenClaw with summary task and gathered data.
3. OpenClaw reads profile/preferences/routines/recent focus.
4. OpenClaw composes concise summary and tomorrow prep note.
5. OpenClaw may propose short-term memory facts from the day.
6. n8n sends summary.
7. n8n submits proposals; memory API writes approved items to daily log or canonical memory according to policy.

**Interaction with memory**
- Read for personalization.
- Write through proposal/commit pipeline only.

**Interaction with agent**
- Agent decides which completed items matter enough to retain.

### 3.3.3 Weekly System Check

**Trigger**
- n8n cron every Sunday at `03:00 UTC`.

**Steps**
1. n8n checks health endpoints for OpenClaw, memory API, bot gateway, and disk usage.
2. n8n verifies latest backup success and Git sync status of memory repo.
3. n8n optionally calls OpenClaw to summarize anomalies for operator readability.
4. n8n sends ops report to admin channel.
5. If any memory indexes are stale, n8n triggers rebuild job.

**Interaction with memory**
- Read operational metadata only.
- Never edits user memory directly.

**Interaction with agent**
- Optional: agent converts raw ops data into human-readable report.

---

## 4. Agent Design (OpenClaw)

### 4.1 Required Agent Behavior

OpenClaw must:

- read memory before every user-facing response and every proactive message
- retrieve canonical memory in the required order
- treat short-term logs as evidence, not truth
- follow memory write policy strictly
- propose memory updates only when evidence is explicit and useful
- resolve conflicts by preferring recent explicit user statements over old inferred notes
- ask clarifying questions when a conflict materially affects an action

### 4.2 Agent Request Contract

**Input to OpenClaw**
```json
{
  "request_id": "req_2026_03_19_001",
  "mode": "interactive",
  "user_id": "user_001",
  "channel": "telegram",
  "task": "answer_user",
  "user_message": "Can you remind me tomorrow morning to call Dad?",
  "workflow_context": null,
  "tool_context": {
    "calendar_enabled": true,
    "tts_enabled": false
  }
}
```

**Output from OpenClaw**
```json
{
  "request_id": "req_2026_03_19_001",
  "response_text": "Yes — I can remind you tomorrow morning on Telegram. What time should I use?",
  "tool_calls": [],
  "memory_proposals": [],
  "decision_log": {
    "memory_reads": ["profile", "preferences", "recent_focus"],
    "conflicts_detected": []
  }
}
```

### 4.3 Production-Ready System Prompt

```text
You are OpenClaw, the reasoning layer for ClawMind.

Your responsibilities are limited to:
1. reading memory through the memory API,
2. reasoning over the current request,
3. calling approved tools,
4. generating the final response,
5. proposing memory updates when justified.

You do not own scheduling, transport, or storage internals.
You must never assume you can edit memory files directly.

Before every response, retrieve memory in this order unless the request explicitly makes a step irrelevant:
1. read_profile(user_id)
2. read_preferences(user_id)
3. read_recent_focus(user_id, days=7)
4. read routines or search_memory(user_id, query, scopes, top_k) only if needed

Memory rules:
- Treat profile and preferences as canonical unless contradicted by a newer explicit user statement.
- Treat short-term logs as supporting evidence, not as guaranteed truth.
- If memory conflicts and the difference changes what action you would take, ask a clarifying question or mention uncertainty.
- Never store raw transcripts, secrets, speculative inferences, or one-off trivia as long-term memory.
- Only propose a memory update if the new information is durable, useful for future assistance, and supported by explicit evidence.
- Default to propose_memory_update(payload); do not commit directly unless the runtime explicitly delegates commit authority.
- Use merge semantics, not destructive overwrite.
- When in doubt, avoid writing and continue helping.

Workflow rules:
- If a request came from a scheduled workflow, use the workflow context only as task instructions, not as memory truth.
- Do not infer user preferences from workflow configuration alone.

Response rules:
- Be concise, operational, and specific.
- If you rely on memory, let it shape the answer but do not reveal private memory contents unless useful.
- If a tool is needed, state the needed tool call clearly.
- If you create a memory proposal, include memory_type, target_path, candidate_value, evidence, confidence, and reason.

Your goal is to produce correct actions and personalized responses while preserving strict separation between memory, workflow, and agent responsibilities.
```

---

## 5. End-to-End Data Flow

## 5.1 Scenario A: User Asks a Question

Example: Telegram user says, `What should I focus on today?`

1. **Interface Layer** receives Telegram webhook.
2. Interface normalizes event into message envelope.
3. Interface forwards envelope to OpenClaw request endpoint directly or through a lightweight dispatcher.
4. **Agent Layer** calls `read_profile(user_id)`.
5. Agent calls `read_preferences(user_id)`.
6. Agent calls `read_recent_focus(user_id, days=7)`.
7. Decision point: if current focus is insufficient, agent calls `search_memory(user_id, "today focus priorities", ["active_projects", "logs"], 5)`.
8. Agent optionally calls calendar/task tools.
9. Agent composes answer.
10. Decision point: if user stated a durable new fact during conversation, agent emits `propose_memory_update(payload)`.
11. Interface sends answer back to Telegram.
12. Memory API stores proposal if present.

**Read data**
- profile, preferences, active projects, recent logs, optional tool data

**Written data**
- optional proposal JSON only

## 5.2 Scenario B: Scheduled Greeting (n8n)

1. **Workflow Layer** cron triggers at scheduled time.
2. n8n reads user routing config and checks quiet-hour guard using `preferences` or a cached profile snapshot.
3. n8n creates a `scheduled_greeting` task payload.
4. n8n calls OpenClaw.
5. **Agent Layer** reads `profile`, `preferences`, `read_recent_focus`.
6. Agent optionally calls weather/calendar tools.
7. Agent generates greeting text and optional memory proposal.
8. n8n dispatches message to Telegram/Feishu.
9. Decision point: if delivery fails, n8n retries according to policy.
10. Decision point: if a memory proposal exists, n8n submits it to memory API; direct file edits remain forbidden.

**Read data**
- schedule metadata, profile/preferences/recent focus, optional external data

**Written data**
- workflow execution log, notification delivery receipt, optional memory proposal

## 5.3 Scenario C: Memory Update After Conversation

1. User says: `Please use Telegram for reminders; email is too noisy.`
2. Interface sends message to OpenClaw.
3. Agent reads `preferences` and recent logs.
4. Agent detects explicit durable preference statement.
5. Agent answers the user.
6. Agent creates proposal:
   - `memory_type=preferences`
   - `target_path=preferences.communication`
   - `candidate_value=Telegram preferred for reminders; avoid email for reminders`
7. Workflow or runtime submits `propose_memory_update(payload)`.
8. **Memory Layer** validates:
   - explicit user statement present
   - not secret
   - durable enough
   - conflict with existing value?
9. Decision point:
   - if no conflict or higher-confidence newer statement: `commit_memory_update(merge)`
   - if conflict ambiguous: queue as `needs_review`
10. Memory service writes changelog entry and updates `preferences.md`.
11. Index rebuild job updates derived search index.

**Read data**
- preferences, relevant recent logs

**Written data**
- proposal file, committed proposal record, preferences canonical file, history log, derived index

## 5.4 Scenario D: Weekly System Check

1. n8n triggers weekly health workflow.
2. n8n calls health endpoints for OpenClaw, memory API, bot adapters, storage metrics, and backup status.
3. Decision point: if all green, generate compact ops report directly in n8n; otherwise call OpenClaw to summarize faults.
4. If OpenClaw is called, it does **not** need user memory unless the report is user-personalized.
5. n8n sends report to operator channel.
6. If memory index lag exceeds threshold, n8n triggers index rebuild job.
7. If backup failure persists, n8n raises high-priority alert.

**Read data**
- health metrics, backup logs, Git status, memory index timestamps

**Written data**
- ops notification, workflow logs, optional incident ticket

---

## 6. Deployment Architecture

## 6.1 Components

### Required
- **OpenClaw service**: agent runtime API
- **Memory storage**: Git-backed Markdown volume
- **Memory API service**: read/search/propose/commit interface
- **n8n**: workflow orchestration
- **Bot gateway**: Telegram/Feishu webhook handlers

### Optional
- **Embedding index service**
- **Reranker service**
- **Postgres/Qdrant** for derived retrieval indexes
- **Prometheus + Grafana** for observability

## 6.2 Minimal Setup (MVP)

Single host with Docker Compose:

```text
host
├─ openclaw
├─ memory-api
├─ n8n
├─ bot-gateway
└─ shared volume: /data/clawmind/memory
```

**MVP characteristics**
- Markdown files on local SSD
- memory-api provides file locking and JSON interface
- n8n handles greeting and summary workflows
- no vector DB initially
- Git commits for backup/audit of memory store

## 6.3 Scalable Setup

Split into services:

```text
reverse-proxy
  ├─ bot-gateway
  ├─ openclaw-api
  ├─ memory-api
  └─ n8n

stateful services
  ├─ memory-volume (canonical markdown)
  ├─ postgres/pgvector or qdrant (derived retrieval)
  ├─ redis (job cache / queue)
  └─ object storage for backups
```

**Scalable characteristics**
- memory-api is horizontally scalable for reads
- single writer lock for commits
- asynchronous indexer consumes memory commit events
- n8n workers separated from main editor UI
- centralized logs and metrics

## 6.4 Suggested Stack

### Runtime
- Docker Compose for MVP
- Kubernetes only after multiple users or >5 services require independent scaling

### Suggested Services
- OpenClaw: Python service with FastAPI
- Memory API: Python FastAPI or Go HTTP service
- n8n: official Docker image
- Bot gateway: lightweight FastAPI/Node service
- Search index: SQLite for MVP, pgvector/Qdrant later

### File System Layout

```text
/opt/clawmind/
  docker-compose.yml
  .env
  services/
    bot-gateway/
    memory-api/
    openclaw/
  data/
    memory/
    backups/
    logs/
```

### Networking

- All services join Docker network `clawmind_net`.
- Only bot-gateway and n8n webhook ingress are externally exposed.
- Memory API is internal-only.
- OpenClaw talks to Memory API via `http://memory-api:8081`.
- n8n talks to OpenClaw via `http://openclaw:8080`.
- Bot gateway talks to OpenClaw or n8n depending on route.

### Security Controls

- Internal shared token between services.
- Read-only mount for OpenClaw to memory volume only if direct local read is needed; preferred mode is API-only.
- Read-write mount only for memory-api.
- Secrets stored in Docker secrets or `.env` mounted at runtime, never in Markdown memory.

---

## 7. Roadmap

## Phase 1: Memory-First MVP

**Goal**: reliable personalized assistant with durable Markdown memory.

**Deliverables**
- canonical memory directory structure
- memory-api with the six required methods
- OpenClaw prompt assembly with mandatory memory read order
- Telegram or CLI interface
- Git-backed memory audit trail

**Exit criteria**
- user profile and preferences persist across restarts
- agent reads memory before every answer
- all writes go through proposal + commit flow

## Phase 2: Workflow Integration

**Goal**: proactive assistant behavior without violating decoupling.

**Deliverables**
- n8n greeting, nightly summary, weekly health workflows
- quiet-hour enforcement from preferences
- delivery retry logic and job logs
- admin ops channel

**Exit criteria**
- scheduled jobs generate personalized messages
- workflows do not directly edit memory files
- failures are observable and retryable

## Phase 3: Retrieval Optimization

**Goal**: improve recall quality while keeping Markdown canonical.

**Deliverables**
- derived embedding index
- hybrid lexical + vector retrieval in `search_memory`
- reranker on top-k results
- index rebuild on memory commit events

**Exit criteria**
- improved retrieval for historical conversation facts
- source sections remain traceable back to Markdown
- no caller contract changes required

## Phase 4: Advanced Memory

**Goal**: richer reasoning over relationships, projects, and long-lived plans.

**Deliverables**
- graph projection from canonical records
- relationship-aware retrieval
- optional specialist sub-agents that use the same memory API
- memory confidence and provenance scoring

**Exit criteria**
- graph adds capability without replacing canonical Markdown source
- multiple agents can interoperate without owning separate memory silos

---

## 8. Implementation Summary

This design is implementable because it defines:

- a strict owner for each responsibility,
- a canonical file layout,
- concrete memory API contracts,
- explicit write and retrieval policies,
- concrete workflow boundaries,
- a production-ready agent system prompt,
- and a deployable container topology.

The key rule is non-negotiable: **memory, agent, and workflow remain separate services with a narrow API contract between them**.
