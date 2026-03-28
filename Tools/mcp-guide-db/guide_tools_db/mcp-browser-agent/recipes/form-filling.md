---
title: "Form Filling and Submission"
domain: browser-automation
trigger: "User needs to fill out a web form, submit data, or complete a multi-step form flow"
tools: [browser_navigate, browser_snapshot, browser_click, browser_type]
related_guides: [mcp-browser-agent]
difficulty: medium
---

## Goal

Fill out a web form and submit it using accessibility-based refs.

## When to use

- User asks to fill out a form on a specific page
- User provides data to enter into form fields
- Multi-step form (wizard) needs to be completed

## When NOT to use

- The form requires login credentials the user has not provided -- stop and ask
- The form submits payment or commits to a binding action -- confirm with user first

## Workflow

### Step 1 -- Navigate to the form

```text
browser_navigate("https://site.com/form-page")
```

Read the snapshot to identify form fields and their refs.

### Step 2 -- Identify fields

From the interactive elements list, locate:
- Text inputs (textbox refs)
- Dropdowns (combobox refs)
- Checkboxes / radio buttons
- Submit button

### Step 3 -- Fill fields in order

```text
browser_type("e5", "John Doe")
browser_type("e8", "john@example.com")
```

For dropdowns and selects:
```text
browser_click("e12")  -- open dropdown
browser_click("e15")  -- select option
```

For checkboxes (batch):
```text
browser_click(refs=["e20", "e22"])
```

### Step 4 -- Verify before submit

Call `browser_snapshot()` to see the full form state.
Confirm all fields are filled correctly.

### Step 5 -- Submit

```text
browser_click("e30")  -- submit button ref
```

Or:
```text
browser_click(key="Enter")
```

### Step 6 -- Confirm result

Read the response snapshot.
Check for success message, error messages, or redirect.

## Stop conditions

- Form submitted successfully and confirmation received
- Or: validation error shown -- report the errors to the user
- Or: CAPTCHA/auth block -- use `browser_wait_for_user`

## Anti-patterns

- Filling fields with refs from a stale snapshot
- Submitting without verifying field values
- Submitting payment forms without explicit user confirmation
- Using separate click calls for each checkbox (use `refs: [...]`)
- Guessing field refs instead of reading from the latest snapshot
