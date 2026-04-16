from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import select

from newsletter_mcp import server
from newsletter_mcp.database import Database, SchwabFuturesCatalog


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


if __name__ == "__main__":
    unittest.main()
