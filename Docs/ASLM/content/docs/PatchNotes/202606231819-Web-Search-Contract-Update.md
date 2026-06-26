---
title: "Web Search Contract Update"
date: 2026-06-23T18:19:54Z
draft: false
description: "Update web search contract to refine effort tier rules, introduce a strict escalation budget for high effort, and enforce sufficiency checks before escalating searches."
---

## New Features

- **[Web Search]**: Updated the MCP search contract (`Tools/mcp-web-search/core/mcp_contract.py`) to refine search effort definitions and rules. `medium` effort is explicitly established as the starting point for all new intents.
- **[Web Search]**: Introduced an Escalation Budget for the `high` effort tier. `high` effort searches are now treated as a rationed, reserved tier, capped at a maximum of 3 calls per response to prevent abuse and excessive resource consumption. Any calls beyond this will return a quota notice, and searches must downshift to lower tiers.
- **[Web Search]**: Added a Sufficiency rule that mandates checking existing gathered evidence before escalating to any further search, preventing unnecessary follow-up queries when answers are already available.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
