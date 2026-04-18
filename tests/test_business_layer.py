from __future__ import annotations

import tempfile
import unittest
from dataclasses import asdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import select

from newsletter_mcp import server
from newsletter_mcp.business import DailyContinuityService, IssueBriefService
from newsletter_mcp.database import Database, IssueBrief
from newsletter_mcp.models import ParsedNewsletter, SectionSummary, WatchlistReference, WatchlistRow


def _make_watchlist_row(
    *,
    commodity_name: str = "Corn",
    spread_code: str = "CU26-CZ26",
    category: str = "Grain",
    section_name: str = "intra_commodity",
    trade_quality: str | None = "Tier 1",
    ridx: float = 35.0,
) -> WatchlistRow:
    return WatchlistRow(
        commodity_name=commodity_name,
        spread_code=spread_code,
        side="SELL",
        legs=1,
        category=category,
        enter_date=date(2026, 4, 17),
        exit_date=date(2026, 8, 30),
        win_pct=93.0,
        avg_profit=642,
        avg_best_profit=910,
        avg_worst_loss=-220,
        avg_draw_down=-140,
        apw_pct=12.0,
        ridx=ridx,
        five_year_corr=4,
        portfolio=None,
        risk_level=None,
        trade_quality=trade_quality,
        volatility_structure="High",
        section_name=section_name,
        page_number=8,
        raw_row="raw row",
    )


def _make_service_row(
    *,
    commodity_name: str = "Corn",
    spread_code: str = "CU26-CZ26",
    category: str = "Grain",
    section_name: str = "intra_commodity",
    trade_quality: str | None = "Tier 1",
    ridx: float = 35.0,
    tradeable: bool | None = True,
    blocked_reason: str | None = None,
) -> SimpleNamespace:
    row = _make_watchlist_row(
        commodity_name=commodity_name,
        spread_code=spread_code,
        category=category,
        section_name=section_name,
        trade_quality=trade_quality,
        ridx=ridx,
    )
    return SimpleNamespace(**asdict(row), tradeable=tradeable, blocked_reason=blocked_reason)


def _make_parsed_newsletter(base_dir: Path) -> ParsedNewsletter:
    source_file = base_dir / "brief-issue.pdf"
    source_file.write_bytes(b"pdf")
    return ParsedNewsletter(
        source_file=source_file,
        file_hash="brief-hash",
        title="Week Ended 2026-04-10",
        week_ended=date(2026, 4, 10),
        raw_text="Raw text",
        metadata={"page_count": 12, "source_filename": source_file.name},
        overall_summary="This week focuses on grains and volatility structures.",
        section_summaries=[
            SectionSummary(
                name="Watch List",
                page_start=8,
                page_end=8,
                raw_text="Watch List page",
                summary_text="Watch List summary",
            )
        ],
        watchlist_reference=WatchlistReference(
            page_number=7,
            raw_text="Reference page",
            summary_text="Reference summary",
            column_definitions=[{"column": "Win %", "meaning": "Winning rate"}],
            trading_rules=["BUY means buy first leg"],
            classification_rules=["Tier 1 is strongest"],
        ),
        watchlist_rows=[
            _make_watchlist_row(category="Grain", commodity_name="Corn"),
            _make_watchlist_row(category="Energy", commodity_name="Natural Gas", spread_code="NGZ26-NGF27"),
        ],
    )


class IssueBriefServiceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        server.database.engine.dispose()

    def test_build_issue_brief_generates_business_summary(self) -> None:
        rows = [
            _make_service_row(category="Grain", commodity_name="Corn"),
            _make_service_row(
                category="Energy",
                commodity_name="Gasoil",
                spread_code="GOU26-GOZ26",
                tradeable=False,
                blocked_reason="Gasoil is not available in TOS.",
                ridx=24.0,
                trade_quality="Tier 3",
            ),
        ]
        delta = type(
            "Delta",
            (),
            {
                "added_entries_json": [{"entry_key": "new"}],
                "removed_entries_json": [],
                "changed_entries_json": [],
                "summary_text": "Added 1 entries, removed 0 entries, and changed 0 carried entries versus the prior issue.",
            },
        )()
        reference = type("Reference", (), {"trading_rules_json": ["BUY means buy first leg"], "classification_rules_json": []})()

        brief = IssueBriefService.build_issue_brief(
            title="Week Ended 2026-04-10",
            executive_summary="Weekly summary",
            entries=rows,
            delta=delta,
            reference=reference,
        )

        self.assertEqual(brief.watchlist_summary["entry_count"], 2)
        self.assertEqual(brief.watchlist_summary["category_counts"]["Grain"], 1)
        self.assertEqual(brief.watchlist_summary["volatility_counts"]["High"], 2)
        self.assertEqual(brief.watchlist_summary["dominant_category"]["label"], "Grain")
        self.assertEqual(brief.watchlist_summary["dominant_volatility"]["label"], "High")
        self.assertTrue(brief.watchlist_summary["blocked_examples"])
        self.assertEqual(brief.change_summary["added_count"], 1)
        self.assertTrue(brief.key_themes)
        self.assertTrue(any("volatility" in theme.lower() for theme in brief.key_themes))
        self.assertTrue(any("blocked" in risk.lower() for risk in brief.notable_risks))
        self.assertTrue(brief.notable_opportunities)

    def test_save_parsed_newsletter_persists_business_brief_fields(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base_dir = Path(temp_dir.name)
        database = Database(f"sqlite:///{(base_dir / 'business.db').as_posix()}")
        database.create_schema()
        self.addCleanup(database.engine.dispose)
        database_patch = mock.patch.object(server, "database", database)
        database_patch.start()
        self.addCleanup(database_patch.stop)

        parsed = _make_parsed_newsletter(base_dir)
        server._save_parsed_newsletter(parsed)

        with database.session() as session:
            brief = session.execute(select(IssueBrief)).scalar_one()
            self.assertEqual(brief.watchlist_summary_json["entry_count"], 2)
            self.assertIn("category_counts", brief.watchlist_summary_json)
            self.assertIn("volatility_counts", brief.watchlist_summary_json)
            self.assertIn("dominant_category", brief.watchlist_summary_json)
            self.assertTrue(brief.key_themes_json)
            self.assertTrue(brief.notable_opportunities_json)

    def test_get_issue_summary_returns_stored_business_layer_fields(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base_dir = Path(temp_dir.name)
        database = Database(f"sqlite:///{(base_dir / 'issue-summary.db').as_posix()}")
        database.create_schema()
        self.addCleanup(database.engine.dispose)
        database_patch = mock.patch.object(server, "database", database)
        database_patch.start()
        self.addCleanup(database_patch.stop)

        parsed = _make_parsed_newsletter(base_dir)
        server._save_parsed_newsletter(parsed)

        summary = server.get_issue_summary("2026-04-10")

        self.assertEqual(summary["week_ended"], "2026-04-10")
        self.assertIn("issue_brief", summary)
        self.assertIn("key_themes", summary["issue_brief"])
        self.assertIn("watchlist_summary", summary["issue_brief"])
        self.assertIn("volatility_counts", summary["issue_brief"]["watchlist_summary"])
        self.assertIn("issue_delta", summary)
        self.assertIn("watchlist_reference", summary)


class DailyContinuityServiceTests(unittest.TestCase):
    def test_resolve_entry_degrades_sunday_pass_on_portfolio_overlap(self) -> None:
        entry = {
            "spread_code": "VXN26-VXU26",
            "legs": ["/VXMN26", "/VXMU26"],
            "tradeable": True,
            "manual_legs_required": True,
            "deferred_principles": [
                "margin_as_survivability_constraint",
                "portfolio_fit_over_isolated_trade_appeal",
            ],
            "principle_influences": {
                "structure_before_conviction": [
                    "weekly_intelligence.opportunity_signal",
                    "issue_delta.new_this_week",
                ],
                "volatility_as_constraint": ["weekly_intelligence.volatility_emphasis"],
            },
        }

        decision = DailyContinuityService.resolve_entry(
            entry,
            open_leg_symbols={"/VXMN26", "/VXMU26"},
            dead_symbols={"/VXMN26", "/VXMU26"},
        )

        self.assertEqual(decision.daily_state, "degraded")
        self.assertEqual(decision.drift, "weaker_than_sunday")
        self.assertEqual(decision.portfolio_fit, "fail")
        self.assertIn("/VXMN26", decision.overlap)
        self.assertTrue(any("downgraded" in note.lower() for note in decision.notes))

    def test_analyze_watchlist_summarizes_ready_blocked_and_degraded(self) -> None:
        watchlist = [
            {
                "spread_code": "LCG27-LHG27",
                "legs": ["/LEG27", "/HEG27"],
                "tradeable": True,
                "manual_legs_required": False,
                "deferred_principles": [
                    "margin_as_survivability_constraint",
                    "portfolio_fit_over_isolated_trade_appeal",
                ],
                "principle_influences": {
                    "selectivity_not_participation": ["weekly_intelligence.opportunity_signal"],
                    "intercommodity_conditional_edge": ["watchlist_reference.rule_context"],
                },
            },
            {
                "spread_code": "SU26-SF27",
                "legs": ["/ZSU26", "/ZSF27"],
                "tradeable": True,
                "manual_legs_required": False,
                "deferred_principles": [
                    "margin_as_survivability_constraint",
                    "portfolio_fit_over_isolated_trade_appeal",
                ],
                "principle_influences": {
                    "selectivity_not_participation": ["weekly_intelligence.opportunity_signal"],
                },
            },
            {
                "spread_code": "GCQ26-GCZ26",
                "legs": ["/GCQ26", "/GCZ26"],
                "tradeable": False,
                "manual_legs_required": False,
                "deferred_principles": [
                    "margin_as_survivability_constraint",
                    "portfolio_fit_over_isolated_trade_appeal",
                ],
                "principle_influences": {},
            },
        ]

        decisions = DailyContinuityService.analyze_watchlist(
            watchlist,
            open_leg_symbols={"/ZSU26", "/ZSF27"},
            dead_symbols=set(),
        )
        summary = DailyContinuityService.summarize(decisions)

        self.assertEqual(summary["ready"], 1)
        self.assertEqual(summary["degraded"], 1)
        self.assertEqual(summary["blocked"], 1)


if __name__ == "__main__":
    unittest.main()
