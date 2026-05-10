# SmartSpreads Session Handoff

## How to use this file

Update this file at the end of each significant session. The next session
should open this file first to understand current project state and priorities.

## Current version

Version: v0.2
Date: 2026-05-10

## 1. Project state summary

Sunday and Daily Phase 3 flows are working end to end. Unified CLI (SmartSpreads + Schwab) is operational with 5 layers (A-E). Docs consolidated (7 files archived, prompts merged). Report directory restructured: issue reports by `week_ended`, Schwab snapshots by calendar date, management reports overwrite in place.

## 2. Architecture / module changes

- `scripts/smartspreads_cli.py` — rewritten from 4 layers to 5 layers (A-E), now bridges both MCPs
- Schwab tools imported directly from `schwab_mcp.tools.*` (all sync, no async wrappers needed)
- Schwab `.env` loaded lazily on first D/E layer access
- `docs/SETUP.md` — merged from CLIENT_CONFIG.md + DEPLOY_LOCAL.md
- `docs/CLI.md` — new, unified CLI usage guide
- 7 docs archived to `docs/archive/`

## 3. Database / content state

<!-- Update these counts after each session -->
- DB: newsletters=~20, watchlist_entries=~280, strategy_principles=7
- Newsletter coverage: 2025-12-26 to 2026-05-08
- Latest published: 2026-05-08 (12 entries, 8 intra + 4 inter)
- Tests: 31+ passing

## 4. Current risks / friction points

1. Parser remains regex-heavy, narrative summaries noisy/OCR-sensitive
2. Gasoil is unresolved/untradeable for TOS
3. Schema evolution is runtime/additive, not migration-first
4. Daily persistence not yet started (`portfolio_fit_reviews` is the leading candidate)
5. Principle calibration active work (`volatility_as_constraint` can over-block)
6. Streaming tools not available in CLI mode — REST alternatives cover most needs

## 5. Next priorities

1. Parser tests and validation hardening
2. Richer validation reporting
3. First Daily persistence layer (`portfolio_fit_reviews`)
4. Live calibration of principle scoring
5. Schema migrations

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

> Open `docs/NEXT_SESSION_HANDOFF.md` and `docs/CLI.md`. Review current state, risks, and priorities. Then check `git log --oneline -10` for recent changes. Ask me what to work on.

## Archived handoffs

- [v0.1 (2026-05-02)](archive/NEXT_SESSION_HANDOFF-v0.1.md) — Phase 1 complete, cross-repo hardening done, observation/calibration stage
