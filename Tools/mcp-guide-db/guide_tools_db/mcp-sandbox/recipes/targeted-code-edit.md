---
title: "Targeted Code Edit"
domain: code-modification
trigger: "User asks to change, fix, update, or add code in a specific file"
tools: [bash, edit, write]
related_guides: [mcp-sandbox]
difficulty: easy
---

## Goal

Make a precise code change in a known file with verification.

## When to use

- User says "fix this bug", "change this function", "add this import"
- User points to a specific file and wants a modification
- User provides a diff or describes a change

## When NOT to use

- User wants to understand the codebase first -- use `repo-analysis`
- User wants a full rewrite -- use `write` directly
- The target file and location are unknown -- use `repo-analysis` first

## Workflow

### Step 1 -- Locate the file

If the user named the file, verify it exists:

```text
bash("ls -la path/to/file.py")
```

If not named, search:

```text
bash("grep -rn 'function_name' . --include='*.py'")
```

### Step 2 -- Read the exact region

```text
bash("cat path/to/file.py")
```

For large files:

```text
bash("sed -n '45,80p' path/to/file.py")
```

### Step 3 -- Edit with exact match

```text
edit("path/to/file.py", old_str, new_str)
```

Rules:

- `old_str` must be copied exactly from the read result
- Include enough context lines to make the match unique
- If editing multiple locations, use `replace_all=true`

### Step 4 -- Verify

```text
bash("python path/to/file.py")
```

Or run tests:

```text
bash("pytest path/to/tests/")
```

### Step 5 -- Report

Summarize: what was changed, why, and verification result.

## Stop conditions

- Edit applied successfully and verified
- Or: edit failed twice on the same string -- stop and report

## Anti-patterns

- Editing without reading the file first
- Guessing the content of `old_str` from memory
- Using `write` for a small change (overwrites the entire file)
- Editing multiple times without verifying between edits
- Reading the entire project to make a one-line fix

## Example trace

```text
bash("cat task/utils.py")
edit("utils.py", "def old_name(x):", "def new_name(x):")
bash("python task/utils.py")
-- "Renamed function, verified import still works."
```
