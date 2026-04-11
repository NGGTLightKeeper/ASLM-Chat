---
title: "Reverse Engineering and Program Inspection"
domain: reverse-engineering
trigger: "User asks to analyze a binary, inspect a compiled program, or understand an unknown executable"
tools: [bash, file, strings, objdump, nm]
related_guides: [mcp-sandbox]
difficulty: hard
---

## Goal

Perform safe static analysis of a binary or compiled program to understand its purpose, dependencies, and behavior.

## When to use

- User provides a binary and asks what it does
- User wants to inspect an EXE, ELF, DLL, or shared library
- User asks about embedded strings, symbols, or imports in a compiled file

## When NOT to use

- The file is source code -- use `repo-analysis`
- The file is a document -- use `pdf-processing`
- Dynamic analysis or execution of untrusted binaries is requested -- refuse

## Safety limits

- Static analysis only. Do not execute unknown binaries.
- Do not attempt to bypass protections, DRM, or obfuscation.
- If the file appears malicious, report findings and stop.

## Workflow

### Step 1 -- Classify the file

```text
bash("file binary")
bash("ls -la binary")
```

### Step 2 -- Extract metadata

```text
bash("strings binary | head -100")
```

For ELF binaries:

```text
bash("readelf -h binary")
bash("readelf -d binary")
```

For PE (Windows) binaries:

```text
bash("objdump -p binary | head -60")
```

### Step 3 -- Inspect symbols and imports

```text
bash("nm -D binary | head -50")
bash("objdump -T binary | head -50")
```

### Step 4 -- Look for embedded resources

```text
bash("strings binary | grep -i 'http\|https\|api\|key\|password\|config' | head -30")
```

### Step 5 -- Synthesis

After steps 1-4, summarize:
- File type and architecture
- Key libraries and dependencies
- Notable strings and indicators
- Purpose assessment based on evidence

## Stop conditions

- File type and purpose are identified from static analysis
- Or: the file is packed/obfuscated beyond static analysis capability -- report this

## Anti-patterns

- Executing the binary to "see what it does"
- Dumping all strings without filtering
- Disassembling the entire binary when `strings` + `nm` is enough
- Spending more than 5 tool calls on a single binary without synthesis
