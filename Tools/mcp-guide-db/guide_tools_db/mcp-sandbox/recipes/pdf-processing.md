---
title: "PDF and Document Processing"
domain: document-extraction
trigger: "User provides a PDF, DOCX, or text document and wants content extracted or analyzed"
tools: [bash, pdftotext, pymupdf, cat]
related_guides: [mcp-sandbox, mcp-web-search]
difficulty: medium
---

## Goal

Extract text, tables, or metadata from a document file and present the content.

## When to use

- User provides or references a PDF, DOCX, or similar document
- User asks to summarize or extract from a downloaded file
- `import_web_file` or `curl` just delivered a document to `task/`

## When NOT to use

- The content is a webpage -- use `read_page` instead
- The file is an image -- use `media-conversion` recipe

## Workflow

### Step 1 -- Confirm file type

```text
bash("file task/downloads/document.pdf")
bash("ls -la task/downloads/document.pdf")
```

### Step 2 -- Choose extraction method

For PDF:

```text
bash("pdftotext task/downloads/document.pdf -")
```

Or with pymupdf4llm (better for structured content):

```text
bash("python -c \"import pymupdf4llm; print(pymupdf4llm.to_markdown('task/downloads/document.pdf'))\"")
```

For plain text:

```text
bash("cat task/downloads/document.txt")
```

### Step 3 -- Handle large output

If document is long, extract by page range:

```text
bash("pdftotext -f 1 -l 5 task/downloads/document.pdf -")
```

Or pipe through head:

```text
bash("pdftotext task/downloads/document.pdf - | head -200")
```

### Step 4 -- Summarize or answer

Present the extracted content relevant to the user's question.
Do not dump the entire document if a targeted section answers the question.

## Stop conditions

- The relevant content has been extracted and presented
- Extraction tool failed twice with the same error -- report and stop

## Anti-patterns

- Dumping entire multi-page documents into context
- Using `cat` on a binary PDF
- Trying multiple extraction tools without checking the first result
- Re-downloading the file when it already exists in `task/`

## Fallback path

If `pdftotext` fails:
1. Try `pymupdf4llm`
2. Try OCR: `bash("tesseract task/downloads/page.png stdout")`
3. Report failure
