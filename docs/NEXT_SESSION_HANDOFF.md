# SmartSpreads Session Handoff

## How to use this file

Update this file at the end of each significant session. The next session
should open this file first to understand current project state and priorities.

## Current version

<!-- Update this after each handoff -->
Version: (not yet written)
Date: (not yet written)

## 1. Project state summary

<!-- What is the current state of the project? What was completed recently? -->

## 2. Architecture / module changes

<!-- Any new modules, renamed files, schema changes, or dependency changes since last handoff? -->

## 3. Database / content state

<!-- Current DB counts, latest ingested issue, latest published issue -->

## 4. Current risks / friction points

<!-- Known bugs, parser issues, calibration concerns, unresolved contracts -->

## 5. Next priorities

<!-- Ordered list of what should be worked on next -->

## 6. Quick-start commands

```powershell
# Verify local setup
powershell -ExecutionPolicy Bypass -File .\scripts\verify_local.ps1

# Run tests
python -m unittest discover -s tests

# Weekly pipeline
powershell -ExecutionPolicy Bypass -File .\scripts\run_weekly_pipeline.ps1

# Offline CLI
python scripts/smartspreads_cli.py
```

## 7. Session opener prompt

<!-- A copy-paste prompt to resume quickly in Claude -->

## Archived handoffs

- [v0.1 (2026-05-02)](archive/NEXT_SESSION_HANDOFF-v0.1.md) — Phase 1 complete, cross-repo hardening done, observation/calibration stage
