from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from sqlalchemy import select

from newsletter_mcp import server
from newsletter_mcp.database import (
    Database,
    Newsletter,
    PublicationArtifact,
    PublicationRun,
    SchwabFuturesCatalog,
    StrategyDocument,
    StrategyPrinciple,
    WatchlistEntry,
)
from newsletter_mcp.models import ParsedNewsletter, SectionSummary, WatchlistReference, WatchlistRow


def _make_row(
    *,
    commodity_name: str = "Corn",
    spread_code: str = "CU26-CZ26",
    section_name: str = "intra_commodity",
    trade_quality: str | None = "Tier 1",
    ridx: float = 35.0,
) -> WatchlistRow:
    return WatchlistRow(
        commodity_name=commodity_name,
        spread_code=spread_code,
        side="SELL",
        legs=1,
        category="Grain",
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


def _make_parsed_newsletter(base_dir: Path) -> ParsedNewsletter:
    source_file = base_dir / "publish-issue.pdf"
    source_file.write_bytes(b"pdf")
    return ParsedNewsletter(
        source_file=source_file,
        file_hash="publish-hash",
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
            _make_row(spread_code="CU26-CZ26"),
            _make_row(
                commodity_name="Sugar #11",
                spread_code="SBK26-SBV26",
                section_name="intra_commodity",
                trade_quality="Tier 3",
            ),
        ],
    )


class PublicationContractTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        server.database.engine.dispose()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.database = Database(f"sqlite:///{(self.base_dir / 'publish.db').as_posix()}")
        self.database.create_schema()
        self.addCleanup(self.database.engine.dispose)
        self.database_patch = mock.patch.object(server, "database", self.database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self._seed_strategy_principles()

        parsed = _make_parsed_newsletter(self.base_dir)
        server._save_parsed_newsletter(parsed)

    def _seed_strategy_principles(self) -> None:
        with self.database.session() as session:
            document = StrategyDocument(
                title="Trading Commodity Spreads",
                source_file=str(self.base_dir / "strategy.pdf"),
                file_hash="strategy-hash",
                document_type="strategy_manual",
                raw_text="manual",
                summary_text="summary",
                metadata_json={},
            )
            session.add(document)
            session.flush()
            for seed in server.STRATEGY_PRINCIPLE_SEED:
                session.add(
                    StrategyPrinciple(
                        strategy_document_id=document.id,
                        strategy_section_id=None,
                        principle_key=seed["principle_key"],
                        principle_title=seed["principle_title"],
                        category=seed["category"],
                        priority=seed["priority"],
                        summary_text=seed["summary_text"],
                        guidance_text=seed["guidance_text"],
                        applies_to_json=seed.get("applies_to", []),
                        examples_json=[],
                        anti_patterns_json=seed.get("anti_patterns", []),
                        metadata_json={"threshold": 0.75},
                    )
                )

    def test_publish_issue_writes_contract_files_and_db_records(self) -> None:
        output_dir = self.base_dir / "published"

        result = server.publish_issue(
            week_ended="2026-04-10",
            output_dir=str(output_dir),
            publication_version="published-1",
            published_by="unit-test",
        )

        self.assertEqual(result["watchlist_count"], 2)
        self.assertTrue((output_dir / "watchlist.yaml").exists())
        self.assertTrue((output_dir / "weekly_intelligence.json").exists())
        self.assertTrue((output_dir / "issue_brief.md").exists())
        self.assertTrue((output_dir / "publication_manifest.json").exists())

        watchlist_payload = json.loads((output_dir / "watchlist.yaml").read_text(encoding="utf-8"))
        self.assertEqual(watchlist_payload["schema_version"], server.PUBLICATION_SCHEMA_VERSION)
        self.assertIn("principle_context", watchlist_payload)
        self.assertEqual(len(watchlist_payload["watchlist"]), 2)
        self.assertEqual(watchlist_payload["watchlist"][0]["type"], "calendar")
        self.assertEqual(watchlist_payload["watchlist"][0]["tradeable"], True)
        self.assertIn("principle_scores", watchlist_payload["watchlist"][0])
        self.assertIn("principle_status", watchlist_payload["watchlist"][0])
        self.assertIn("principle_influences", watchlist_payload["watchlist"][0])
        self.assertIn("intelligence_context", watchlist_payload["watchlist"][0])
        self.assertEqual(watchlist_payload["watchlist"][1]["tradeable"], False)
        self.assertIn("Sugar #11 is not tradeable", watchlist_payload["watchlist"][1]["blocked_reason"])

        intelligence_payload = json.loads((output_dir / "weekly_intelligence.json").read_text(encoding="utf-8"))
        self.assertEqual(intelligence_payload["week_ended"], "2026-04-10")
        self.assertIn("issue_brief", intelligence_payload)

        issue_brief_md = (output_dir / "issue_brief.md").read_text(encoding="utf-8")
        self.assertIn("# SmartSpreads Issue Brief - 2026-04-10", issue_brief_md)
        self.assertIn("## Reference Rules", issue_brief_md)

        manifest = json.loads((output_dir / "publication_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["watchlist_count"], 2)
        self.assertIn("watchlist_yaml", manifest["files"])
        self.assertIn("publication_manifest_json", manifest["files"])

        with self.database.session() as session:
            newsletter = session.execute(
                select(Newsletter).where(Newsletter.week_ended == date(2026, 4, 10))
            ).scalar_one()
            publication_runs = session.execute(select(PublicationRun)).scalars().all()
            artifacts = session.execute(select(PublicationArtifact)).scalars().all()
            entries = session.execute(select(WatchlistEntry)).scalars().all()

            self.assertEqual(newsletter.issue_status, "published")
            self.assertEqual(len(publication_runs), 2)
            self.assertEqual(publication_runs[-1].publication_version, "published-1")
            self.assertEqual(len(artifacts), 4)
            self.assertTrue(all(entry.publication_state == "published" for entry in entries))

    def test_refresh_and_publish_issue_rebuilds_stale_brief_before_publishing(self) -> None:
        with self.database.session() as session:
            newsletter = session.execute(
                select(Newsletter).where(Newsletter.week_ended == date(2026, 4, 10))
            ).scalar_one()
            brief = session.execute(
                select(server.IssueBrief).where(server.IssueBrief.newsletter_id == newsletter.id)
            ).scalar_one()
            delta = session.execute(
                select(server.IssueDelta).where(server.IssueDelta.newsletter_id == newsletter.id)
            ).scalar_one()

            brief.key_themes_json = []
            brief.notable_risks_json = []
            brief.notable_opportunities_json = []
            brief.watchlist_summary_json = {"entry_count": 2}
            delta.summary_text = "stale summary"

        output_dir = self.base_dir / "refreshed-published"
        result = server.refresh_and_publish_issue(
            week_ended="2026-04-10",
            output_dir=str(output_dir),
            publication_version="published-refresh",
            published_by="unit-test",
        )

        self.assertEqual(result["refreshed"]["week_ended"], "2026-04-10")
        self.assertEqual(result["published"]["publication_version"], "published-refresh")

        intelligence_payload = json.loads((output_dir / "weekly_intelligence.json").read_text(encoding="utf-8"))
        issue_brief = intelligence_payload["issue_brief"]
        self.assertTrue(issue_brief["key_themes"])
        self.assertTrue(issue_brief["notable_risks"])
        self.assertTrue(issue_brief["notable_opportunities"])
        self.assertIn("blocked_count", issue_brief["watchlist_summary"])
        self.assertNotEqual(issue_brief["change_summary"]["summary_text"], "stale summary")

        with self.database.session() as session:
            newsletter = session.execute(
                select(Newsletter).where(Newsletter.week_ended == date(2026, 4, 10))
            ).scalar_one()
            brief = session.execute(
                select(server.IssueBrief).where(server.IssueBrief.newsletter_id == newsletter.id)
            ).scalar_one()
            self.assertTrue(brief.key_themes_json)
            self.assertIn("blocked_count", brief.watchlist_summary_json)

    def test_publish_issue_surfaces_support_metadata_for_manual_leg_symbols(self) -> None:
        with self.database.session() as session:
            session.add(
                SchwabFuturesCatalog(
                    symbol_root="/VX",
                    display_name="CBOE Volatility Index (VIX)",
                    category="Stock Indices",
                    options_tradable=False,
                    multiplier="$1,000",
                    minimum_tick_size="0.05 = $50",
                    settlement_type="Cash",
                    trading_hours="6 p.m. ET Sunday to 5 p.m. Friday",
                    is_micro=False,
                    stream_supported=False,
                    native_spread_support=False,
                    manual_legs_required=True,
                    support_notes="Manual legs required in TOS for this workflow.",
                    is_active=True,
                    metadata_json={},
                )
            )
            session.add(
                server.NewsletterCommodityCatalog(
                    newsletter_root="VX",
                    commodity_name="VIX",
                    preferred_schwab_root="/VX",
                    metadata_json={},
                )
            )
            newsletter = session.execute(
                select(Newsletter).where(Newsletter.week_ended == date(2026, 4, 10))
            ).scalar_one()
            session.add(
                WatchlistEntry(
                    newsletter_id=newsletter.id,
                    commodity_name="S&P 500 VIX",
                    spread_code="VXN26-VXU26",
                    side="SELL",
                    legs=2,
                    category="Index",
                    enter_date=date(2026, 4, 13),
                    exit_date=date(2026, 6, 28),
                    win_pct=100.0,
                    avg_profit=1179,
                    avg_best_profit=1500,
                    avg_worst_loss=-300,
                    avg_draw_down=-200,
                    apw_pct=10.0,
                    ridx=45.0,
                    five_year_corr=7,
                    trade_quality="Tier 1",
                    volatility_structure="Mid",
                    section_name="intra_commodity",
                    page_number=8,
                    raw_row="raw vix row",
                    metadata_json={},
                )
            )

        output_dir = self.base_dir / "published-support"
        result = server.publish_issue(
            week_ended="2026-04-10",
            output_dir=str(output_dir),
            publication_version="published-support",
            published_by="unit-test",
        )

        self.assertEqual(result["watchlist_count"], 3)
        watchlist_payload = json.loads((output_dir / "watchlist.yaml").read_text(encoding="utf-8"))
        vix_row = next(row for row in watchlist_payload["watchlist"] if row["spread_code"] == "VXN26-VXU26")
        self.assertEqual(vix_row["stream_supported"], False)
        self.assertEqual(vix_row["native_spread_support"], False)
        self.assertEqual(vix_row["manual_legs_required"], True)
        self.assertEqual(vix_row["support_notes"], ["Manual legs required in TOS for this workflow."])


if __name__ == "__main__":
    unittest.main()
