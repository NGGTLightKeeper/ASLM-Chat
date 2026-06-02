---
title: "feature_jobs_edit"
draft: false
---

## Package `feature_jobs_edit`

`Tools/mcp-sandbox/tests/feature_jobs_edit/` — Integration tests for line edit, job registry, and background bash routes.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [helpers](helpers/) | `helpers.py` | `reset_task_root` test fixture |
| [test_line_edit_core](test_line_edit_core/) | `test_line_edit_core.py` | Core line edit |
| [test_line_edit_anchor](test_line_edit_anchor/) | `test_line_edit_anchor.py` | Anchor mismatch |
| [test_line_edit_api](test_line_edit_api/) | `test_line_edit_api.py` | API-level line edit |
| [test_job_bash_routes](test_job_bash_routes/) | `test_job_bash_routes.py` | Bash job commands |
| [test_job_registry](test_job_registry/) | `test_job_registry.py` | `JOB_REGISTRY` |
| [test_background_policy](test_background_policy/) | `test_background_policy.py` | Background mode policy |
| [test_native_background](test_native_background/) | `test_native_background.py` | Native runtime background |
| [test_docker_background](test_docker_background/) | `test_docker_background.py` | Docker runtime background |
| [test_smoke](test_smoke/) | `test_smoke.py` | Feature smoke |

---

## Related

- [tests/_index](../_index/)
