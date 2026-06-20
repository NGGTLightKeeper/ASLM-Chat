---
title: "stackoverflow"
draft: false
---

## Module `stackoverflow`

`Tools/mcp-web-search/core/ddgs/engines/stackoverflow.py` — ASLM Chat Python module.

---

## Classes

### `class StackOverflow(BaseSearchEngine[TextResult])`

Specialist engine for programming questions. It inherits from `BaseSearchEngine` and interacts with the Stack Exchange API.

#### Methods

- `def __init__(self, proxy: str | None = None, timeout: int | None = None, *, verify: bool | str = True) -> None`
  Initializes the StackOverflow engine with optional proxy, timeout, and verification settings.
- `def request(self, method: str, url: str, **kwargs: Any) -> str`
  Uses the JSON API transport (via `curl_cffi`) instead of the generic HTML engine client. It explicitly handles HTTP 429 status codes and specific error messages ("too many requests", "temporarily rate limited", "unusually high number of requests") by raising a `RatelimitException` instead of a generic `DDGSException`.

---

## Related

- [engines/_index](../_index/)
