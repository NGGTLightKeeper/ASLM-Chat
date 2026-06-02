---
title: "Static"
draft: false
---

## `Apps/UI/static/js`

Client-side ES modules for the chat UI. Entry point: [js/main/main.js](js/main/main/).

| Folder | Role |
| --- | --- |
| [js/main](js/main/) | Bootstrap, context, API, chat controller, engine manager, events |
| [js/ui](js/ui/) | Message rendering, attachments, parameters, skills, browser portal |
| [js/engines](js/engines/) | LLM backend adapters |

**Out of scope for this reference:** `js/vendor/`, `jquery.min.js`, and non-JS assets under `Apps/UI/static/` (CSS, images).
