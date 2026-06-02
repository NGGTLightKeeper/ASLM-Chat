---
title: "JavaScript"
draft: false
---

## `Apps/UI/static/js`

ES module graph rooted at [main/main.js](main/main/).

| Folder | Role |
| --- | --- |
| [main](main/) | Bootstrap, context, API, chat controller, engine manager, events |
| [ui](ui/) | DOM rendering: messages, attachments, parameters, skills, browser portal |
| [engines](engines/) | Per-backend adapters (Ollama service, LMS, OpenAI, Google GenAI) |

Factory modules export `create*` functions that close over `context` from [app-context](main/app-context/) and return a public method object.

Third-party scripts under `vendor/` and `jquery.min.js` are not documented here.
