---
title: "models"
draft: false
---

## Module `models`

`Apps/Data/models.py` — ASLM Chat Python module.

---

## Classes

### `class MessageRole`

**Purpose:** Type `MessageRole` defined in `models.py`.

### `class Chat`

**Purpose:** Type `Chat` defined in `models.py`.

### `class Message`

**Purpose:** Type `Message` defined in `models.py`.

### `class MessageAttachmentKind`

**Purpose:** Type `MessageAttachmentKind` defined in `models.py`.

### `class MessageAttachment`

**Purpose:** Type `MessageAttachment` defined in `models.py`.

### `class MessageImage`

**Purpose:** Type `MessageImage` defined in `models.py`.

### `class OllamaPreset`

**Purpose:** Type `OllamaPreset` defined in `models.py`.

### `class LmsPreset`

**Purpose:** Type `LmsPreset` defined in `models.py`.

---

## Public functions

#### `def Chat.__str__() -> str`

**Purpose:** Return the display name for Django admin and logs.

#### `def Message.__str__() -> str`

**Purpose:** Return a compact preview of the stored message.

#### `def MessageAttachment.data_url() -> str`

**Purpose:** Return the stored attachment as a data URL.

#### `def MessageAttachment.is_image() -> bool`

**Purpose:** Return whether the attachment should be treated as an image.

#### `def MessageAttachment.__str__() -> str`

**Purpose:** Return a readable label for the related attachment.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def MessageImage.data_url() -> str`

**Purpose:** Return the stored image as a data URL.

#### `def MessageImage.__str__() -> str`

**Purpose:** Return a readable label for the related image.

#### `def OllamaPreset.__str__() -> str`

**Purpose:** Return a readable preset name with its model.

#### `def LmsPreset.__str__() -> str`

**Purpose:** Return a readable preset name with its model.

---

## Related

- [Data/_index](../../_index/)
