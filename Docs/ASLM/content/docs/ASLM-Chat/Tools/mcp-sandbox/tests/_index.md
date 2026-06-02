---
title: "tests"
draft: false
---

## Package `tests`

`Tools/mcp-sandbox/tests/` — Pytest coverage for workspace security, bash routing, Docker host, background jobs, intent classification, and line-edit feature integration.

`pytest.ini` configures discovery.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [conftest](conftest/) | `conftest.py` | Hermetic `HOST_WORKSPACE` fixture |
| [test_native_exec](test_native_exec/) | `test_native_exec.py` | Native bash exec |
| [test_snapshot_preflight](test_snapshot_preflight/) | `test_snapshot_preflight.py` | Snapshot preflight |
| [test_phase1_smoke](test_phase1_smoke/) | `test_phase1_smoke.py` | Cat/grep routing smoke |
| [test_workspace_cleanup_timing](test_workspace_cleanup_timing/) | `test_workspace_cleanup_timing.py` | Idle cleanup timing |
| [test_supervisor_simplified](test_supervisor_simplified/) | `test_supervisor_simplified.py` | Contract smoke |
| [test_host_proxy](test_host_proxy/) | `test_host_proxy.py` | Stdio proxy |
| [test_workspace_boundary](test_workspace_boundary/) | `test_workspace_boundary.py` | Path traversal |
| [test_container_retry](test_container_retry/) | `test_container_retry.py` | Container recovery |
| [test_job_cleanup](test_job_cleanup/) | `test_job_cleanup.py` | Background job cleanup |
| [security_test](security_test/) | `security_test.py` | Manual security checklist |
| [test_destructive_container_resilience](test_destructive_container_resilience/) | `test_destructive_container_resilience.py` | Stress recovery |
| [test_cwd_contract](test_cwd_contract/) | `test_cwd_contract.py` | Task cwd persistence |
| [test_config_validation](test_config_validation/) | `test_config_validation.py` | Host workspace validation |
| [test_session_state](test_session_state/) | `test_session_state.py` | Exploration state |
| [test_intent](test_intent/) | `test_intent.py` | Command classifier |
| [test_controller_presenters](test_controller_presenters/) | `test_controller_presenters.py` | Presenters + dispatch import |
| [test_rg_type_map](test_rg_type_map/) | `test_rg_type_map.py` | ripgrep type map |
| [test_api_bash_supervision](test_api_bash_supervision/) | `test_api_bash_supervision.py` | Large-file cat preview |
| [test_workspace_cleanup](test_workspace_cleanup/) | `test_workspace_cleanup.py` | Staging/recycle integration |
| [test_ps](test_ps/) | `test_ps.py` | Process listing |
| [test_v2_contracts](test_v2_contracts/) | `test_v2_contracts.py` | v2 response envelope |
| [feature_jobs_edit](feature_jobs_edit/) | `tests/feature_jobs_edit/` | Line edit and job routes |

---

## Related

- [mcp-sandbox](../_index/)
- [supervisor/sandbox/api](../supervisor/sandbox/api/)
