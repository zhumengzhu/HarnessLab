# HarnessLab eval suite

YAML tasks under `eval/tasks/` drive the production `HarnessLoop` with
`ReplayModel` or `SimpleModel` inside an isolated temp workspace. Results
are compared to `eval/baseline.json` for regression detection.

## Running

```bash
uv run harnesslab eval                    # full suite vs baseline
uv run harnesslab eval --task 07_grep_then_edit
uv run harnesslab eval --update-baseline  # refresh baseline (reviewed commit)
uv run pytest tests/test_eval_tasks.py    # CI-style gate (all tasks must pass)
```

Exit codes: `0` ok, `2` task failure, `3` baseline regression.

## Adding a task

1. Add `eval/tasks/NN_name.yaml` (lexicographic `NN_` prefix = run order).
2. Prefer `decisions:` + `ReplayModel` for multi-step tool chains; use
   `/tool …` inputs with `SimpleModel` for parser-level smoke tests.
3. Set `turns[].max_steps` when one user message needs multiple inner
   steps (see `06_multi_step_tool_then_final.yaml`).
4. Optional `limits:` overrides `RuntimeLimits` for one task (e.g. low
   `compaction_threshold_tokens` in `08_compaction_on_threshold.yaml`).
5. Run `uv run harnesslab eval --update-baseline` in the same PR when
   metrics change intentionally.
6. Extend `tests/test_eval_tasks.py::test_shipped_tasks_cover_expected_paths`
   when the task guards a new code path.

## Propose → eval workflow

When `harnesslab propose` surfaces a recurring failure cluster:

1. **Reproduce** — capture a trace or minimal steps that trigger the failure.
2. **Codify** — add a YAML task that asserts the *correct* behavior (not
   the bug). Template kinds map to eval coverage:

   | propose kind | Typical eval task |
   |--------------|-------------------|
   | `policy_denial` | denied path / shell denylist tasks |
   | `invalid_args` | schema rejection task |
   | `tool_failure` | multi-step tool chain with `ok: true` |
   | `eval_regression` | fix loop; baseline already guards |

3. **Fix** — patch the loop/tools/policy; the new task must pass.
4. **Gate** — `uv run pytest` + `uv run harnesslab eval` before merge.
5. **Proposal status** — human moves the proposal to `accepted` or
   `rejected` (see `AGENTS.md`); agents do not auto-apply proposals.

## Shipped coverage (Phase 3.1)

| Task | Path exercised |
|------|----------------|
| `assistant_fallback` | SimpleModel final reply |
| `write_then_read` | file tools + two-turn session |
| `policy_denied_path` | workspace path policy |
| `invalid_args_schema` | tool args validation |
| `shell_denylist_blocks` | shell denylist |
| `multi_step_tool_then_final` | inner loop `max_steps` |
| `grep_then_edit` | Phase 2.5 search + edit |
| `compaction_on_threshold` | context compaction |
| `session_resume_second_turn` | session resume / turn index |
| `session_memory_persists` | session-scoped memory read/write |
