```
     _       _     _
  __| | ___ | |__ | |__  _   _
 / _` |/ _ \| '_ \| '_ \| | | |
| (_| | (_) | |_) | |_) | |_| |
 \__,_|\___/|_.__/|_.__/ \__, |
                          |___/
```

# Dobby

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange.svg)](https://docs.anthropic.com/en/docs/claude-code)
[![Discord](https://img.shields.io/badge/Discord-bot-5865F2.svg?logo=discord&logoColor=white)](notify/adapters/discord.py)
[![Slack](https://img.shields.io/badge/Slack-bot-4A154B.svg?logo=slack&logoColor=white)](notify/adapters/slack.py)
[![Tests: 14/14](https://img.shields.io/badge/tests-14%2F14-brightgreen.svg)](smoke.py)

Give it a task. Go do something else. It'll ask if it needs you.

---

## What it does

- **Runs Claude agents in background tmux sessions** -- hand off a task and keep working.
- **HITL relay** -- the agent can ask you a question mid-task, block until you answer, then continue.
- **Convergence loops** -- production agent builds, quality agent evaluates (blind, isolated), orchestrator decides: iterate or ship. Automated quality improvement with score tracking.
- **Multi-agent teams** -- decompose multi-domain requests into subtasks, match to roster roles, launch agents in parallel.
- **Dynamic agent growth** -- detects plateaus and bottlenecks, spawns advisory agents when stuck.
- **Budget enforcement** with cost tracking per agent, per iteration, per task.

## Quick start

```bash
git clone https://github.com/zl190/dobby.git ~/.claude/skills/dobby

# In any project directory:
/dobby "build a REST API with auth"
```

That's it. The agent launches in a tmux session. You'll be notified when it finishes -- or when it has a question for you.

## How the HITL relay works

This is the part that matters. When a background agent gets stuck on a decision it can't make alone, the relay kicks in:

```
Agent                          Orchestrator                   You
  |                                |                            |
  |-- writes QUESTION.md -------->|                            |
  |-- signals via tmux ---------->|                            |
  |   (blocks, waiting)           |-- reads question --------->|
  |                                |   "SQLite or Postgres?"   |
  |                                |                            |
  |                                |<-- you answer: "SQLite" --|
  |                                |-- writes ANSWER.md        |
  |   <-- signals back ------------|                            |
  |   reads answer, continues      |                            |
```

The agent does not poll. It does not guess. It waits for you, gets the answer, and keeps going.

## Commands

| Command | Description |
|---|---|
| `/dobby <request>` | Give Dobby a task |
| `/dobby --role <slug> <request>` | Use a specific roster role |
| `/dobby --converge <request>` | Run with convergence loop (build, evaluate, fix) |
| `/dobby status` | Show all tasks and progress |
| `/dobby progress <task-name>` | Live progress bar for a task |
| `/dobby notify` | Show notification config status |
| `/dobby stop <task-name>` | Stop a running task |
| `/dobby deliver <task-name>` | Read output and present results |
| `/dobby roster` | Show project agent roster |
| `/dobby roster init` | Create a starter roster config |

## Team mode

When your request spans multiple domains, Dobby assembles a team:

```
/dobby "build a REST API and write documentation for it"
```

Dobby decomposes this into subtasks, matches each to a roster role, and launches agents in parallel:

```
Dobby team assembled for: build a REST API and write documentation for it
  - build-api (Builder, $5) → .dobby/build-api/output/
  - write-docs (Writer, $8) → .dobby/write-docs/output/
```

Each agent works independently in its own tmux session. They can read each other's `output/` directories for coordination. When all agents finish, you get a combined cost report and deliverables summary.

## Convergence loop

The differentiator. When a task needs quality, Dobby runs an automated produce-evaluate-fix cycle:

```
/dobby --converge "write a research proposal on LLM evaluation"
```

```
Iteration 1:
  Production agent writes draft v1 → output/
  Quality agent evaluates (blind, isolated) → score: 6.5/10
    Issues: "Claims exceed evidence", "Missing related work"
  Orchestrator: score < 8, iterating...

Iteration 2:
  Production agent reads feedback, fixes issues → v2
  Quality agent evaluates (fresh context, no prior scores) → score: 7.8/10
    Issues: "Methodology section thin"
  Orchestrator: score < 8, iterating...

Iteration 3:
  Production agent addresses methodology → v3
  Quality agent evaluates → score: 8.4/10
  Orchestrator: score >= 8, shipping.

Dobby has finished: research-proposal (converged in 3 iterations)
Score trajectory: v1=6.5 → v2=7.8 → v3=8.4
Total cost: $4.20 (3 production + 3 quality evaluations)
```

**Quality isolation is real.** The quality agent runs in a temp directory with only the deliverable and rubric. It cannot see prior scores, version history, or the vision statement. This prevents anchoring bias -- the evaluator judges the artifact on its own merit, not relative to what came before.

**Bottleneck detection is automatic.** If scores plateau for 3 iterations, Dobby spawns an advisory agent to diagnose the binding constraint. If the advisory says "structural problem," Dobby launches parallel variant experiments.

## What's included

```
~/.claude/skills/dobby/
  SKILL.md          # The protocol -- routing, scaffolding, convergence, HITL, completion
  smoke.py          # Tests (14 tests: bootstrap through bot completion)
  progress.py       # Live progress bar (filesystem phase detection)
  notify/           # Slack/Discord webhook notifications (zero dependencies)
  templates/        # VP architecture templates (research + company overlays)
  install.sh        # One-line installer
```

## Agent roster

Projects can predefine named agent roles in `.dobby/roster-config.md`. Each role carries a model, budget cap, keyword hints for auto-matching, and a description injected into the agent's instructions.

```bash
# Create a starter roster:
/dobby roster init

# Use a specific role:
/dobby --role researcher "survey the state of WebSocket libraries in Python"
```

Default roles: Builder, Reviewer, Researcher, Writer. Edit the config to fit your project.

## Requirements

- **Claude Code CLI** (`claude` command available)
- **tmux**
- **uv** (for Python scripts: progress bar, notifications, tests)

## How it works

```
/dobby "task"
   |
   classify (quick / task / project / multi-domain)
   |
   ├── single-shot (project, default):
   |   scaffold → launch agent → wait → report
   |
   ├── convergence (--converge or quality signals):
   |   scaffold → loop:
   |     production agent builds → quality agent evaluates (isolated)
   |     → orchestrator decides: iterate or ship
   |     → if plateau: spawn advisory agent
   |   → report with score trajectory
   |
   └── team (multi-domain):
       decompose → match roles → launch N agents in parallel
       → wait for all → combined report
   |
   all modes:
       question? --> relay to user --> relay answer back
       done?     --> report cost + deliverables
```

Routing is lightweight by default. Quick questions get answered inline. Medium tasks use Claude's Task tool. Only substantial work gets a background agent. Convergence mode activates automatically for $20+ tasks or on request.

**Note on permissions:** Background agents run with `--dangerously-skip-permissions` for autonomy. Each task's CLAUDE.md instructs the agent to write only to its `output/` directory, but this is a convention, not a hard sandbox.

## What Dobby does differently

A single skill file (~650 lines of protocol) that gives you:
- **HITL relay** -- background agents can block-wait for your input mid-task
- **Automated convergence loops** -- produce → evaluate (blind) → fix → repeat until quality threshold
- **Quality isolation** -- evaluation agents run in temp directories with no access to prior scores or vision
- **Multi-agent teams** -- decompose requests, match to roster roles, launch in parallel
- **Bottleneck detection** -- detects score plateaus, spawns advisory agents

It ships as a Claude Code skill -- no framework, no runtime, no dependencies beyond tmux and uv.

## Notifications

Dobby can push to Slack and/or Discord when agents finish or need help:

```bash
export DOBBY_SLACK_WEBHOOK="https://hooks.slack.com/services/T.../B.../xxx"
# or
export DOBBY_DISCORD_WEBHOOK="https://discord.com/api/webhooks/123456/abcdef"
```

That's it. Dobby notifies on: task completed, agent has a question, convergence score update, team finished, command launched. Zero extra dependencies -- uses `curl` under the hood.

### Two-way bot (answer questions from Slack/Discord)

```bash
# Slack: create an app at api.slack.com, enable Socket Mode
export DOBBY_SLACK_BOT_TOKEN="xoxb-..."
export DOBBY_SLACK_APP_TOKEN="xapp-..."
export DOBBY_SLACK_CHANNEL="#dobby"

# Discord: create an app at discord.com/developers
export DOBBY_DISCORD_BOT_TOKEN="MTIz..."
export DOBBY_DISCORD_CHANNEL_ID="123456"

# Install the SDK you need (only the one you use):
pip install slack-sdk    # for Slack
pip install discord.py   # for Discord
```

When an agent asks a question, Dobby posts it to your channel. Reply in the thread (Slack) or reply to the message (Discord) -- the agent gets your answer and continues. You can also answer in the terminal. First answer wins.

### Remote control (launch tasks from Slack/Discord)

Start the relay daemon with command mode enabled:

```bash
cd /path/to/project
SKILL_DIR="$(readlink -f ~/.claude/skills/dobby)"
uv run "${SKILL_DIR}/notify/relay.py" daemon --enable-commands &
```

Then type in your Slack/Discord channel:

```
dobby build a REST API with tests
```

Dobby launches a tmux session on your dev machine and posts a confirmation. Completion notifications, question relay, and cost reports all flow back through the same channel.

**Access control:** Set platform-specific env vars to restrict who can trigger commands and answer questions:

```bash
export DOBBY_SLACK_AUTHORIZED_USERS="U01ABC,U02DEF"      # Slack user IDs
export DOBBY_DISCORD_AUTHORIZED_USERS="123456789,987654"  # Discord user IDs
```

Without these, any channel member can launch tasks and answer questions. Commands and answers from channels other than the configured `DOBBY_SLACK_CHANNEL` / `DOBBY_DISCORD_CHANNEL_ID` are ignored.

## License

MIT License. See [LICENSE](LICENSE).
