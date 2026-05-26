# HarnessLab eval suite

YAML tasks under `eval/tasks/` drive the production `HarnessLoop` with
`ReplayModel` or `SimpleModel` inside an isolated temp workspace. Results
are compared to `eval/baseline.json` for regression detection.

## Running

```bash
uv run harnesslab eval                    # full suite vs baseline
uv run harnesslab eval --skip-tags network  # CI / offline (skips wttr.in task)
uv run harnesslab eval --task 07_grep_then_edit
uv run harnesslab eval --update-baseline  # refresh baseline (reviewed commit)
uv run pytest tests/test_eval_tasks.py    # offline tasks (excludes network tag)
RUN_LIVE_EVAL=1 uv run pytest -m network  # optional live network tasks
RUN_DEEPSEEK_LIVE=1 DEEPSEEK_API_KEY=... uv run pytest tests/manual/test_deepseek_live.py -m network
```

Set ``HARNESSLAB_LOG=INFO`` and pytest ``-s`` to see live diagnostics (**stderr**, not stdout).

Exit codes: `0` ok, `2` task failure, `3` baseline regression.

## Optional live lanes (not in CI)

| Lane | Env | What it exercises |
|------|-----|-------------------|
| Eval network tasks | `RUN_LIVE_EVAL=1` | wttr.in fetch (`fetch_url_weather`) |
| DeepSeek provider | `RUN_DEEPSEEK_LIVE=1` + `DEEPSEEK_API_KEY` | Real `deepseek-v4-flash`: thinking disabled/enabled smoke only (no tool tests) |

CI runs `pytest -m "not network"` and `eval --skip-tags network` only.

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

## Shipped coverage (Phase 3.1+)

Fifteen tasks in `eval/baseline.json`. Task `fetch_url_weather` is tagged
``network`` and skipped by default in CI (`--skip-tags network` /
`pytest -m "not network"`). Optional live lane: ``RUN_LIVE_EVAL=1 pytest -m network``.

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
| `apply_patch_unified_diff` | unified-diff patch tool |
| `fetch_url_weather` | allowlisted HTTP fetch (wttr.in); tag: ``network`` |
| `shell_profile_strict` | named shell profile denies dev runners |
| `workspace_memory_persists` | workspace memory across sessions |
| `plan_then_execute` | non-terminal `plan` decision + `plan_emitted` |
