from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from sqlalchemy import select

from newsletter_mcp import server
from newsletter_mcp.database import ContractMonthCode, Database, Newsletter, NewsletterCommodityCatalog, SchwabFuturesCatalog


CATALOG_CSV = """Micros,,,,,,
,Symbol,Options Tradable on thinkorswim,Multiplier,Minimum Tick Size,Settlement,Trading Days/Hours
Micro Gold,/MGC,No,$10,0.10 = $1.00,Physical,6 p.m. ET Sunday to 5 p.m. Friday
View Less,,,,,,
Stock Indices,,,,,,
,Symbol,Options Tradable on thinkorswim,Multiplier,Minimum Tick Size,Settlement,Trading Days/Hours
CBOE Volatility Index (VIX),/VX,No,"$1,000",0.05 = $50,Cash,6 p.m. ET Sunday to 5 p.m. Friday
Mini CBOE Volatility Index,/VXM,No,$100,0.01 = $1.00,Cash,6 p.m. ET Sunday to 5 p.m. Friday
"""


class SymbolCatalogTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        server.database.engine.dispose()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)

        self.database = Database(f"sqlite:///{(self.base_dir / 'catalog.db').as_posix()}")
        self.database.create_schema()
        self.addCleanup(self.database.engine.dispose)

        self.database_patch = mock.patch.object(server, "database", self.database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)

        self.csv_path = self.base_dir / "schwab-futures.csv"
        self.csv_path.write_text(CATALOG_CSV, encoding="utf-8")

    def test_import_schwab_futures_catalog_creates_rows_and_categories(self) -> None:
        result = server.import_schwab_futures_catalog(str(self.csv_path))

        self.assertEqual(result["row_count"], 3)
        self.assertEqual(result["imported_count"], 3)
        self.assertEqual(result["updated_count"], 0)
        self.assertEqual(result["category_counts"]["Micros"], 1)
        self.assertEqual(result["category_counts"]["Stock Indices"], 2)

        with self.database.session() as session:
            rows = session.execute(
                select(SchwabFuturesCatalog).order_by(SchwabFuturesCatalog.symbol_root)
            ).scalars().all()

        self.assertEqual([row.symbol_root for row in rows], ["/MGC", "/VX", "/VXM"])
        self.assertTrue(rows[0].is_micro)
        self.assertFalse(rows[1].is_micro)
        self.assertEqual(rows[1].category, "Stock Indices")
        self.assertEqual(rows[1].settlement_type, "Cash")

    def test_upsert_schwab_futures_support_updates_operational_flags(self) -> None:
        server.import_schwab_futures_catalog(str(self.csv_path))

        result = server.upsert_schwab_futures_support(
            "/VXM",
            stream_supported=False,
            native_spread_support=False,
            manual_legs_required=True,
            support_notes="Manual legs required in TOS for this workflow.",
        )

        self.assertEqual(result["updated"], "/VXM")
        self.assertEqual(result["row"]["stream_supported"], False)
        self.assertEqual(result["row"]["native_spread_support"], False)
        self.assertEqual(result["row"]["manual_legs_required"], True)
        self.assertEqual(result["row"]["support_notes"], "Manual legs required in TOS for this workflow.")

    def test_list_schwab_futures_catalog_filters_by_category(self) -> None:
        server.import_schwab_futures_catalog(str(self.csv_path))

        result = server.list_schwab_futures_catalog(category="Stock Indices")

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["categories"]["Micros"], 1)
        self.assertEqual(result["categories"]["Stock Indices"], 2)
        self.assertEqual(
            [row["symbol_root"] for row in result["rows"]],
            ["/VX", "/VXM"],
        )

    def test_upsert_newsletter_commodity_mapping_persists_and_lists(self) -> None:
        result = server.upsert_newsletter_commodity_mapping(
            newsletter_root="KW",
            commodity_name="KC Wheat",
            preferred_schwab_root="/KE",
            category="Grain",
            mapping_confidence=0.95,
            mapping_notes="Matches Schwab KC wheat root.",
        )

        self.assertEqual(result["action"], "created")
        self.assertEqual(result["mapping"]["preferred_schwab_root"], "/KE")

        listing = server.list_newsletter_commodity_catalog()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["rows"][0]["newsletter_root"], "KW")
        self.assertEqual(listing["rows"][0]["preferred_schwab_root"], "/KE")

    def test_contract_resolution_prefers_newsletter_mapping_when_catalog_exists(self) -> None:
        server.import_schwab_futures_catalog(str(self.csv_path))
        server.upsert_newsletter_commodity_mapping(
            newsletter_root="VX",
            commodity_name="VIX",
            preferred_schwab_root="/VXM",
            category="Index",
            mapping_notes="Prefer mini VIX for Schwab execution.",
        )

        tos_symbol, blocked_reason, root = server._tos_symbol_for_contract("VXN26")

        self.assertEqual(root, "VX")
        self.assertIsNone(blocked_reason)
        self.assertEqual(tos_symbol, "/VXMN26")

    def test_parse_spread_legs_includes_support_flags(self) -> None:
        server.import_schwab_futures_catalog(str(self.csv_path))
        server.upsert_schwab_futures_support(
            "/VXM",
            stream_supported=False,
            native_spread_support=False,
            manual_legs_required=True,
            support_notes="Manual legs required in TOS for this workflow.",
        )
        server.upsert_newsletter_commodity_mapping(
            newsletter_root="VX",
            commodity_name="VIX",
            preferred_schwab_root="/VXM",
            category="Index",
        )

        legs = server._parse_spread_legs("VXN26-VXU26")

        self.assertEqual([leg["tos_symbol"] for leg in legs], ["/VXMN26", "/VXMU26"])
        self.assertEqual([leg["manual_legs_required"] for leg in legs], [True, True])
        self.assertEqual([leg["native_spread_support"] for leg in legs], [False, False])

    def test_parse_newsletter_commodity_rows_extracts_details(self) -> None:
        raw_text = (
            "Smart Spreads Commodity  Details Month Symbol Commodity Exchange $/Unit "
            "Newsletter / Pit Symbol Globex Symbol "
            "Crude Oil (WTI) NYMEX 1,000 CL CL "
            "Hard Red Wheat KCBT 50 KW KE "
            "Feeder Cattle CME 500 FC GF "
            "What to Expect From"
        )

        rows = server._parse_newsletter_commodity_rows(raw_text)

        self.assertEqual(
            [row["newsletter_root"] for row in rows],
            ["CL", "KW", "FC"],
        )
        self.assertEqual(rows[1]["preferred_schwab_root"], "/KE")
        self.assertEqual(rows[2]["preferred_schwab_root"], "/GF")
        self.assertEqual(rows[2]["policy_block_reason"], "Feeder Cattle is in the doghouse and should never be traded.")

    def test_import_newsletter_commodity_catalog_from_issue(self) -> None:
        with self.database.session() as session:
            session.add(
                Newsletter(
                    source_file="issue.pdf",
                    file_hash="issue-hash",
                    title="Week Ended 2026-04-10",
                    week_ended=date(2026, 4, 10),
                    raw_text=(
                        "Commodity  Details Month Symbol Commodity Exchange $/Unit "
                        "Newsletter / Pit Symbol Globex Symbol "
                        "Crude Oil (WTI) NYMEX 1,000 CL CL "
                        "Hard Red Wheat KCBT 50 KW KE "
                        "Volatility Index CBOT 1,000 VX VX "
                        "What to Expect From"
                    ),
                    overall_summary="summary",
                    metadata_json={},
                )
            )

        result = server.import_newsletter_commodity_catalog("2026-04-10")

        self.assertEqual(result["row_count"], 3)
        self.assertEqual(result["imported_count"], 3)

        with self.database.session() as session:
            rows = session.execute(
                select(NewsletterCommodityCatalog).order_by(NewsletterCommodityCatalog.newsletter_root)
            ).scalars().all()

        self.assertEqual([row.newsletter_root for row in rows], ["CL", "KW", "VX"])
        self.assertEqual(rows[1].globex_symbol_root, "/KE")
        self.assertEqual(rows[1].broker_symbol_root, "/KE")
        self.assertEqual(rows[1].preferred_schwab_root, "/KE")
        self.assertEqual(rows[1].source_issue_week, date(2026, 4, 10))

    def test_parse_contract_month_codes_extracts_full_calendar(self) -> None:
        raw_text = (
            "Commodity  Details Month Symbol "
            "January F February G March H April J May K June M "
            "July N August Q September U October V November X December Z "
            "Commodity Exchange $/Unit "
            "Crude Oil (WTI) NYMEX 1,000 CL CL "
            "What to Expect From"
        )

        rows = server._parse_contract_month_codes(raw_text)

        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0], {"month_code": "F", "month_name": "January", "sort_order": 1})
        self.assertEqual(rows[-1], {"month_code": "Z", "month_name": "December", "sort_order": 12})

    def test_import_contract_month_codes_from_issue(self) -> None:
        with self.database.session() as session:
            session.add(
                Newsletter(
                    source_file="months.pdf",
                    file_hash="months-hash",
                    title="Week Ended 2026-04-10",
                    week_ended=date(2026, 4, 10),
                    raw_text=(
                        "Commodity  Details Month Symbol "
                        "January F February G March H April J May K June M "
                        "July N August Q September U October V November X December Z "
                        "Commodity Exchange $/Unit "
                        "Crude Oil (WTI) NYMEX 1,000 CL CL "
                        "What to Expect From"
                    ),
                    overall_summary="summary",
                    metadata_json={},
                )
            )

        result = server.import_contract_month_codes("2026-04-10")

        self.assertEqual(result["row_count"], 12)
        self.assertEqual(result["imported_count"], 12)

        listing = server.list_contract_month_codes()
        self.assertEqual(listing["count"], 12)
        self.assertEqual(listing["rows"][0]["month_code"], "F")
        self.assertEqual(listing["rows"][0]["month_name"], "January")

        with self.database.session() as session:
            stored = session.execute(
                select(ContractMonthCode).where(ContractMonthCode.month_code == "U")
            ).scalar_one()
        self.assertEqual(stored.month_name, "September")


if __name__ == "__main__":
    unittest.main()
