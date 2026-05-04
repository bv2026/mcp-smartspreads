from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from sqlalchemy import select

from newsletter_mcp import server
from newsletter_mcp.database import Database, Newsletter, WatchlistEntry
from newsletter_mcp.models import ParsedNewsletter, SectionSummary, WatchlistReference, WatchlistRow


def _make_row(
    *,
    commodity_name: str = "S&P 500 VIX",
    spread_code: str = "VXN26-VXU26",
    section_name: str = "intra_commodity",
    category: str = "Index",
    trade_quality: str | None = "Tier 1",
    ridx: float = 46.6,
) -> WatchlistRow:
    return WatchlistRow(
        commodity_name=commodity_name,
        spread_code=spread_code,
        side="SELL",
        legs=1,
        category=category,
        enter_date=date(2026, 4, 13),
        exit_date=date(2026, 6, 28),
        win_pct=100.0,
        avg_profit=1179,
        avg_best_profit=1402,
        avg_worst_loss=-210,
        avg_draw_down=-105,
        apw_pct=12.0,
        ridx=ridx,
        five_year_corr=96,
        portfolio=None,
        risk_level=None,
        trade_quality=trade_quality,
        volatility_structure="Mid",
        section_name=section_name,
        page_number=9,
        raw_row="raw row",
    )


def _make_parsed_newsletter(base_dir: Path) -> ParsedNewsletter:
    source_file = base_dir / "e2e-issue.pdf"
    source_file.write_bytes(b"pdf")
    return ParsedNewsletter(
        source_file=source_file,
        file_hash="e2e-hash",
        title="Week Ended 2026-04-10",
        week_ended=date(2026, 4, 10),
        raw_text="Raw text",
        metadata={"page_count": 12, "source_filename": source_file.name},
        overall_summary="This week focuses on volatility and grains.",
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
            _make_row(),
            _make_row(
                commodity_name="Sugar #11",
                spread_code="SBK26-SBV26",
                category="Food",
                trade_quality="Tier 3",
                ridx=28.0,
            ),
        ],
    )


class Phase1EndToEndTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        server.database.engine.dispose()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.database = Database(f"sqlite:///{(self.base_dir / 'e2e.db').as_posix()}")
        self.database.create_schema()
        self.addCleanup(self.database.engine.dispose)
        self.database_patch = mock.patch.object(server, "database", self.database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)

    def test_ingest_publish_and_load_through_schwab_file_contract(self) -> None:
        parsed = _make_parsed_newsletter(self.base_dir)
        ingest_result = server._save_parsed_newsletter(parsed)
        self.assertEqual(ingest_result["status"], "ingested")

        publish_dir = self.base_dir / "published"
        publish_result = server.publish_issue(
            week_ended="2026-04-10",
            output_dir=str(publish_dir),
            publication_version="published-e2e",
            published_by="test",
        )

        self.assertEqual(publish_result["watchlist_count"], 2)
        manifest_path = publish_dir / "publication_manifest.json"
        watchlist_path = publish_dir / "watchlist.yaml"
        intelligence_path = publish_dir / "weekly_intelligence.json"
        issue_brief_path = publish_dir / "issue_brief.md"
        validation_path = publish_dir / "publication_validation.json"
        self.assertTrue(manifest_path.exists())
        self.assertTrue(watchlist_path.exists())
        self.assertTrue(intelligence_path.exists())
        self.assertTrue(issue_brief_path.exists())
        self.assertTrue(validation_path.exists())

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["publication_version"], "published-e2e")
        self.assertEqual(manifest["watchlist_count"], 2)
        self.assertIn("publication_validation_json", manifest["files"])

        validation_report = json.loads(validation_path.read_text(encoding="utf-8"))
        self.assertEqual(validation_report["watchlist_count"], 2)
        self.assertTrue(validation_report["checks"]["has_entries"])

        schwab_config_path = Path(r"C:\work\schwab-mcp-file\src\schwab_mcp\config.py")
        spec = importlib.util.spec_from_file_location("schwab_file_config", schwab_config_path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        previous_watchlist_path = os.environ.get("SCHWAB_WATCHLIST_CONFIG")
        try:
            os.environ["SCHWAB_WATCHLIST_CONFIG"] = str(watchlist_path)
            schwab_watchlist = module.load_watchlist_config()
            schwab_metadata = module.load_watchlist_metadata()
        finally:
            if previous_watchlist_path is None:
                os.environ.pop("SCHWAB_WATCHLIST_CONFIG", None)
            else:
                os.environ["SCHWAB_WATCHLIST_CONFIG"] = previous_watchlist_path

        self.assertEqual(len(schwab_watchlist), 2)
        self.assertEqual(schwab_metadata["week_ending"], "2026-04-10")
        self.assertEqual(schwab_watchlist[0]["name"], "S&P 500 VIX")
        self.assertEqual(schwab_watchlist[0]["avg_value"], 1179)
        self.assertEqual(schwab_watchlist[0]["corr_5yr"], 96)
        self.assertEqual(schwab_watchlist[0]["vol"], "Mid")
        self.assertEqual(schwab_watchlist[1]["type"], "calendar")
        self.assertEqual(
            schwab_watchlist[1]["action"],
            "Review intra_commodity idea from 2026-04-10 newsletter.",
        )
        self.assertFalse(schwab_watchlist[1]["tradeable"])
        self.assertIn("Sugar #11 is not tradeable", schwab_watchlist[1]["blocked_reason"])

        with self.database.session() as session:
            newsletter = session.execute(select(Newsletter)).scalar_one()
            entries = session.execute(select(WatchlistEntry)).scalars().all()

            self.assertEqual(newsletter.issue_status, "published")
            self.assertEqual(len(entries), 2)
            self.assertTrue(all(entry.publication_state == "published" for entry in entries))

    def test_verify_newsletter_ingested_reports_missing_requested_issue(self) -> None:
        parsed = _make_parsed_newsletter(self.base_dir)
        server._save_parsed_newsletter(parsed)

        present = server.verify_newsletter_ingested("2026-04-10")
        self.assertTrue(present["is_ingested"])
        self.assertEqual(present["week_ended"], "2026-04-10")
        self.assertEqual(present["entry_count"], 2)
        self.assertEqual(present["section_counts"], {"intra_commodity": 2})

        missing = server.verify_newsletter_ingested("2026-05-01")
        self.assertFalse(missing["is_ingested"])
        self.assertEqual(missing["requested_week_ended"], "2026-05-01")
        self.assertEqual(missing["latest_ingested_week_ended"], "2026-04-10")
        self.assertIn("not ingested", missing["message"])
        self.assertNotIn("entry_count", missing)

        latest = server.verify_newsletter_ingested()
        self.assertTrue(latest["is_ingested"])
        self.assertEqual(latest["latest_ingested_week_ended"], "2026-04-10")
        self.assertEqual(latest["entry_count"], 2)

    def test_watchlist_serialization_includes_one_spread_reporting_expression(self) -> None:
        parsed = _make_parsed_newsletter(self.base_dir)
        parsed.watchlist_rows = [
            _make_row(
                commodity_name="Corn",
                spread_code="CZ26-2*CN27+CZ27",
                section_name="intra_commodity",
                category="Grain",
            )
        ]
        server._save_parsed_newsletter(parsed)

        result = server.get_watchlist("2026-04-10", include_reference=False)
        entry = result["entries"][0]

        self.assertEqual(entry["section_name"], "intra_commodity")
        self.assertEqual(entry["spread_type"], "butterfly")
        self.assertEqual(entry["spread_formula"], "CZ26 - 2*CN27 + CZ27")
        self.assertEqual(entry["spread_expression"], "SELL (CZ26 - 2*CN27 + CZ27)")
        self.assertIn("one spread", entry["reporting_rule"])

    def test_validated_watchlist_report_withholds_rows_on_contract_mismatch(self) -> None:
        parsed = _make_parsed_newsletter(self.base_dir)
        server._save_parsed_newsletter(parsed)

        valid = server.get_validated_watchlist_report(
            "2026-04-10",
            expected_entry_count=2,
            expected_intra_commodity_count=2,
            expected_inter_commodity_count=0,
        )
        self.assertTrue(valid["is_valid"])
        self.assertEqual(valid["actual"]["entry_count"], 2)
        self.assertEqual(len(valid["entries"]), 2)
        self.assertEqual(len(valid["entries_by_section"]["intra_commodity"]), 2)

        invalid = server.get_validated_watchlist_report(
            "2026-04-10",
            expected_entry_count=31,
            expected_intra_commodity_count=21,
            expected_inter_commodity_count=10,
        )
        self.assertFalse(invalid["is_valid"])
        self.assertEqual(invalid["entries"], [])
        self.assertEqual(invalid["entries_by_section"], {})
        self.assertEqual(invalid["mismatches"]["entry_count"], {"expected": 31, "actual": 2})


if __name__ == "__main__":
    unittest.main()
