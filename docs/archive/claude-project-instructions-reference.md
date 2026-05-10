# Claude Project Instructions Reference

This document explains how to update Claude Project Instructions for the
current SmartSpreads architecture.

It is the longer companion to:
- [`CLAUDE_PROJECT_INSTRUCTIONS.md`](../CLAUDE_PROJECT_INSTRUCTIONS.md)

## Why the old instruction set is outdated

The older project instructions assumed a largely manual workflow:
- upload a newsletter PDF
- perform a strict page-by-page validation step
- manually deep-dive the issue
- generate Excel/Word artifacts as the primary workflow outputs
- use screenshots and past conversation history as the main operational memory

That model was useful early on, but it no longer matches the implemented
system.

The current architecture now has distinct system responsibilities:

- `smartspreads-mcp`
  - newsletter memory
  - weekly intelligence
  - issue briefs and deltas
  - strategy doctrine
  - newsletter-history-backed exit resolution

- `schwab-smartspreads-file`
  - current Daily positions
  - live/latest market data
  - spread values and current P/L
  - file-based TOS workflow

The newer workflow is no longer "manually analyze the PDF first and do
everything from there." It is:

1. ingest/store weekly intelligence
2. publish the approved weekly contract
3. use Schwab MCP operational data for Daily workflow
4. use newsletter history and doctrine for interpretation

## What should remain from the old instructions

These ideas are still valuable and should remain as policy/rules:

- SmartSpreads-only scope
- TOS / Schwab futures-spread context
- RIDX threshold and tier rules
- entry/exit timing defaults
- no-stop/no-target default risk framework with explicit exceptions
- portfolio margin limits
- permanently blocked or excluded markets like `/GF`
- structural volatility concepts
- no stop-loss / profit-target default framework
- scheduled exits remain valid unless explicitly overridden
- portfolio-fit and concentration thinking

## What should be removed or de-emphasized

These should no longer be the center of Claude’s permanent project rules:

- mandatory manual 3-step PDF workflow before all analysis
- strict requirement to manually inventory the PDF before system use
- Excel/Word artifact generation as the default workflow
- "search past conversations" as the primary way to find exit dates
- old static Google Doc link lists as the main historical memory source
- assumptions that screenshots are the primary source of Daily position truth

## Current recommended project-instruction model

The short copy-paste project instructions are in:
- [`CLAUDE_PROJECT_INSTRUCTIONS.md`](../CLAUDE_PROJECT_INSTRUCTIONS.md)

The design goals of that shorter version are:

- keep it short enough that Claude reliably follows it
- focus on MCP system boundaries
- define the Sunday vs Daily split
- preserve the important SmartSpreads trading rules
- preserve durable business rules from the older instruction set without preserving the manual workflow
- stop Claude from exposing tool chatter
- encourage use of the doctrine layer when appropriate

## Key instruction themes

### 1. System roles

Claude should understand:

- `smartspreads-mcp` = weekly intelligence and memory
- `schwab-smartspreads-file` = Daily operational state

### 2. Workflow split

Sunday:
- ingest
- validate
- brief
- publish

Daily:
- load current positions
- load live/latest marks
- resolve exits from newsletter history
- combine with weekly intelligence
- produce action-oriented Daily output

### 3. Exit resolution

Claude should not search old chats when the system already supports:
- current-watchlist matches
- legacy carryovers
- broker-root-aware symbol matching
- quantity-aware butterfly matching

This is why project instructions should prefer:
- `schwab-smartspreads-file.get_futures_positions`
- `smartspreads-mcp.get_daily_exit_schedule`

### 4. Response style

Claude should be told to avoid:
- tool discovery chatter
- function schema dumps
- internal MCP details

This keeps the final answer readable during Daily use.

### 5. Strategy doctrine

The imported Smart Spreads strategy manual is now a usable doctrine layer.
Project instructions should encourage Claude to use it when explaining:

- why a setup matters
- why a setup is blocked
- why portfolio overlap matters
- why volatility and margin should shape decisions

## Recommended maintenance approach

Keep permanent project instructions for:
- system boundaries
- workflow ordering
- business rules
- response behavior

Keep changing operational prompts in:
- [`PROMPTS.md`](../PROMPTS.md)
- [`CLAUDE_CHEAT_SHEET.md`](../CLAUDE_CHEAT_SHEET.md)

This keeps project instructions stable while allowing prompt styles to evolve.

## Suggested update process

When updating Claude project instructions later:

1. keep the short version short
2. move explanation into repo docs, not into the project instructions
3. add new rules only if they are durable and repeatedly useful
4. avoid embedding temporary workflows or one-off prompts

## Current recommendation

Use:
- [`CLAUDE_PROJECT_INSTRUCTIONS.md`](../CLAUDE_PROJECT_INSTRUCTIONS.md)

as the new project instruction source.

Use:
- [`CLAUDE_CHEAT_SHEET.md`](../CLAUDE_CHEAT_SHEET.md)

for day-to-day prompting.
