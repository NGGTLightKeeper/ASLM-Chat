---
title: "Archive Triage"
domain: file-processing
trigger: "User provides a ZIP, TAR, 7z, or other archive to inspect or extract"
tools: [bash, unzip, tar, file, find]
related_guides: [mcp-sandbox]
difficulty: easy
---

## Goal

Inspect archive contents, extract relevant files, and continue with the appropriate workflow.

## When to use

- User provides or downloads an archive file (ZIP, TAR, GZ, 7z, RAR)
- `import_web_file` or `curl` delivered an archive into the sandbox workspace
- User asks "what is inside this archive"

## When NOT to use

- The file is a single document -- use `pdf-processing`
- The archive is a git repository -- use `git clone` directly

## Workflow

### Step 1 -- Identify archive type

```text
bash("file downloads/archive.zip")
```

### Step 2 -- List contents without extracting

For ZIP:
```text
bash("unzip -l downloads/archive.zip | head -40")
```

For TAR/GZ:
```text
bash("tar -tzf downloads/archive.tar.gz | head -40")
```

For 7z:
```text
bash("7z l downloads/archive.7z | head -40")
```

### Step 3 -- Assess and plan

Based on the listing:
- How many files? What types?
- Are there binaries that should be avoided?
- Which files are relevant to the user's question?

### Step 4 -- Extract minimal subset

Extract only needed files when possible:

```text
bash("unzip downloads/archive.zip 'path/to/specific/file.txt' -d extracted/")
```

Or extract everything if the archive is small:

```text
bash("unzip downloads/archive.zip -d extracted/")
```

### Step 5 -- Hand off

After extraction, continue with the appropriate recipe:
- Source code -- `repo-analysis`
- Documents -- `pdf-processing`
- Data files -- direct `bash` analysis

## Stop conditions

- Contents are listed and relevant files identified
- Or: extraction complete and handoff to next workflow done

## Anti-patterns

- Extracting everything blindly from a large archive
- Attempting to read binary files after extraction
- Ignoring the file listing and extracting without assessment
- Extracting into the root of the sandbox workspace without a subdirectory
