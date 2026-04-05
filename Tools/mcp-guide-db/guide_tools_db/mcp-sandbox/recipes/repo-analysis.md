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

### Step 0 -- Mandatory repo index pre-check

This step is mandatory for repository analysis.
Do not skip it.
Do not replace it with `cat`, `head`, or ad-hoc broad file reads.
Step 0 is not complete until you have read `repo_index.log` and used it to choose the next files or paths to inspect.
Create `repo_index.sh` with `write`, not with `cat <<'EOF'`.
The reason is simple: if the script has one bad line, you must be able to correct that line surgically instead of rewriting the whole file.

Before broad repository reading, create a compact repo index, check its size, and use that index to navigate.

If the repository is remote and not yet available locally, do Step 1 first, then return to Step 0 immediately.

Allowed exception:

- The user explicitly named one small file or one exact path and only wants that target inspected
- You already know the exact file and exact region you need, and no broad repository exploration is needed

If the task is "understand the repo", "analyze the codebase", "find where X lives", or anything similarly broad, Step 0 is required.

```text
write("repo_index.sh", "#!/bin/bash\nset -euo pipefail\n\nROOT=\"${1:-repo}\"\nOUT=\"${2:-repo_index.log}\"\n\n{\n  echo \"=== REPOSITORY STRUCTURE ===\"\n  find \"$ROOT\" -not -path '*/.*' -not -path '*/node_modules/*' -not -path '*/dist/*' -not -path '*/build/*' -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -not -path '*/.venv/*' -not -path '*/venv/*' | sed \"s#^$ROOT#.#\"\n  echo\n  echo \"=== FILE METADATA ===\"\n  find \"$ROOT\" -not -path '*/.*' -not -path '*/node_modules/*' -not -path '*/dist/*' -not -path '*/build/*' -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -not -path '*/.venv/*' -not -path '*/venv/*' -type f | while IFS= read -r file; do\n    size=$(stat -c%s \"$file\")\n    kind=$(file -b \"$file\")\n    printf '%s | %s bytes | %s\\n' \"$file\" \"$size\" \"$kind\"\n  done\n} > \"$OUT\"\n")
bash("chmod +x repo_index.sh")
bash("./repo_index.sh repo repo_index.log")
bash("stat repo_index.log")
bash("head -n 80 repo_index.log")
bash("grep -n '^===\\|README\\.md\\|package\\.json\\|pyproject\\.toml\\|Cargo\\.toml\\|go\\.mod\\|Dockerfile\\|src/\\|app/\\|cmd/' repo_index.log | head -40")
bash("sed -n '1,160p' repo_index.log")
```

If the generated index is large, do not `cat` it wholesale.
`repo_index.log` is not a throwaway file and not a one-time preview.
It is a reusable navigation artifact for the whole repository-analysis workflow.
Use `grep`, `rg`, `sed -n`, `head`, `tail`, and similar targeted commands against it throughout the task.
Do not read only the beginning or end of the log and then stop using it.
After reading the index, name the first 2-5 targets you will inspect next.
Do not proceed to broad direct file reads until this is done.

### Step 1 -- Acquire

If remote repository:

```text
bash("git clone https://github.com/user/repo repo")
```

If already local, skip.
If you performed Step 1, return to Step 0 immediately.
Do not continue to Step 2 until Step 0 is complete.

### Step 2 -- Map structure (breadth-first)

```text
bash("ls -la repo")
bash("find repo -maxdepth 2 -type f | head -60")
```

Look for markers: `README`, `Makefile`, `pyproject.toml`, `package.json`, `Dockerfile`, `setup.py`, `Cargo.toml`, `go.mod`.
Use `repo_index.log` from Step 0 as the default navigation map when the repo is large, noisy, or unfamiliar.
At this stage, direct file reads should be guided by what you already saw in `repo_index.log`.

### Step 3 -- Identify entry points

Common patterns:

- Python: `main.py`, `app.py`, `manage.py`, `__main__.py`
- JS/TS: `index.js`, `index.ts`, `server.js`, `app.js`
- Go: `main.go`, `cmd/`
- Rust: `src/main.rs`, `src/lib.rs`

```text
bash("find repo -name 'main.*' -o -name 'app.*' -o -name 'index.*' | head -10")
```

### Step 4 -- Localize target

```text
bash("grep -rn 'class.*Main\|def main\|if __name__' repo --include='*.py' | head -20")
```

Search for the specific symbol, class, or concept the user is asking about.

### Step 5 -- Read targeted regions

```text
bash("sed -n '1,60p' repo/src/main.py")
bash("head -n 40 repo/README.md")
```

Read only the justified region -- not the entire file.

For generated repo indexes or long manifests:

```text
bash("stat repo_index.log")
bash("head -n 80 repo_index.log")
bash("grep -n '^===\\|^repo/src/' repo_index.log | head -40")
bash("sed -n '120,220p' repo_index.log")
```

Keep returning to the index as you localize the next targets.
Do not treat `repo_index.log` as a file you read once and abandon.
Use the index to choose what to read next, then switch back to targeted source reads with `grep` + `sed -n`.

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

- Skipping Step 0 for a broad repository-analysis task
- Claiming Step 0 is unnecessary because `head` or `cat` feels faster
- Creating `repo_index.sh` with heredoc shell text when `write` would allow easier correction
- Creating `repo_index.log` and then not reading it
- Creating `repo_index.log` and then jumping straight to direct file reads
- Reading only the first chunk of `repo_index.log` and then ignoring the artifact for the rest of the task
- Reading every file in a directory sequentially
- Generating a giant analysis log and immediately `cat`-ing it
- `cat` on large files without `head` or `sed -n`
- Skipping `stat` before opening a generated manifest or log
- Continuing to explore after enough evidence exists
- Scanning all imports of every module
- Reading test files when the question is about architecture
- Using `cat` then re-reading the same file with `sed`

## Example trace

```text
bash("git clone https://github.com/user/repo repo")
bash("./repo_index.sh repo repo_index.log")
bash("stat repo_index.log")
bash("head -n 80 repo_index.log")
bash("grep -n '^===\\|README\\.md\\|package\\.json\\|src/' repo_index.log | head -20")
bash("ls -la repo")
bash("grep -rn 'def main\|class App' repo --include='*.py' | head -15")
bash("sed -n '1,50p' repo/src/app.py")
-- synthesis: "This is a Flask web app with routes in src/app.py, models in src/models/..."
```
