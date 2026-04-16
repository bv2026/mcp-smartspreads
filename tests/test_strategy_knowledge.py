from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from newsletter_mcp import server
from newsletter_mcp.database import Database


class StrategyKnowledgeTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        server.database.engine.dispose()

    def test_import_strategy_manual_populates_documents_sections_and_principles(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base_dir = Path(temp_dir.name)
        database = Database(f"sqlite:///{(base_dir / 'strategy.db').as_posix()}")
        database.create_schema()
        self.addCleanup(database.engine.dispose)

        strategy_path = base_dir / "strategy.pdf"
        strategy_path.write_bytes(b"%PDF-1.4\n% mock strategy manual\n")

        extracted = {
            "title": "Trading Commodity Spreads",
            "page_count": 12,
            "raw_text": "chapter text",
            "sections": [
                {
                    "part_number": 2,
                    "part_title": "Trade Quality",
                    "chapter_number": 8,
                    "chapter_title": "Structure Before Conviction",
                    "page_start": 41,
                    "page_end": 55,
                    "heading_path": "Part 2 > Trade Quality > Chapter 8 > Structure Before Conviction",
                    "body_text": "Structure matters.",
                    "summary_text": "Structure matters.",
                    "keywords": ["structure", "trade quality"],
                },
                {
                    "part_number": 3,
                    "part_title": "Trade Selection",
                    "chapter_number": 9,
                    "chapter_title": "Selectivity",
                    "page_start": 56,
                    "page_end": 70,
                    "heading_path": "Part 3 > Trade Selection > Chapter 9 > Selectivity",
                    "body_text": "Selectivity matters.",
                    "summary_text": "Selectivity matters.",
                    "keywords": ["selection"],
                },
                {
                    "part_number": 5,
                    "part_title": "Risk and Survivability",
                    "chapter_number": 16,
                    "chapter_title": "Margin",
                    "page_start": 120,
                    "page_end": 134,
                    "heading_path": "Part 5 > Risk and Survivability > Chapter 16 > Margin",
                    "body_text": "Margin matters.",
                    "summary_text": "Margin matters.",
                    "keywords": ["margin"],
                },
                {
                    "part_number": 6,
                    "part_title": "Framework",
                    "chapter_number": 23,
                    "chapter_title": "Inter-Commodity",
                    "page_start": 180,
                    "page_end": 190,
                    "heading_path": "Part 6 > Framework > Chapter 23 > Inter-Commodity",
                    "body_text": "Inter-commodity discipline matters.",
                    "summary_text": "Inter-commodity discipline matters.",
                    "keywords": ["inter-commodity"],
                },
            ],
        }

        with mock.patch.object(server, "database", database), mock.patch.object(
            server, "_extract_strategy_pdf", return_value=extracted
        ):
            imported = server.import_strategy_manual(str(strategy_path))
            self.assertEqual(imported["status"], "imported")
            self.assertEqual(imported["section_count"], 4)
            self.assertGreater(imported["principle_count"], 0)

            documents = server.list_strategy_documents()
            self.assertEqual(documents["count"], 1)
            self.assertEqual(documents["items"][0]["title"], "Trading Commodity Spreads")

            sections = server.list_strategy_sections()
            self.assertEqual(sections["count"], 4)
            self.assertEqual(sections["items"][0]["chapter_number"], 8)

            principles = server.list_strategy_principles(category="margin")
            self.assertEqual(principles["count"], 1)
            self.assertEqual(principles["items"][0]["principle_key"], "margin_as_survivability_constraint")

            updated = server.import_strategy_manual(str(strategy_path))
            self.assertEqual(updated["status"], "updated")
            self.assertEqual(updated["section_count"], 4)


if __name__ == "__main__":
    unittest.main()
