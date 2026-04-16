from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from newsletter_mcp import server
from newsletter_mcp.database import Database, Newsletter, WatchlistEntry


def _make_newsletter(*, week_ended: date, source_file: str) -> Newsletter:
    return Newsletter(
        source_file=source_file,
        file_hash=f"hash-{week_ended.isoformat()}",
        title=f"Week Ended {week_ended.isoformat()}",
        week_ended=week_ended,
        raw_text="raw text",
        overall_summary="summary",
        metadata_json={},
    )


def _make_watchlist_entry(
    *,
    newsletter_id: int,
    commodity_name: str,
    spread_code: str,
    enter_date: date,
    exit_date: date,
    section_name: str = "intra_commodity",
    trade_quality: str | None = "Tier 1",
) -> WatchlistEntry:
    return WatchlistEntry(
        newsletter_id=newsletter_id,
        commodity_name=commodity_name,
        spread_code=spread_code,
        side="SELL",
        legs=2,
        category="Grain",
        enter_date=enter_date,
        exit_date=exit_date,
        win_pct=90.0,
        avg_profit=500,
        avg_best_profit=700,
        avg_worst_loss=-200,
        avg_draw_down=-100,
        apw_pct=10.0,
        ridx=35.0,
        five_year_corr=4,
        portfolio=None,
        risk_level=None,
        trade_quality=trade_quality,
        volatility_structure="High",
        section_name=section_name,
        page_number=8,
        raw_row="row",
        metadata_json={},
    )


class ExitScheduleResolverTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        server.database.engine.dispose()

    def test_resolve_open_position_exit_schedule_uses_newsletter_history(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base_dir = Path(temp_dir.name)
        database = Database(f"sqlite:///{(base_dir / 'exit-schedule.db').as_posix()}")
        database.create_schema()
        self.addCleanup(database.engine.dispose)

        database_patch = mock.patch.object(server, "database", database)
        database_patch.start()
        self.addCleanup(database_patch.stop)

        with database.session() as session:
            older = _make_newsletter(week_ended=date(2026, 4, 3), source_file="older.pdf")
            current = _make_newsletter(week_ended=date(2026, 4, 10), source_file="current.pdf")
            session.add_all([older, current])
            session.flush()
            session.add_all(
                [
                    _make_watchlist_entry(
                        newsletter_id=older.id,
                        commodity_name="KC Wheat",
                        spread_code="KWU26-KWX26",
                        enter_date=date(2026, 4, 5),
                        exit_date=date(2026, 4, 20),
                    ),
                    _make_watchlist_entry(
                        newsletter_id=current.id,
                        commodity_name="Gold",
                        spread_code="GCQ26-GCZ26",
                        enter_date=date(2026, 4, 12),
                        exit_date=date(2026, 4, 16),
                    ),
                ]
            )

        result = server.resolve_open_position_exit_schedule(
            positions=[
                {
                    "id": "gold",
                    "name": "Gold calendar",
                    "legs": ["/GCQ26", "/GCZ26"],
                },
                {
                    "id": "wheat",
                    "name": "KC Wheat calendar",
                    "legs": ["/KEU26", "/KEX26"],
                },
                {
                    "id": "unknown",
                    "name": "Unknown spread",
                    "legs": ["/CLM26", "/CLZ26"],
                },
            ],
            as_of="2026-04-16",
        )

        self.assertEqual(result["current_issue_week_ended"], "2026-04-10")
        self.assertEqual(result["urgency_counts"]["due_today"], 1)
        self.assertEqual(result["urgency_counts"]["due_this_week"], 1)
        self.assertEqual(result["urgency_counts"]["unknown"], 1)

        gold, wheat, unknown = result["positions"]

        self.assertTrue(gold["matched"])
        self.assertEqual(gold["alignment_status"], "current_watchlist")
        self.assertEqual(gold["exit_date"], "2026-04-16")
        self.assertEqual(gold["urgency_bucket"], "due_today")

        self.assertTrue(wheat["matched"])
        self.assertEqual(wheat["alignment_status"], "legacy_carryover")
        self.assertEqual(wheat["matched_week_ended"], "2026-04-03")
        self.assertEqual(wheat["exit_date"], "2026-04-20")
        self.assertEqual(wheat["urgency_bucket"], "due_this_week")

        self.assertFalse(unknown["matched"])
        self.assertEqual(unknown["alignment_status"], "unmatched")
        self.assertIsNone(unknown["exit_date"])
        self.assertEqual(unknown["urgency_bucket"], "unknown")

    def test_resolve_open_position_exit_schedule_honors_expanded_butterfly_legs(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base_dir = Path(temp_dir.name)
        database = Database(f"sqlite:///{(base_dir / 'exit-schedule-bfly.db').as_posix()}")
        database.create_schema()
        self.addCleanup(database.engine.dispose)

        database_patch = mock.patch.object(server, "database", database)
        database_patch.start()
        self.addCleanup(database_patch.stop)

        with database.session() as session:
            current = _make_newsletter(week_ended=date(2026, 4, 3), source_file="current.pdf")
            session.add(current)
            session.flush()
            session.add(
                _make_watchlist_entry(
                    newsletter_id=current.id,
                    commodity_name="Corn",
                    spread_code="CU26-2*CZ26+CH27",
                    enter_date=date(2026, 4, 9),
                    exit_date=date(2026, 8, 31),
                    trade_quality="Tier 2",
                )
            )

        result = server.resolve_open_position_exit_schedule(
            positions=[
                {
                    "id": "zc_bfly",
                    "name": "Corn butterfly",
                    "legs": ["/ZCU26", "/ZCZ26", "/ZCH27"],
                    "expanded_legs": ["/ZCU26", "/ZCZ26", "/ZCZ26", "/ZCH27"],
                }
            ],
            as_of="2026-04-16",
        )

        self.assertEqual(result["urgency_counts"]["later"], 1)
        match = result["positions"][0]
        self.assertTrue(match["matched"])
        self.assertEqual(match["commodity_name"], "Corn")
        self.assertEqual(match["exit_date"], "2026-08-31")
        self.assertEqual(match["alignment_status"], "current_watchlist")

    def test_resolve_open_position_exit_schedule_accepts_flat_leg_rows(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base_dir = Path(temp_dir.name)
        database = Database(f"sqlite:///{(base_dir / 'exit-schedule-flat.db').as_posix()}")
        database.create_schema()
        self.addCleanup(database.engine.dispose)

        database_patch = mock.patch.object(server, "database", database)
        database_patch.start()
        self.addCleanup(database_patch.stop)

        with database.session() as session:
            older = _make_newsletter(week_ended=date(2026, 4, 3), source_file="older.pdf")
            current = _make_newsletter(week_ended=date(2026, 4, 10), source_file="current.pdf")
            session.add_all([older, current])
            session.flush()
            session.add_all(
                [
                    _make_watchlist_entry(
                        newsletter_id=current.id,
                        commodity_name="Gold",
                        spread_code="GCQ26-GCZ26",
                        enter_date=date(2026, 4, 12),
                        exit_date=date(2026, 7, 5),
                    ),
                    _make_watchlist_entry(
                        newsletter_id=older.id,
                        commodity_name="Corn",
                        spread_code="CU26-2*CZ26+CH27",
                        enter_date=date(2026, 4, 9),
                        exit_date=date(2026, 8, 31),
                        trade_quality="Tier 2",
                    ),
                ]
            )

        result = server.resolve_open_position_exit_schedule(
            positions=[
                {"symbol": "/GCQ26", "quantity": 1, "spread_id": "gc_calendar_1", "spread_name": "Gold"},
                {"symbol": "/GCZ26", "quantity": 1, "spread_id": "gc_calendar_1", "spread_name": "Gold"},
                {"symbol": "/ZCU26", "quantity": 1, "spread_id": "zc_butterfly_1", "spread_name": "Corn"},
                {"symbol": "/ZCZ26", "quantity": 2, "spread_id": "zc_butterfly_1", "spread_name": "Corn"},
                {"symbol": "/ZCH27", "quantity": 1, "spread_id": "zc_butterfly_1", "spread_name": "Corn"},
            ],
            as_of="2026-04-16",
        )

        self.assertEqual(result["position_count"], 2)
        self.assertEqual(result["urgency_counts"]["later"], 2)
        gold, corn = result["positions"]
        self.assertTrue(gold["matched"])
        self.assertEqual(gold["exit_date"], "2026-07-05")
        self.assertTrue(corn["matched"])
        self.assertEqual(corn["exit_date"], "2026-08-31")

    def test_get_daily_exit_schedule_accepts_schwab_futures_positions_payload(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base_dir = Path(temp_dir.name)
        database = Database(f"sqlite:///{(base_dir / 'exit-schedule-daily.db').as_posix()}")
        database.create_schema()
        self.addCleanup(database.engine.dispose)

        database_patch = mock.patch.object(server, "database", database)
        database_patch.start()
        self.addCleanup(database_patch.stop)

        with database.session() as session:
            older = _make_newsletter(week_ended=date(2026, 4, 3), source_file="older.pdf")
            current = _make_newsletter(week_ended=date(2026, 4, 10), source_file="current.pdf")
            session.add_all([older, current])
            session.flush()
            session.add_all(
                [
                    _make_watchlist_entry(
                        newsletter_id=current.id,
                        commodity_name="Gold",
                        spread_code="GCQ26-GCZ26",
                        enter_date=date(2026, 4, 12),
                        exit_date=date(2026, 7, 5),
                    ),
                    _make_watchlist_entry(
                        newsletter_id=older.id,
                        commodity_name="Corn",
                        spread_code="CU26-2*CZ26+CH27",
                        enter_date=date(2026, 4, 9),
                        exit_date=date(2026, 8, 31),
                        trade_quality="Tier 2",
                    ),
                ]
            )

        result = server.get_daily_exit_schedule(
            schwab_futures_positions={
                "futures_legs": [
                    {"symbol": "/GCQ26", "quantity": 1, "spread_id": "gc_calendar_1", "spread_name": "Gold"},
                    {"symbol": "/GCZ26", "quantity": 1, "spread_id": "gc_calendar_1", "spread_name": "Gold"},
                    {"symbol": "/ZCU26", "quantity": 1, "spread_id": "zc_butterfly_1", "spread_name": "Corn"},
                    {"symbol": "/ZCZ26", "quantity": 2, "spread_id": "zc_butterfly_1", "spread_name": "Corn"},
                    {"symbol": "/ZCH27", "quantity": 1, "spread_id": "zc_butterfly_1", "spread_name": "Corn"},
                ],
                "spreads": [
                    {
                        "id": "gc_calendar_1",
                        "name": "Gold Calendar",
                        "type": "calendar",
                        "entry_value": -72.2,
                        "current_value": -71.25,
                        "spread_pl": 0.95,
                        "marks_live": False,
                    },
                    {
                        "id": "zc_butterfly_1",
                        "name": "Corn Butterfly",
                        "type": "butterfly",
                        "entry_value": -2.0,
                        "current_value": -4.875,
                        "spread_pl": -2.875,
                        "marks_live": False,
                    },
                ],
            },
            as_of="2026-04-16",
        )

        self.assertEqual(result["position_count"], 2)
        gold, corn = result["positions"]
        self.assertEqual(gold["exit_date"], "2026-07-05")
        self.assertEqual(gold["current_value"], -71.25)
        self.assertEqual(gold["spread_type"], "calendar")
        self.assertEqual(corn["exit_date"], "2026-08-31")
        self.assertEqual(corn["entry_value"], -2.0)
        self.assertEqual(corn["spread_type"], "butterfly")


if __name__ == "__main__":
    unittest.main()
