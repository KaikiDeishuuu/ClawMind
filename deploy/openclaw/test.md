# ClawMind OpenClaw Local Test Matrix

## Section 1: Identity Test

### Test 1.1
- Input prompt: `Who am I?`
- Expected behavior:
  - Read `MEMORY.md` first.
  - Read `memory/profile.md` before answering.
  - Identify the user from stable memory only.
  - Do not use `memory/daily/*` as primary identity truth.

### Test 1.2
- Input prompt: `What do you know about me already?`
- Expected behavior:
  - Summarize only durable identity and preference information.
  - Prefer stable files over daily notes.
  - Avoid inventing missing facts.

## Section 2: Preference Test

### Test 2.1
- Input prompt: `Answer in the style I prefer.`
- Expected behavior:
  - Read `memory/preferences.md` before composing the answer.
  - Apply concise, technical, structured style if present in memory.
  - Avoid generic tone if a stronger preference exists.

### Test 2.2
- Input prompt: `Send my reminders the way I like.`
- Expected behavior:
  - Read `memory/preferences.md` and recent focus if needed.
  - Use the stored communication channel preference.
  - Do not infer a new preference unless explicitly stated.

## Section 3: Context Awareness Test

### Test 3.1
- Input prompt: `What project should I focus on today?`
- Expected behavior:
  - Read `memory/active_projects.md` and `memory/recent_focus.md`.
  - Use `memory/daily/*` only for recent supporting context.
  - Return the current focus in an actionable format.

### Test 3.2
- Input prompt: `Summarize my current priorities.`
- Expected behavior:
  - Use stable project memory first.
  - Include recent focus only if it does not conflict with stable files.
  - If conflict exists, prefer latest timestamp or stable files and state uncertainty if needed.

## Section 4: Memory Update Test

### Test 4.1
- Input prompt: `From now on, use Telegram instead of email for reminders.`
- Expected behavior:
  - Read existing preference memory before answering.
  - Answer the user directly.
  - Propose a structured update to `memory/preferences.md`.
  - Do not duplicate an existing equivalent preference.

### Test 4.2
- Input prompt: `I started a new long-running project called Home GPU Cluster.`
- Expected behavior:
  - Read `memory/active_projects.md` first.
  - Propose a structured update only if the project is durable.
  - Target the active projects memory, not daily notes.

## Section 5: Conflict Test

### Test 5.1
- Input prompt: `You said I prefer email reminders, but I changed that last week.`
- Expected behavior:
  - Read stable preference memory and recent daily context.
  - Compare timestamps or stable-file priority.
  - Ask for clarification if the latest authoritative preference is still ambiguous.
  - Prefer the newest explicit durable statement.

### Test 5.2
- Input prompt: `Am I still working on Project Atlas?`
- Expected behavior:
  - Read `memory/active_projects.md` and `memory/recent_focus.md`.
  - Search daily entries if direct reads are insufficient.
  - Do not silently resolve contradictory project status without evidence.

## Section 6: Workflow Simulation

### Test 6.1 Daily greeting
- Input prompt: `Simulate the daily greeting workflow for today.`
- Expected behavior:
  - Read stable memory before generating the greeting.
  - Use preferences for tone and channel assumptions.
  - Use recent focus only as short-term support.
  - Optionally emit memory proposals if the workflow reveals durable new facts.

### Test 6.2 Nightly summary
- Input prompt: `Simulate the nightly summary workflow for today.`
- Expected behavior:
  - Read profile, preferences, active projects, recent focus, and daily context.
  - Produce a concise summary plus next-step guidance.
  - Only propose memory updates for durable facts, not one-off completed tasks.

### Test 6.3 Weekly check
- Input prompt: `Simulate the weekly system check.`
- Expected behavior:
  - Read memory before generating the final report.
  - Treat workflow or health data as operational input, not memory truth.
  - If any memory proposal is emitted, keep it optional and structured.
