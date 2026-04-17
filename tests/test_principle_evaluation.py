from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from sqlalchemy import select

from newsletter_mcp import server
from newsletter_mcp.database import (
    Database,
    EvaluationRun,
    Newsletter,
    PrincipleEvaluationRecord,
    StrategyDocument,
    StrategyPrinciple,
    WatchlistDecision,
    WatchlistEntry,
)
from newsletter_mcp.models import ParsedNewsletter, SectionSummary, WatchlistReference, WatchlistRow


def _make_row(
    *,
    commodity_name: str = "Corn",
    spread_code: str = "CU26-CZ26",
    section_name: str = "intra_commodity",
    trade_quality: str | None = "Tier 1",
    ridx: float = 45.0,
    win_pct: float = 88.0,
) -> WatchlistRow:
    return WatchlistRow(
        commodity_name=commodity_name,
        spread_code=spread_code,
        side="SELL",
        legs=1,
        category="Grain",
        enter_date=date(2026, 4, 17),
        exit_date=date(2026, 8, 30),
        win_pct=win_pct,
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


def _make_parsed_newsletter(base_dir: Path, *, week_ended: date, file_hash: str, rows: list[WatchlistRow]) -> ParsedNewsletter:
    source_file = base_dir / f"issue-{week_ended.isoformat()}.pdf"
    source_file.write_bytes(b"pdf")
    return ParsedNewsletter(
        source_file=source_file,
        file_hash=file_hash,
        title=f"Week Ended {week_ended.isoformat()}",
        week_ended=week_ended,
        raw_text="Raw text",
        metadata={"page_count": 12, "source_filename": source_file.name},
        overall_summary="Weekly summary",
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
        watchlist_rows=rows,
    )


class PrincipleEvaluationTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        server.database.engine.dispose()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.database = Database(f"sqlite:///{(self.base_dir / 'principles.db').as_posix()}")
        self.database.create_schema()
        self.addCleanup(self.database.engine.dispose)
        self.database_patch = mock.patch.object(server, "database", self.database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self._seed_strategy_principles()

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

    def test_ingestion_populates_principle_evaluation_metadata(self) -> None:
        prior = _make_parsed_newsletter(
            self.base_dir,
            week_ended=date(2026, 4, 3),
            file_hash="prior-hash",
            rows=[_make_row()],
        )
        current = _make_parsed_newsletter(
            self.base_dir,
            week_ended=date(2026, 4, 10),
            file_hash="current-hash",
            rows=[_make_row(), _make_row(commodity_name="Corn", spread_code="CU26-CN26", trade_quality="Tier 3")],
        )

        server._save_parsed_newsletter(prior)
        server._save_parsed_newsletter(current)

        with self.database.session() as session:
            newsletter = session.execute(
                select(Newsletter).where(Newsletter.week_ended == date(2026, 4, 10))
            ).scalar_one()
            entries = session.execute(
                select(WatchlistEntry).where(WatchlistEntry.newsletter_id == newsletter.id).order_by(WatchlistEntry.id)
            ).scalars().all()

            first_eval = entries[0].metadata_json.get("principle_evaluation")
            second_eval = entries[1].metadata_json.get("principle_evaluation")
            self.assertEqual(first_eval["evaluation_version"], "phase3-v1")
            self.assertIn("structure_before_conviction", first_eval["principle_scores"])
            self.assertIn("portfolio_fit_over_isolated_trade_appeal", first_eval["deferred_principles"])
            self.assertTrue(entries[0].tradeable)
            self.assertFalse(entries[1].tradeable)
            self.assertIsNotNone(second_eval["blocked_reason"])
            runs = session.execute(select(EvaluationRun).order_by(EvaluationRun.id)).scalars().all()
            principle_rows = session.execute(select(PrincipleEvaluationRecord)).scalars().all()
            decisions = session.execute(select(WatchlistDecision).order_by(WatchlistDecision.id)).scalars().all()
            self.assertEqual(len(runs), 2)
            self.assertEqual(runs[-1].run_type, "sunday_publish")
            self.assertEqual(len(principle_rows), 3 * len(server.STRATEGY_PRINCIPLE_SEED))
            self.assertEqual(len(decisions), 3)
            self.assertEqual(decisions[-2].final_outcome, "deferred")
            self.assertEqual(decisions[-1].final_outcome, "blocked")


if __name__ == "__main__":
    unittest.main()
