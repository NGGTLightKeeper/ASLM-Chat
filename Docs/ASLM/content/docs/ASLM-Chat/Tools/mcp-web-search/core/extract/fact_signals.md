---
title: "fact_signals"
draft: false
---

## Module `fact_signals`

`Tools/mcp-web-search/core/extract/fact_signals.py` — ASLM Chat Python module.

---

## Public functions

#### `def has_currency(text) -> bool`

**Purpose:** True when text contains a currency symbol, ISO code, or currency word.

#### `def has_measurement(text) -> bool`

**Purpose:** True when text contains a numeric value with a known unit or percent.

#### `def has_decimal_number(text) -> bool`

**Purpose:** True when text contains a decimal number (digit separator or fraction).

#### `def fact_signal_score(text) -> float`

**Purpose:** Factual-density score: 0 none, 0.4 decimal only, 0.8 currency or unit.

**Steps:**

1. Return the computed result to the caller.

#### `def is_fact_like_text(text) -> bool`

**Purpose:** True when any factual signal is present in the text.

---

## Private functions

#### `def _compiled()`

**Purpose:** Implements `_compiled` in `fact_signals.py`.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [extract/_index](../../../../_index/)
