---
title: "Repository Analysis"
domain: code-analysis
trigger: "User asks to understand, analyze, inspect, or explore a git repository"
tools: [bash, grep, find, cat, sed]
related_guides: [mcp-sandbox]
difficulty: medium
---

## Goal

Understand the architecture, entry points, and key components of a repository.

## When to use

- User asks to analyze or understand a project
- User gives a GitHub URL to inspect
- User asks to find a specific component in a codebase
- User asks "what does this project do?"

## When NOT to use

- User just wants to edit a known file -- use `targeted-code-edit`
- User wants to run tests -- direct `bash` execution
- User wants a single file read -- just `bash("cat ...")`

## Workflow

### Step 1 -- Acquire

If remote repository:

```text
bash("git clone https://github.com/user/repo task/repo")
```

If already local, skip.

### Step 2 -- Map structure (breadth-first)

```text
bash("ls -la task/repo")
bash("find task/repo -maxdepth 2 -type f | head -60")
```

Look for markers: `README`, `Makefile`, `pyproject.toml`, `package.json`, `Dockerfile`, `setup.py`, `Cargo.toml`, `go.mod`.

### Step 3 -- Identify entry points

Common patterns:

- Python: `main.py`, `app.py`, `manage.py`, `__main__.py`
- JS/TS: `index.js`, `index.ts`, `server.js`, `app.js`
- Go: `main.go`, `cmd/`
- Rust: `src/main.rs`, `src/lib.rs`

```text
bash("find task/repo -name 'main.*' -o -name 'app.*' -o -name 'index.*' | head -10")
```

### Step 4 -- Localize target

```text
bash("grep -rn 'class.*Main\|def main\|if __name__' task/repo --include='*.py' | head -20")
```

Search for the specific symbol, class, or concept the user is asking about.

### Step 5 -- Read targeted regions

```text
bash("sed -n '1,60p' task/repo/src/main.py")
bash("head -n 40 task/repo/README.md")
```

Read only the justified region -- not the entire file.

### Step 6 -- Synthesis checkpoint

After reading 3 files/regions, STOP and assess:

- Can you describe what the project does?
- Can you answer the user's specific question?
- YES -- answer now
- NO -- state exactly what is missing and search for it

## Stop conditions

- You can describe the project's purpose and structure
- You've identified the component relevant to the user's question
- You have enough evidence to answer with qualified confidence

## Anti-patterns

- Reading every file in a directory sequentially
- `cat` on large files without `head` or `sed -n`
- Continuing to explore after enough evidence exists
- Scanning all imports of every module
- Reading test files when the question is about architecture
- Using `cat` then re-reading the same file with `sed`

## Example trace

```text
bash("git clone https://github.com/user/repo task/repo")
bash("ls -la task/repo")
bash("find task/repo -maxdepth 2 -type f | head -40")
bash("grep -rn 'def main\|class App' task/repo --include='*.py' | head -15")
bash("sed -n '1,50p' task/repo/src/app.py")
-- synthesis: "This is a Flask web app with routes in src/app.py, models in src/models/..."
```
