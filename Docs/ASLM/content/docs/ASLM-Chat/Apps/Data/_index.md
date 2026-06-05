---
title: "Data"
draft: false
---

## Apps.Data

Django app for **chat persistence** and **engine presets** (Ollama / LM Studio). No HTTP views — APIs live in [Apps.UI](../UI/).

| Module | Role |
| --- | --- |
| [models](models/) | `Chat`, `Message`, attachments, presets |
| [ollama_presets](ollama_presets/) | Ollama preset CRUD and normalization |
| [lms_presets](lms_presets/) | LM Studio preset CRUD |
| [admin](admin/) | Django admin registrations |
| [tests](tests/) | Automated regression tests |

Migrations under `Apps/Data/migrations/` are schema history, not documented here.
