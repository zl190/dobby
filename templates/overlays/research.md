# Research Overlay

Append this to CLAUDE.md for research projects (papers, experiments, publications).

---

## Project Lifecycle (Phases 4–7)

Phases 1–3 (Vision, Infrastructure, Agent Team) are in the base template. This overlay covers the research-specific phases.

### Phase 4: Design Experiments

Before running anything, answer three questions:
1. **What claim does this experiment support?** If you can't name the claim, don't run the experiment.
2. **What would falsify it?** If nothing could falsify it, it's not an experiment.
3. **What's the minimum sample size?** Don't over-collect. Design for the effect size you need.

**Pre-flight gate (Research Methodologist):** Before spending API budget, pass your design through an advisory agent: "What am I actually measuring? What are the threats to validity?" This catches design flaws before they become expensive mistakes.

**Pre-registration:** Commit your design (hypotheses, conditions, sample sizes, analysis plan) to git BEFORE running. Deviations are fine — but they must be transparently reported. Pre-registration is credibility infrastructure.

### Phase 5: Inner Loop (Experiment → Feedback)

```
Write/Edit → Blind Review → Analyze Gaps → Fix → Blind Review
```

**The governing law: claims-evidence ratio.** The single most predictive variable of evaluation score. When claims exceed evidence, score drops. When evidence exceeds claims, score rises. The optimal point: claim exactly what your evidence supports. Both overclaiming and over-hedging are failure modes.

**Study your evaluator first.** Before optimizing, understand what the evaluator rewards and penalizes. Spend 30 minutes studying the evaluation criteria and prior evaluations before your first iteration. The evaluator's rubric IS the objective function.

**Reframing > new evidence.** Sometimes the data is right but the story is wrong. Before collecting new evidence, ask: "Can I tell a better story with what I already have?" A reframe can move the score significantly with zero new data.

**The v10b principle.** Fewer changes beat more changes. 5 surgical edits that address the binding constraint outperform 20 comprehensive changes. Before each iteration: "What is the ONE binding constraint?" Fix that. Nothing else.

**Reset to peak.** When the current version scores >0.3 below the historical best: stop iterating forward. Go back to the peak version and apply only validated learnings.

### Phase 6: Outer Loop (Result → Audit)

```
Accumulate versions → Claims audit → Score trajectory → Strategy decision
```

**Claims audit (Research Methodologist Gate 2):** Before every major evaluation, pass the draft through: "Do my claims match my evidence? Any internal contradictions?" This catches logical gaps before reviewer attention.

**Score plateau detection.** If the score oscillates for 3+ consecutive versions:
1. You've hit a ceiling. More iterations of the same strategy won't break through.
2. Classify remaining issues: **cheap** (text edits) vs **hard** (new evidence, field data, infrastructure).
3. If all hard → stop iterating. Inform user. Pivot or accept ceiling.
4. If mixed → cheap gains ONLY in one surgical pass, then reassess.

**Parallel experiments when stuck.** Don't try one thing at a time. Run 2-3 variants simultaneously:
- Variant A: minimal fix (patch only new criticals)
- Variant B: cherry-pick from peak (best version + proven learnings only)
- Variant C: ambitious restructure (test whether ceiling is structural)

The variant that wins tells you what kind of problem you have.

**Strategy taxonomy.** Track strategy type + score delta + insight for every version. Over 5+ versions, this reveals which strategies reliably improve scores. Example:

| Strategy | Avg Δ | Lesson |
|---|---|---|
| Pure optimization (fix issues, no new content) | +0.3 | Most reliable |
| Consolidation (cut 25%, tighten) | +0.4 | Best when bloated |
| Targeted cherry-pick (few surgical edits) | +0.24 | Second best |
| Optimization + expansion | +0.2 | Risky — new attack surface |
| Pure expansion | 0.0 | Never improves score |
| Heavy formalization | -0.025 | Expansion disguised as optimization |
| Trimming (just cut) | -0.05 | Removes weakness AND substance |
| Evidence injection (external) | -0.1 | External evidence ≠ your own proof |

### Phase 7: Publish

- Final polish cycle: no new content, surgical fixes only (v10b strategy)
- Claims audit one final time
- Ensure all experiment data is archived and reproducible
- Pre-submission checklist: formatting, references complete, appendices cross-referenced, word/page limits

## Research Anti-Patterns

**Escape behavior.** The system generates increasingly elaborate strategies to avoid the hard problem — new frameworks, formalizations, literature surveys — anything except running the experiment. Detect by: 3+ iterations with flat scores despite increasing effort. Fix: name the hard problem. Do it or accept the ceiling.

**Hydra pattern.** Fixing one dimension breaks another. You add literature → paper gets long → clarity drops. Net: zero. Fix: consolidation before adding anything new.

**Honesty trap.** Over-hedging ("merely illustrative," "future work will determine...") invites the evaluator to demand the evidence you just disclaimed. Assert in results, hedge ONLY in limitations.

**Kitchen sink.** Adding everything to demonstrate effort. Each addition is individually defensible but collectively they bloat the artifact and dilute the core contribution.

**Expansion disguised as optimization.** Adding new content while claiming to fix existing issues. The tell: issue count stays the same despite "fixing" things.

## Research Agent Upgrades

When you hit the corresponding wall, add these research-specific agents:

| Wall | Agent | Role |
|---|---|---|
| "Don't know if my design is valid" | Research Methodologist (Gate 1) | Pre-experiment design review |
| "Don't know if my claims match evidence" | Research Methodologist (Gate 2) | Pre-review claims audit |
| "Need domain expertise I don't have" | Professor / Domain Expert | Strategic advisory, framing |
| "Need to explore the competitive landscape" | Ideation agent | Literature survey, gap analysis |

The Research Methodologist is one agent with two trigger gates — same critical-reading skill, different timing.
