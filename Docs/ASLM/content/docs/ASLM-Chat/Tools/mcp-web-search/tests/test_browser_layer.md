---
title: "test_browser_layer"
draft: false
---

## Module `test_browser_layer`

`Tools/mcp-web-search/tests/test_browser_layer.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_identity_checkpoint_and_latest_good(tmp_path) -> None`

#### `def test_identity_prune_keeps_newest_good(tmp_path) -> None`

#### `def test_identity_rotate_burns_latest_and_falls_back(tmp_path) -> None`

#### `def test_identity_rotate_with_no_fallback_returns_none(tmp_path) -> None`

#### `def test_identity_cookie_header_is_host_scoped(tmp_path) -> None`

#### `def test_browser_section_defaults() -> None`

#### `def test_browser_config_validates_enums(tmp_path) -> None`

#### `def test_client_off_returns_unavailable() -> None`

#### `def test_client_warm_dispatches_to_daemon() -> None`

#### `def test_client_warm_unreachable_is_unavailable_not_crash() -> None`

#### `def test_client_autostart_spawns_daemon_when_unreachable(monkeypatch) -> None`

#### `def test_client_no_autostart_when_disabled(monkeypatch) -> None`

---

## Related

- [tests/_index](../_index/)
