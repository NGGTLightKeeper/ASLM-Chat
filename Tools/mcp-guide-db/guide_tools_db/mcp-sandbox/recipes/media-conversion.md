---
title: "Media Conversion and OCR"
domain: media-processing
trigger: "User asks to process images, audio, video, or extract text from images via OCR"
tools: [bash, tesseract, ffmpeg, convert]
related_guides: [mcp-sandbox]
difficulty: medium
---

## Goal

Process media files: convert formats, extract text from images (OCR), transcribe audio, or manipulate video/images.

## When to use

- User provides an image and wants text extracted (OCR)
- User wants format conversion (image, audio, video)
- User asks to resize, crop, or transform media
- User needs audio transcription

## When NOT to use

- The file is a document (PDF, DOCX) -- use `pdf-processing`
- The user wants to inspect a webpage screenshot -- use browser tools

## Workflow

### Step 1 -- Classify the media

```text
bash("file media/input.png")
bash("ls -la media/")
```

### Step 2 -- Choose the right tool

**OCR (text from images):**

```text
bash("tesseract media/page.png stdout -l eng")
```

For Russian + English:
```text
bash("tesseract media/page.png stdout -l rus+eng")
```

**Image conversion/manipulation:**

```text
bash("convert media/input.png -resize 800x600 media/output.jpg")
```

**Audio/video with ffmpeg:**

```text
bash("ffmpeg -i media/video.mp4 -vn -acodec mp3 media/audio.mp3")
```

**Audio transcription (whisper):**

```text
bash("python -c \"from faster_whisper import WhisperModel; m=WhisperModel('base'); segs,_=m.transcribe('media/audio.mp3'); print('\\n'.join(s.text for s in segs))\"")
```

### Step 3 -- Verify output

```text
bash("file media/output.jpg")
bash("ls -la media/output.jpg")
```

For OCR, review the extracted text and clean up if needed.

### Step 4 -- Present result

Summarize the output or present the extracted text.

## Stop conditions

- Conversion complete and output verified
- Or: OCR text extracted and presented

## Anti-patterns

- Running OCR on a text file
- Using ffmpeg without checking input format first
- Converting without verifying the output exists
- Ignoring language flags for OCR (default is English only)
