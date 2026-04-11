---
title: "SPA and Dynamic Site Interaction"
domain: browser-automation
trigger: "User needs to interact with a JavaScript-heavy page, SPA, or dynamic web application"
tools: [browser_navigate, browser_snapshot, browser_click, browser_type]
related_guides: [mcp-browser-agent]
difficulty: medium
---

## Goal

Navigate and interact with a dynamic web page using accessibility-based element refs.

## When to use

- The page requires JavaScript to render content
- The page is a SPA (Single Page Application)
- Content loads dynamically (infinite scroll, lazy load, AJAX)
- `read_page` returns incomplete or empty content

## When NOT to use

- The page is static and readable -- use `read_page`
- You need to download a file -- use `import_web_file` or `curl`
- You need to inspect a GitHub repo -- use `bash("git clone ...")`

## Workflow

### Step 1 -- Navigate

```text
browser_navigate("https://target-site.com/page")
```

Read the full snapshot: URL, title, page situation warnings, interactive elements.

### Step 2 -- Check for blockers

If snapshot shows:
- CAPTCHA -- go to `browser_wait_for_user("Please solve the CAPTCHA")`
- Login wall -- go to `browser_wait_for_user("Please log in")`
- Overlay -- try `browser_click(ref)` on close button first

### Step 3 -- Interact

Use refs from the latest snapshot:

```text
browser_click("e3")
browser_type("e7", "search query", press_enter=true)
```

After each action, read the new compact snapshot for updated refs.

### Step 4 -- Get full context when needed

If you need the complete accessibility tree after a series of compact actions:

```text
browser_snapshot()
```

To scroll and reveal more content:

```text
browser_snapshot(scroll="down", amount=800)
```

### Step 5 -- Extract information

Read the accessibility tree text content from snapshots.
If text is missing (canvas, iframe, CSS-hidden):

```text
browser_screenshot()
read("_in/screenshot_<ts>.png")  -- in sandbox
```

## Stop conditions

- The needed information is extracted from the page
- The desired interaction (form submit, button click) is confirmed
- Or: the page is blocked (CAPTCHA unsolved, auth required) -- report and stop

## Anti-patterns

- Using refs from a previous snapshot (they expire every action)
- Inventing refs that never appeared in output
- Calling `browser_click` multiple times for batch operations (use `refs: [...]`)
- Using browser tools when `read_page` would work
- Forgetting to check page situation warnings before interacting
