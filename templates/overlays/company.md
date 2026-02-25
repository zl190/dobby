# Company Overlay

Append this to CLAUDE.md for engineering/product projects (software, systems, deployments).

---

## Project Lifecycle (Phases 4–7)

Phases 1–3 (Vision, Infrastructure, Agent Team) are in the base template. This overlay covers the engineering-specific phases.

### Phase 4: Design Work

Before building, answer three questions:
1. **What's the acceptance criteria?** If you can't write a test for it, you can't build it.
2. **What's the smallest shippable unit?** Don't design the whole system. Design the first increment that delivers value.
3. **What breaks if this goes wrong?** Understand blast radius before writing code.

**Sprint/milestone structure:** Break work into time-boxed increments. Each increment has: scope (what to build), acceptance criteria (how to verify), and a demo (what to show). The milestone tracker in the state file replaces the version registry — track scope, completion %, blockers, and cycle time.

**Architecture decision records (ADRs):** For non-trivial decisions (framework choice, data model, API design), write a one-paragraph ADR in the decision log: context, decision, consequences. Future you (or the next session after compaction) needs to know WHY, not just WHAT.

### Phase 5: Inner Loop (Build → Test → Fix)

```
Write code → Run tests → Fix failures → Run tests → Code review → Merge
```

**Tests are the quality agent.** In a research project, the blind reviewer is the evaluator. In engineering, the test suite is. Treat test results with the same analytical rigor: which tests failed, why, what's the binding constraint, what's the minimum fix.

**The v10b principle applies to code too.** The minimum diff that fixes the failing test is the optimal diff. Don't refactor adjacent code, don't add "while I'm here" improvements, don't upgrade dependencies. Fix the thing. Ship it. Come back for cleanup in a separate pass.

**CI/CD as the outer quality gate.** Every push triggers: lint → unit tests → integration tests → build. If CI fails, fix it before doing anything else. A broken pipeline blocks the entire team (even if the team is just you and your agents).

**Code review protocol:**
- Production agent writes code
- SDE agent reviews (architecture, patterns, security)
- Quality agent runs tests (automated, not subjective)
- All three must pass before merge

### Phase 6: Outer Loop (Release → Verify → Monitor)

```
Feature complete → Staging deploy → QA/security audit → Production deploy → Monitor
```

**Staging is your claims audit.** Just as a research project audits "do claims match evidence," staging audits "does the feature work in a realistic environment." Don't skip staging because it worked locally.

**Security audit before production.** Run OWASP checks, dependency vulnerability scans, and access control review before any production deployment. This is non-negotiable — a security incident is more expensive than a delayed launch.

**Monitoring as ongoing evaluation.** After deploy, watch: error rates, latency percentiles, resource consumption. Set alerts for anomalies. The deploy isn't done until you've confirmed it's stable in production for 24 hours.

**Rollback plan.** Before every production deploy, document: how to roll back, what data migrations need reversing, who to notify. If you can't roll back, you can't ship.

### Phase 7: Ship

- Release notes: what changed, what to watch, known issues
- Documentation updates: API docs, README, architecture diagrams
- Stakeholder notification: changelog, demo, migration guide if needed
- Post-mortem if anything went wrong: what happened, why, what we changed to prevent recurrence

## Engineering Anti-Patterns

**Premature optimization.** Optimizing code that isn't the bottleneck. Profile first, then optimize. The fastest code is the code you don't write.

**Scope creep.** "While I'm here, let me also..." is how a 2-hour task becomes a 2-day task. Each addition is individually reasonable but collectively they destroy cycle time. Scope is a budget — every addition requires a subtraction.

**Tech debt accumulation.** Shipping fast by skipping tests, hardcoding values, copy-pasting instead of abstracting. Each shortcut is a loan with interest. Track tech debt explicitly in the backlog with estimated payoff cost.

**Gold plating.** Making it perfect when good enough ships. The user asked for a button that saves data. They didn't ask for undo, auto-save, conflict resolution, and offline support. Ship the button. Add features when users ask for them.

**Configuration over convention.** Making everything configurable "for flexibility." Most configuration is never changed. Pick sensible defaults. Only make things configurable when you have evidence that different users need different values.

## Engineering Agent Upgrades

When you hit the corresponding wall, add these engineering-specific agents:

| Wall | Agent | Role |
|---|---|---|
| "Tests pass but the architecture is wrong" | SDE / Architect | Code review, pattern enforcement |
| "Deploys keep breaking" | DevOps agent | CI/CD pipeline, infrastructure as code |
| "Security vulnerabilities keep appearing" | Security Scanner | OWASP checks, dependency audit |
| "Can't keep up with bug reports" | QA / Triage agent | Bug reproduction, priority classification |

## Engineering Metrics to Track

| Metric | What It Measures | Target |
|---|---|---|
| Cycle time | Commit to production | < 1 day for small changes |
| Test coverage | % of code paths tested | > 80% for critical paths |
| CI pass rate | % of pushes that pass CI | > 95% |
| Mean time to recovery | How fast you fix production issues | < 1 hour |
| Deployment frequency | How often you ship | Daily or better |
