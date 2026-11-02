# Evals for draft_units, generate_similar, link_question (T9.7)

Runner: `evals/framework` (JSONL cases, per-run cost ceiling, per-case exception capture,
Markdown report). CI uses the fake provider only.

## Labels from learner edits

Export from the core-api database (only accounts with `eval_consent_at`, ADR-0010):

    python -m core_api.cli_export_eval --kind unit-edits --out edits.jsonl

Each line holds `rev0` (the AI draft), `rev1` (the learner's edit) and the `anchors` quotes.
Turn a line into a `draft_units` case: `expected` = one `{"quote": ...}` per kept card, taken
from `rev1` anchors. Keep the file out of git (learner text).

## Run

    python -m evals.framework.cli --suite draft_units            # fake provider, harness check
    ANTHROPIC_API_KEY=... python -m evals.framework.cli --suite draft_units \
        --provider anthropic --max-cost-usd 0.20                 # by hand, never in CI

Never run the real command casually: the whole MVP AI budget is 2 USD. The report goes to
`evals/<suite>/out/report.md` (gitignored); the orchestrator copies the one worth keeping to
`docs/evals/` (separate repo).

## Thresholds

Per task, in the suite's `thresholds` and the report table; all `None` ("unset") until the
first real data exists. Set them in the suite when the first real run is read.

## Sample reports (fake provider, harness check only)

```markdown
# draft_units eval report

- provider: fake, model: fake-grader-v1
- cases: 3, run: 3
- cost: $0.000000
- provider fake: checks the harness only, says nothing about model quality

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Cases hit | 66.7% | - | - |
| precision | 100.0% | unset (to be set when the first data exists) | n/a |
| recall | 75.0% | unset (to be set when the first data exists) | n/a |

Errors (counted as a miss): 0.

## Missed cases

- du-notes-only
```

```markdown
# generate_similar eval report

- provider: fake, model: fake-grader-v1
- cases: 3, run: 3
- cost: $0.000000
- provider fake: checks the harness only, says nothing about model quality

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Cases hit | 100.0% | - | - |
| leak_free | 100.0% | unset (to be set when the first data exists) | n/a |
| status | 100.0% | unset (to be set when the first data exists) | n/a |

Errors (counted as a miss): 0.

## Missed cases

- none
```

```markdown
# link_question eval report

- provider: fake, model: fake-grader-v1
- cases: 2, run: 2
- cost: $0
- provider fake: checks the harness only, says nothing about model quality

| Metric | Value | Threshold | Status |
|---|---|---|---|
| Cases hit | 0.0% | - | - |
| precision | n/a | unset (to be set when the first data exists) | n/a |
| recall | n/a | unset (to be set when the first data exists) | n/a |

Errors (counted as a miss): 2.

## Missed cases

- lq-one
- lq-two
```

