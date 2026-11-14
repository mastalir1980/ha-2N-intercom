---
id: TASK-80
title: >-
  E2E pipeline unit stage fails in a fresh venv: test_blueprint needs Jinja2
  that e2e.sh setup does not install
status: To Do
assignee: []
created_date: '2026-11-13 19:42'
labels:
  - e2e
  - env
dependencies: []
references:
  - e2e/e2e.sh
  - e2e/run.sh
  - tests/requirements.txt
  - tests/test_blueprint.py
  - README.md
priority: medium
type: bug
ordinal: 84000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The local E2E pipeline (`e2e/e2e.sh wip` / `run`) fails in stage `unit` before anything is deployed, so no E2E test runs. Classification: environment / pipeline tooling, not an integration bug.

Current behaviour: `e2e/run.sh` runs the unit suite with the E2E venv (`PY="$E2E_DIR/.venv/bin/python"`, e2e/run.sh:33 and :52). `e2e/e2e.sh setup` builds that venv from `e2e/requirements.txt` only (e2e/e2e.sh:26-27: pytest, requests, websocket-client). `tests/test_blueprint.py:8-10` (added in TASK-55) imports `jinja2` and `yaml`, which are declared only in `tests/requirements.txt` (Jinja2>=3.1, PyYAML>=6.0). In a venv created by `e2e.sh setup` (for example in a new task worktree) the module cannot be imported and the whole pipeline stops.

Expected behaviour: a venv created by `e2e.sh setup` can run the full unit suite; the unit stage of the pipeline is green on a clean checkout/worktree without manual `pip install`.

Evidence (report e2e/reports/20261113-204130, trigger manual, ref worktree, failed_stage unit; branch task-12 on top of 1914bd1):
```
ERROR: test_blueprint (unittest.loader._FailedTest.test_blueprint)
ImportError: Failed to import test module: test_blueprint
  File "tests/test_blueprint.py", line 8, in <module>
    from jinja2 import StrictUndefined
ModuleNotFoundError: No module named 'jinja2'
Ran 845 tests in 41.375s
FAILED (errors=1)
```
All other 844 tests passed; the failure is unrelated to the change under test. No context.json exists because the run stopped before deploy (HA version and intercom firmware not involved).

Suspected location: e2e/e2e.sh:27 (setup installs only e2e/requirements.txt); alternatively e2e/run.sh:52 could verify the test requirements before the unit stage. README.md:752-757 already documents `pip install -r tests/requirements.txt` for manual runs.

Workaround: `e2e/.venv/bin/pip install -r tests/requirements.txt` in the affected checkout.
Reproduce: fresh worktree, `bash e2e/e2e.sh setup`, then `bash e2e/e2e.sh wip`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `bash e2e/e2e.sh setup` installs `tests/requirements.txt` into the E2E venv in addition to `e2e/requirements.txt` [unit]
- [ ] #2 In a venv created only by `e2e.sh setup`, `python -m unittest discover -s tests -t tests` imports `tests/test_blueprint.py` and the unit stage of `e2e/run.sh` passes [jan]
- [ ] #3 When a unit-test dependency is missing, the pipeline unit stage fails with a message that names the missing requirements file and the install command, not only an ImportError inside unit.log [unit]
- [ ] #4 `e2e/README.md` setup section mentions that the E2E venv also carries the unit-test requirements [unit]
<!-- AC:END -->
