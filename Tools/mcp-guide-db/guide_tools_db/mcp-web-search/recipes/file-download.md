---
title: "File Download from Web"
domain: file-acquisition
trigger: "User needs to download a file found via web search (PDF, CSV, ZIP, etc.)"
tools: [web_search, read_page, import_web_file, bash]
related_guides: [mcp-web-search, mcp-sandbox]
difficulty: easy
---

## Goal

Identify and download a file from the web into the sandbox for processing.

## When to use

- Search results show a file badge (PDF, ZIP, CSV, etc.)
- `read_page` returned a "downloadable file" hint
- User provides a direct file URL

## When NOT to use

- The URL is a GitHub repository -- use `bash("git clone ...")`
- The URL is a webpage to read -- use `read_page`
- The file is over 50 MB -- use `bash("curl -L -o ...")`

## Workflow

### Step 1 -- Confirm the file

If from search results, check for file badges.
If from a URL, use `read_page` first to confirm it is a file, not a page.

### Step 2 -- Download

For confirmed files under 50 MB:

```text
import_web_file(url, save_to="downloads/", allowed_types=["text"])
```

For files over 50 MB:

```text
bash("curl -L -o downloads/filename.csv https://example.com/large.csv")
```

### Step 3 -- Verify

```text
bash("ls -la downloads/")
bash("file downloads/filename.pdf")
```

### Step 4 -- Hand off

Route to the appropriate sandbox recipe based on file type:
- PDF/DOCX -- `pdf-processing`
- ZIP/TAR -- `archive-triage`
- CSV/JSON -- direct bash analysis
- Image -- `media-conversion`

## Stop conditions

- File downloaded and verified in the sandbox workspace
- Or: download failed -- report error and stop

## Anti-patterns

- Using `import_web_file` on a GitHub repo URL
- Retrying `import_web_file` on the same URL after failure
- Passing `max_size_mb` above 50
- Downloading without verifying the file type first
- Using `read_page` repeatedly on a file URL expecting text
