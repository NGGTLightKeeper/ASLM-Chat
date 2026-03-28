---
title: "CAPTCHA and Blocker Recovery"
domain: browser-automation
trigger: "Browser encounters a CAPTCHA, login wall, or persistent overlay that blocks progress"
tools: [browser_navigate, browser_snapshot, browser_click, browser_wait_for_user]
related_guides: [mcp-browser-agent]
difficulty: easy
---

## Goal

Recover from page blockers (CAPTCHA, login, overlays) by delegating to the user when needed.

## When to use

- Snapshot shows a CAPTCHA warning (reCAPTCHA, hCaptcha, Cloudflare, Turnstile)
- Snapshot shows a login wall (password input detected)
- Snapshot shows an overlay warning that auto-dismiss failed to close
- A page interaction is blocked and cannot proceed

## When NOT to use

- The overlay was auto-dismissed successfully -- just continue
- The page loaded normally without warnings -- just interact

## Workflow

### CAPTCHA detected

```text
browser_wait_for_user("Please solve the CAPTCHA on the page", timeout_seconds=60)
```

After the wait, a fresh full snapshot is returned. Check if the CAPTCHA is resolved.
If still present -- report to user that manual intervention is needed.

### Login wall detected

```text
browser_wait_for_user("Please log in with your credentials", timeout_seconds=90)
```

Do not attempt to guess or type credentials unless the user explicitly provides them.

### Persistent overlay

First try to close it:

```text
browser_click("e15")  -- close button ref from snapshot
```

If no close button is visible or click did not work:

```text
browser_wait_for_user("Please close the popup manually")
```

### After recovery

Always check the fresh snapshot before continuing:
- Is the blocker gone?
- Are the expected page elements now visible?
- If yes -- continue with the original task
- If no -- report the blocker and stop

## Stop conditions

- Blocker resolved and page is interactive
- Or: user could not resolve the blocker -- stop and report

## Anti-patterns

- Using `browser_click` on a CAPTCHA (it cannot be clicked through)
- Calling `browser_wait_for_user` before `browser_navigate` (no page is open)
- Attempting to bypass auth programmatically
- Continuing interaction without checking if the blocker is actually resolved
- Retrying the same recovery method more than twice
