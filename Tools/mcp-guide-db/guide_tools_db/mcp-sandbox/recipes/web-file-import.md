---
title: "Web File Import and Local Analysis"
domain: file-acquisition
trigger: "User provides a URL to a file (PDF, CSV, ZIP, image) that needs to be downloaded and processed locally"
tools: [bash, curl, import_web_file]
related_guides: [mcp-sandbox, mcp-web-search]
difficulty: easy
---

## Goal

Download a remote file into the sandbox and hand off to the appropriate processing workflow.

## When to use

- User provides a direct file URL (not a webpage)
- Search results show a downloadable file badge
- `read_page` returned a "downloadable file" hint

## When NOT to use

- The URL is a webpage -- use `read_page`
- The URL is a GitHub repository -- use `bash("git clone ...")`
- The user just wants to read a webpage -- use browser or web-search tools

## Workflow

### Step 1 -- Determine acquisition method

**Files under 50 MB with known type:**

```text
import_web_file(url, save_to="downloads/", allowed_types=["text"])
```

**Files over 50 MB or when you need precise control:**

```text
bash("curl -L -o downloads/file.csv https://example.com/large.csv")
```

**When the URL is confirmed by search/read_page hint:**

Use `import_web_file` -- it handles content-type detection and safe naming.

### Step 2 -- Verify the download

```text
bash("ls -la downloads/")
bash("file downloads/file.pdf")
```

### Step 3 -- Hand off to processing recipe

Based on file type:

| Type | Next recipe |
| --- | --- |
| PDF, DOCX, TXT | `pdf-processing` |
| ZIP, TAR, 7z | `archive-triage` |
| CSV, JSON, XML | Direct `bash` analysis (`head`, `jq`, `awk`) |
| Image | `media-conversion` (OCR) or direct inspection |
| Source code archive | `archive-triage` then `repo-analysis` |

## Stop conditions

- File downloaded and verified in the sandbox workspace
- Handoff to the correct processing recipe initiated

## Anti-patterns

- Using `read_page` on a direct file URL
- Using `import_web_file` for files over 50 MB
- Using `import_web_file` on a GitHub repo URL (use `git clone`)
- Downloading without verifying the file landed correctly
- Retrying `import_web_file` more than once on the same URL

## Decision table

| Scenario | Action |
| --- | --- |
| Direct file URL, < 50 MB | `import_web_file(url)` |
| Direct file URL, > 50 MB | `bash("curl -L -o ...")` |
| GitHub repository | `bash("git clone ...")` |
| Unknown URL type | `read_page(url)` first, then decide |
