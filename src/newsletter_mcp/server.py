from __future__ import annotations

import csv
from collections import Counter
from datetime import date, datetime
import json
from io import StringIO
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import desc, select

from .config import Settings
from .database import (
    Database,
    IssueBrief,
    IssueDelta,
    Newsletter,
    NewsletterSection,
    ParserRun,
    PublicationRun,
    WatchlistEntry,
    WatchlistReferenceRecord,
)
from .parser import parse_newsletter


PARSER_VERSION = "phase1-v1"
settings = Settings.from_env()
database = Database(settings.database_url)
database.create_schema()
mcp = FastMCP("newsletter-mcp")


def _seed_record(parsed) -> dict[str, Any]:
    return {
        "source_file": str(parsed.source_file),
        "file_hash": parsed.file_hash,
        "title": parsed.title,
        "week_ended": parsed.week_ended,
        "raw_text": parsed.raw_text,
        "overall_summary": parsed.overall_summary,
        "metadata_json": parsed.metadata,
        "issue_code": parsed.source_file.stem,
        "issue_version": None,
        "issue_status": "validated",
        "page_count": parsed.metadata.get("page_count"),
        "source_modified_at": datetime.fromtimestamp(parsed.source_file.stat().st_mtime),
    }


def _normalize_key_part(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized


def _build_entry_key(week_ended: date, row: Any) -> str:
    return "|".join(
        [
            week_ended.isoformat(),
            _normalize_key_part(row.section_name),
            _normalize_key_part(row.commodity_name),
            _normalize_key_part(row.spread_code),
            row.side.lower(),
        ]
    )


def _classify_section_type(section_name: str) -> str:
    name = section_name.lower()
    if "watch list" in name:
        return "watchlist_page"
    if "trade calendar" in name:
        return "trade_calendar"
    if "margin summary" in name:
        return "margin_summary"
    if "macro" in name:
        return "macro_commentary"
    return "article"


def _summarize_watchlist_rows(rows: list[Any]) -> dict[str, Any]:
    section_counts = Counter(row.section_name for row in rows)
    quality_counts = Counter(row.trade_quality or row.portfolio or "unclassified" for row in rows)
    return {
        "entry_count": len(rows),
        "section_counts": dict(section_counts),
        "classification_counts": dict(quality_counts),
    }


def _serialize_entry_delta(current: WatchlistEntry, previous: WatchlistEntry) -> dict[str, Any]:
    changed_fields: list[str] = []
    for field_name in ("side", "enter_date", "exit_date", "trade_quality", "risk_level", "volatility_structure"):
        if getattr(current, field_name) != getattr(previous, field_name):
            changed_fields.append(field_name)

    return {
        "entry_key": current.entry_key,
        "commodity_name": current.commodity_name,
        "spread_code": current.spread_code,
        "changed_fields": changed_fields,
        "current": _serialize_watchlist_entry(current),
        "previous": _serialize_watchlist_entry(previous),
    }


def _compute_issue_delta(
    current_entries: list[WatchlistEntry],
    previous_entries: list[WatchlistEntry],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    current_map = {entry.entry_key: entry for entry in current_entries if entry.entry_key}
    previous_map = {entry.entry_key: entry for entry in previous_entries if entry.entry_key}

    added_keys = sorted(set(current_map) - set(previous_map))
    removed_keys = sorted(set(previous_map) - set(current_map))
    changed_keys = sorted(
        key
        for key in set(current_map) & set(previous_map)
        if any(
            getattr(current_map[key], field_name) != getattr(previous_map[key], field_name)
            for field_name in ("side", "enter_date", "exit_date", "trade_quality", "risk_level", "volatility_structure")
        )
    )

    added = [_serialize_watchlist_entry(current_map[key]) for key in added_keys]
    removed = [_serialize_watchlist_entry(previous_map[key]) for key in removed_keys]
    changed = [_serialize_entry_delta(current_map[key], previous_map[key]) for key in changed_keys]

    summary = (
        f"Added {len(added)} entries, removed {len(removed)} entries, "
        f"and changed {len(changed)} carried entries versus the prior issue."
    )
    return added, removed, changed, summary


def _seed_phase1_records(session: Any, newsletter: Newsletter) -> dict[str, Any]:
    parser_run = session.execute(
        select(ParserRun).where(ParserRun.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    if parser_run is None:
        parser_run = ParserRun(
            newsletter_id=newsletter.id,
            parser_version=PARSER_VERSION,
            status="completed",
            run_started_at=newsletter.ingested_at,
            run_completed_at=newsletter.ingested_at,
            page_count_detected=newsletter.page_count or newsletter.metadata_json.get("page_count"),
            pages_parsed=newsletter.page_count or newsletter.metadata_json.get("page_count"),
            watchlist_entry_count=len(newsletter.watchlist_entries),
            section_count=len(newsletter.sections),
            warning_count=0,
            warnings_json=[],
            metrics_json={
                "has_watchlist_reference": newsletter.watchlist_reference is not None,
                "source_filename": Path(newsletter.source_file).name,
                "backfilled": True,
            },
        )
        session.add(parser_run)
        session.flush()

    if not newsletter.issue_status:
        newsletter.issue_status = "validated"
    if newsletter.page_count is None:
        newsletter.page_count = newsletter.metadata_json.get("page_count")

    for section in newsletter.sections:
        if section.parser_run_id is None:
            section.parser_run_id = parser_run.id
        if section.section_type is None:
            section.section_type = _classify_section_type(section.name)
        if section.extraction_confidence is None:
            section.extraction_confidence = 0.95
        if section.metadata_json is None:
            section.metadata_json = {}

    for entry in newsletter.watchlist_entries:
        if entry.entry_key is None:
            entry.entry_key = _build_entry_key(newsletter.week_ended, entry)
        if entry.parser_run_id is None:
            entry.parser_run_id = parser_run.id
        if entry.publication_state is None:
            entry.publication_state = "candidate"
        if entry.metadata_json is None:
            entry.metadata_json = {}

    if newsletter.watchlist_reference is not None:
        reference = newsletter.watchlist_reference
        if reference.parser_run_id is None:
            reference.parser_run_id = parser_run.id
        if reference.reference_version is None:
            reference.reference_version = "v1"
        if reference.metadata_json is None:
            reference.metadata_json = {}

    session.flush()

    previous_newsletter = _get_previous_newsletter(session, newsletter.week_ended)
    previous_entries = previous_newsletter.watchlist_entries if previous_newsletter is not None else []
    added_entries, removed_entries, changed_entries, delta_summary = _compute_issue_delta(
        list(newsletter.watchlist_entries),
        list(previous_entries),
    )

    issue_brief = session.execute(
        select(IssueBrief).where(IssueBrief.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    if issue_brief is None:
        session.add(
            IssueBrief(
                newsletter_id=newsletter.id,
                parser_run_id=parser_run.id,
                brief_status="draft",
                headline=newsletter.title,
                executive_summary=newsletter.overall_summary,
                key_themes_json=[],
                notable_risks_json=[],
                notable_opportunities_json=[],
                watchlist_summary_json=_summarize_watchlist_rows(newsletter.watchlist_entries),
                change_summary_json={
                    "added_count": len(added_entries),
                    "removed_count": len(removed_entries),
                    "changed_count": len(changed_entries),
                },
            )
        )

    issue_delta = session.execute(
        select(IssueDelta).where(IssueDelta.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    if issue_delta is None:
        session.add(
            IssueDelta(
                newsletter_id=newsletter.id,
                previous_newsletter_id=previous_newsletter.id if previous_newsletter is not None else None,
                delta_status="generated",
                added_entries_json=added_entries,
                removed_entries_json=removed_entries,
                changed_entries_json=changed_entries,
                summary_text=delta_summary if previous_newsletter is not None else "No prior issue available for comparison.",
            )
        )

    publication_run = session.execute(
        select(PublicationRun)
        .where(PublicationRun.newsletter_id == newsletter.id)
        .order_by(desc(PublicationRun.created_at))
    ).scalars().first()
    if publication_run is None:
        session.add(
            PublicationRun(
                newsletter_id=newsletter.id,
                publication_version="draft-1",
                status="draft",
                manifest_json={
                    "week_ended": newsletter.week_ended.isoformat(),
                    "entry_count": len(newsletter.watchlist_entries),
                    "backfilled": True,
                },
            )
        )

    return {
        "parser_run_id": parser_run.id,
        "delta_summary": delta_summary if previous_newsletter is not None else None,
    }


def _get_previous_newsletter(session: Any, current_week_ended: date) -> Newsletter | None:
    stmt = (
        select(Newsletter)
        .where(Newsletter.week_ended < current_week_ended)
        .order_by(desc(Newsletter.week_ended))
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _save_parsed_newsletter(parsed) -> dict[str, Any]:
    with database.session() as session:
        existing = session.execute(
            select(Newsletter).where(Newsletter.file_hash == parsed.file_hash)
        ).scalar_one_or_none()
        if existing is not None:
            return {
                "status": "skipped",
                "week_ended": existing.week_ended.isoformat(),
                "source_file": existing.source_file,
                "reason": "already_ingested",
            }

        newsletter = Newsletter(**_seed_record(parsed))
        session.add(newsletter)
        session.flush()

        parser_run = ParserRun(
            newsletter_id=newsletter.id,
            parser_version=PARSER_VERSION,
            status="completed",
            run_started_at=datetime.utcnow(),
            run_completed_at=datetime.utcnow(),
            page_count_detected=parsed.metadata.get("page_count"),
            pages_parsed=parsed.metadata.get("page_count"),
            watchlist_entry_count=len(parsed.watchlist_rows),
            section_count=len(parsed.section_summaries),
            warning_count=0,
            warnings_json=[],
            metrics_json={
                "has_watchlist_reference": parsed.watchlist_reference is not None,
                "source_filename": parsed.source_file.name,
            },
        )
        session.add(parser_run)
        session.flush()

        for section in parsed.section_summaries:
            session.add(
                NewsletterSection(
                    newsletter_id=newsletter.id,
                    name=section.name,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    raw_text=section.raw_text,
                    summary_text=section.summary_text,
                    section_type=_classify_section_type(section.name),
                    extraction_confidence=0.95,
                    parser_run_id=parser_run.id,
                    metadata_json={},
                )
            )

        if parsed.watchlist_reference is not None:
            session.add(
                WatchlistReferenceRecord(
                    newsletter_id=newsletter.id,
                    page_number=parsed.watchlist_reference.page_number,
                    raw_text=parsed.watchlist_reference.raw_text,
                    summary_text=parsed.watchlist_reference.summary_text,
                    column_definitions_json=parsed.watchlist_reference.column_definitions,
                    trading_rules_json=parsed.watchlist_reference.trading_rules,
                    classification_rules_json=parsed.watchlist_reference.classification_rules,
                    parser_run_id=parser_run.id,
                    reference_version="v1",
                    metadata_json={},
                )
            )

        for row in parsed.watchlist_rows:
            session.add(
                WatchlistEntry(
                    newsletter_id=newsletter.id,
                    commodity_name=row.commodity_name,
                    spread_code=row.spread_code,
                    side=row.side,
                    legs=row.legs,
                    category=row.category,
                    enter_date=row.enter_date,
                    exit_date=row.exit_date,
                    win_pct=row.win_pct,
                    avg_profit=row.avg_profit,
                    avg_best_profit=row.avg_best_profit,
                    avg_worst_loss=row.avg_worst_loss,
                    avg_draw_down=row.avg_draw_down,
                    apw_pct=row.apw_pct,
                    ridx=row.ridx,
                    five_year_corr=row.five_year_corr,
                    portfolio=row.portfolio,
                    risk_level=row.risk_level,
                    trade_quality=row.trade_quality,
                    volatility_structure=row.volatility_structure,
                    section_name=row.section_name,
                    page_number=row.page_number,
                    raw_row=row.raw_row,
                    entry_key=_build_entry_key(parsed.week_ended, row),
                    tradeable=None,
                    blocked_reason=None,
                    parser_run_id=parser_run.id,
                    publication_state="candidate",
                    metadata_json={},
                )
            )

        session.flush()

        current_entries = session.execute(
            select(WatchlistEntry)
            .where(WatchlistEntry.newsletter_id == newsletter.id)
            .order_by(WatchlistEntry.id)
        ).scalars().all()
        previous_newsletter = _get_previous_newsletter(session, newsletter.week_ended)
        previous_entries: list[WatchlistEntry] = []
        if previous_newsletter is not None:
            previous_entries = session.execute(
                select(WatchlistEntry)
                .where(WatchlistEntry.newsletter_id == previous_newsletter.id)
                .order_by(WatchlistEntry.id)
            ).scalars().all()

        added_entries, removed_entries, changed_entries, delta_summary = _compute_issue_delta(
            current_entries,
            previous_entries,
        )

        session.add(
            IssueBrief(
                newsletter_id=newsletter.id,
                parser_run_id=parser_run.id,
                brief_status="draft",
                headline=newsletter.title,
                executive_summary=newsletter.overall_summary,
                key_themes_json=[],
                notable_risks_json=[],
                notable_opportunities_json=[],
                watchlist_summary_json=_summarize_watchlist_rows(parsed.watchlist_rows),
                change_summary_json={
                    "added_count": len(added_entries),
                    "removed_count": len(removed_entries),
                    "changed_count": len(changed_entries),
                },
            )
        )
        session.add(
            IssueDelta(
                newsletter_id=newsletter.id,
                previous_newsletter_id=previous_newsletter.id if previous_newsletter is not None else None,
                delta_status="generated",
                added_entries_json=added_entries,
                removed_entries_json=removed_entries,
                changed_entries_json=changed_entries,
                summary_text=delta_summary if previous_newsletter is not None else "No prior issue available for comparison.",
            )
        )
        session.add(
            PublicationRun(
                newsletter_id=newsletter.id,
                publication_version="draft-1",
                status="draft",
                manifest_json={
                    "week_ended": newsletter.week_ended.isoformat(),
                    "entry_count": len(current_entries),
                },
            )
        )

        return {
            "status": "ingested",
            "week_ended": parsed.week_ended.isoformat(),
            "source_file": str(parsed.source_file),
            "watchlist_rows": len(parsed.watchlist_rows),
            "sections": len(parsed.section_summaries),
            "has_watchlist_reference": parsed.watchlist_reference is not None,
            "issue_status": newsletter.issue_status,
            "parser_run_status": parser_run.status,
            "delta_summary": delta_summary if previous_newsletter is not None else None,
        }


def _resolve_pdf_path(pdf_path: str | None) -> Path:
    if pdf_path:
        path = Path(pdf_path)
        return path if path.is_absolute() else settings.data_dir / path
    pdf_files = sorted(settings.data_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDFs found in {settings.data_dir}")
    return pdf_files[-1]


def _parse_issue_date(value: str) -> date:
    return date.fromisoformat(value)


@mcp.tool()
def ingest_newsletter(pdf_path: str | None = None) -> dict[str, Any]:
    """Parse a newsletter PDF and store issue metadata, summaries, and watchlist rows."""
    path = _resolve_pdf_path(pdf_path)
    parsed = parse_newsletter(path)
    return _save_parsed_newsletter(parsed)


@mcp.tool()
def ingest_pending_newsletters() -> dict[str, Any]:
    """Scan the data folder and ingest all PDFs not already present in the database."""
    results: list[dict[str, Any]] = []
    for pdf_path in sorted(settings.data_dir.glob("*.pdf")):
        parsed = parse_newsletter(pdf_path)
        results.append(_save_parsed_newsletter(parsed))

    ingested = [result for result in results if result["status"] == "ingested"]
    skipped = [result for result in results if result["status"] == "skipped"]
    return {
        "data_dir": str(settings.data_dir),
        "ingested_count": len(ingested),
        "skipped_count": len(skipped),
        "results": results,
    }


@mcp.tool()
def backfill_phase1_intelligence() -> dict[str, Any]:
    """Backfill Phase 1 parser, brief, delta, and publication records for existing issues."""
    with database.session() as session:
        newsletters = session.execute(
            select(Newsletter).order_by(Newsletter.week_ended)
        ).scalars().all()
        results: list[dict[str, Any]] = []
        for newsletter in newsletters:
            seeded = _seed_phase1_records(session, newsletter)
            results.append(
                {
                    "week_ended": newsletter.week_ended.isoformat(),
                    "parser_run_id": seeded["parser_run_id"],
                    "delta_summary": seeded["delta_summary"],
                }
            )

        return {
            "issue_count": len(newsletters),
            "results": results,
        }


@mcp.tool()
def list_issues(limit: int = 10) -> list[dict[str, Any]]:
    """List newsletter issues already imported into the database."""
    with database.session() as session:
        stmt = select(Newsletter).order_by(desc(Newsletter.week_ended)).limit(limit)
        records = session.execute(stmt).scalars().all()
        return [
            {
                "week_ended": record.week_ended.isoformat(),
                "title": record.title,
                "source_file": record.source_file,
                "summary": record.overall_summary,
            }
            for record in records
        ]


@mcp.tool()
def get_issue_summary(week_ended: str) -> dict[str, Any]:
    """Return the issue summary and section summaries for a specific week ended date."""
    with database.session() as session:
        stmt = select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
        newsletter = session.execute(stmt).scalar_one_or_none()
        if newsletter is None:
            raise ValueError(f"No newsletter found for {week_ended}")

        sections_stmt = (
            select(NewsletterSection)
            .where(NewsletterSection.newsletter_id == newsletter.id)
            .order_by(NewsletterSection.page_start)
        )
        sections = session.execute(sections_stmt).scalars().all()
        return {
            "week_ended": newsletter.week_ended.isoformat(),
            "title": newsletter.title,
            "summary": newsletter.overall_summary,
            "sections": [
                {
                    "name": section.name,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                    "summary": section.summary_text,
                }
                for section in sections
            ],
        }


def _serialize_watchlist_reference(reference: WatchlistReferenceRecord | None) -> dict[str, Any] | None:
    if reference is None:
        return None

    return {
        "page_number": reference.page_number,
        "summary": reference.summary_text,
        "column_definitions": reference.column_definitions_json,
        "trading_rules": reference.trading_rules_json,
        "classification_rules": reference.classification_rules_json,
    }


def _serialize_watchlist_entry(entry: WatchlistEntry) -> dict[str, Any]:
    return {
        "commodity_name": entry.commodity_name,
        "spread_code": entry.spread_code,
        "side": entry.side,
        "legs": entry.legs,
        "category": entry.category,
        "enter_date": entry.enter_date.isoformat(),
        "exit_date": entry.exit_date.isoformat(),
        "win_pct": entry.win_pct,
        "avg_profit": entry.avg_profit,
        "avg_best_profit": entry.avg_best_profit,
        "avg_worst_loss": entry.avg_worst_loss,
        "avg_draw_down": entry.avg_draw_down,
        "apw_pct": entry.apw_pct,
        "ridx": entry.ridx,
        "five_year_corr": entry.five_year_corr,
        "portfolio": entry.portfolio,
        "risk_level": entry.risk_level,
        "trade_quality": entry.trade_quality,
        "volatility_structure": entry.volatility_structure,
        "section_name": entry.section_name,
        "page_number": entry.page_number,
    }


WATCHLIST_CSV_FIELDNAMES = [
    "commodity_name",
    "spread_code",
    "side",
    "legs",
    "category",
    "enter_date",
    "exit_date",
    "win_pct",
    "avg_profit",
    "avg_best_profit",
    "avg_worst_loss",
    "avg_draw_down",
    "apw_pct",
    "ridx",
    "five_year_corr",
    "portfolio",
    "risk_level",
    "trade_quality",
    "volatility_structure",
    "section_name",
    "page_number",
]


def _build_watchlist_csv(entries: list[dict[str, Any]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=WATCHLIST_CSV_FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    writer.writerows(entries)
    return output.getvalue()


def _write_text_file(path_str: str, content: str) -> str:
    path = Path(path_str)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")
    return str(path)


@mcp.tool()
def get_watchlist(
    week_ended: str,
    min_trade_quality: str | None = None,
    include_reference: bool = True,
) -> dict[str, Any]:
    """Return watchlist rows for a given issue date, optionally filtered by trade quality tier."""
    with database.session() as session:
        newsletter = session.execute(
            select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
        ).scalar_one_or_none()
        if newsletter is None:
            raise ValueError(f"No newsletter found for {week_ended}")

        stmt = (
            select(WatchlistEntry)
            .where(WatchlistEntry.newsletter_id == newsletter.id)
            .order_by(WatchlistEntry.page_number, WatchlistEntry.id)
        )
        entries = session.execute(stmt).scalars().all()

        if min_trade_quality:
            threshold = int(min_trade_quality.split()[-1])
            entries = [
                entry
                for entry in entries
                if entry.trade_quality and int(entry.trade_quality.split()[-1]) <= threshold
            ]

        counts = Counter((entry.trade_quality or entry.portfolio or "unclassified") for entry in entries)
        response = {
            "week_ended": newsletter.week_ended.isoformat(),
            "entry_count": len(entries),
            "watchlist_bucket_counts": dict(counts),
            "entries": [_serialize_watchlist_entry(entry) for entry in entries],
        }

        if include_reference:
            reference = session.execute(
                select(WatchlistReferenceRecord).where(
                    WatchlistReferenceRecord.newsletter_id == newsletter.id
                )
            ).scalar_one_or_none()
            response["watchlist_reference"] = _serialize_watchlist_reference(reference)

        return response


@mcp.tool()
def export_watchlist_csv(
    week_ended: str,
    section_name: str | None = None,
    min_trade_quality: str | None = None,
    include_reference: bool = True,
    output_path: str | None = None,
    reference_output_path: str | None = None,
) -> dict[str, Any]:
    """Export watchlist rows as CSV, optionally filtered by section and trade quality."""
    result = get_watchlist(
        week_ended=week_ended,
        min_trade_quality=min_trade_quality,
        include_reference=include_reference,
    )
    entries = result["entries"]

    if section_name is not None:
        entries = [entry for entry in entries if entry["section_name"] == section_name]

    csv_content = _build_watchlist_csv(entries)
    written_files: dict[str, str] = {}

    if output_path is not None:
        written_files["csv"] = _write_text_file(output_path, csv_content)

    if include_reference and reference_output_path is not None:
        reference_json = json.dumps(result.get("watchlist_reference"), indent=2)
        written_files["reference"] = _write_text_file(reference_output_path, reference_json)

    response = {
        "week_ended": result["week_ended"],
        "section_name": section_name,
        "entry_count": len(entries),
        "csv": csv_content,
        "watchlist_reference": result.get("watchlist_reference"),
    }
    if written_files:
        response["written_files"] = written_files

    return response


@mcp.tool()
def export_watchlist_package(
    week_ended: str,
    section_name: str | None = None,
    min_trade_quality: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Export one issue as paired rows.csv and reference.json outputs."""
    result = export_watchlist_csv(
        week_ended=week_ended,
        section_name=section_name,
        min_trade_quality=min_trade_quality,
        include_reference=True,
    )
    reference = result.get("watchlist_reference")
    package = {
        "week_ended": result["week_ended"],
        "section_name": section_name,
        "entry_count": result["entry_count"],
        "rows_csv": result["csv"],
        "reference_json": json.dumps(reference, indent=2),
        "watchlist_reference": reference,
    }

    if output_dir is not None:
        base_dir = Path(output_dir)
        if not base_dir.is_absolute():
            base_dir = Path.cwd() / base_dir
        base_dir.mkdir(parents=True, exist_ok=True)
        rows_path = _write_text_file(str(base_dir / "rows.csv"), package["rows_csv"])
        reference_path = _write_text_file(str(base_dir / "reference.json"), package["reference_json"])
        package["written_files"] = {
            "rows_csv": rows_path,
            "reference_json": reference_path,
        }

    return package


@mcp.tool()
def export_all_watchlists_csv(
    date_from: str,
    date_to: str,
    section_name: str | None = None,
    min_trade_quality: str | None = None,
    include_reference: bool = True,
    output_path: str | None = None,
    reference_output_path: str | None = None,
) -> dict[str, Any]:
    """Export watchlists across a date range as one CSV, with optional reference bundle."""
    start_date = _parse_issue_date(date_from)
    end_date = _parse_issue_date(date_to)

    with database.session() as session:
        newsletters = session.execute(
            select(Newsletter)
            .where(Newsletter.week_ended >= start_date, Newsletter.week_ended <= end_date)
            .order_by(Newsletter.week_ended)
        ).scalars().all()

        rows: list[dict[str, Any]] = []
        references: list[dict[str, Any]] = []

        for newsletter in newsletters:
            result = get_watchlist(
                week_ended=newsletter.week_ended.isoformat(),
                min_trade_quality=min_trade_quality,
                include_reference=include_reference,
            )
            issue_entries = result["entries"]
            if section_name is not None:
                issue_entries = [
                    entry for entry in issue_entries if entry["section_name"] == section_name
                ]

            for entry in issue_entries:
                rows.append(
                    {
                        "week_ended": newsletter.week_ended.isoformat(),
                        **entry,
                    }
                )

            if include_reference and result.get("watchlist_reference") is not None:
                references.append(
                    {
                        "week_ended": newsletter.week_ended.isoformat(),
                        **result["watchlist_reference"],
                    }
                )

    combined_fieldnames = ["week_ended", *WATCHLIST_CSV_FIELDNAMES]
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=combined_fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_content = output.getvalue()

    written_files: dict[str, str] = {}
    if output_path is not None:
        written_files["csv"] = _write_text_file(output_path, csv_content)
    if include_reference and reference_output_path is not None:
        written_files["references"] = _write_text_file(
            reference_output_path,
            json.dumps(references, indent=2),
        )

    response = {
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "issue_count": len(newsletters),
        "entry_count": len(rows),
        "section_name": section_name,
        "csv": csv_content,
    }
    if include_reference:
        response["watchlist_references"] = references
    if written_files:
        response["written_files"] = written_files

    return response


@mcp.tool()
def export_watchlist_bundle(
    date_from: str,
    date_to: str,
    output_dir: str,
    include_issue_packages: bool = True,
    include_consolidated: bool = True,
    include_reference_bundle: bool = True,
) -> dict[str, Any]:
    """Export a folder bundle with per-issue watchlists and consolidated CSVs."""
    start_date = _parse_issue_date(date_from)
    end_date = _parse_issue_date(date_to)
    base_dir = Path(output_dir)
    if not base_dir.is_absolute():
        base_dir = Path.cwd() / base_dir
    base_dir.mkdir(parents=True, exist_ok=True)

    with database.session() as session:
        newsletters = session.execute(
            select(Newsletter)
            .where(Newsletter.week_ended >= start_date, Newsletter.week_ended <= end_date)
            .order_by(Newsletter.week_ended)
        ).scalars().all()

    issue_packages: list[dict[str, Any]] = []
    consolidated_outputs: dict[str, Any] = {}

    if include_issue_packages:
        issues_dir = base_dir / "issues"
        issues_dir.mkdir(parents=True, exist_ok=True)
        for newsletter in newsletters:
            issue_date = newsletter.week_ended.isoformat()
            issue_dir = issues_dir / issue_date
            issue_dir.mkdir(parents=True, exist_ok=True)

            intra = export_watchlist_package(
                week_ended=issue_date,
                section_name="intra_commodity",
                output_dir=str(issue_dir / "intra_commodity"),
            )
            inter = export_watchlist_package(
                week_ended=issue_date,
                section_name="inter_commodity",
                output_dir=str(issue_dir / "inter_commodity"),
            )

            issue_packages.append(
                {
                    "week_ended": issue_date,
                    "issue_dir": str(issue_dir),
                    "intra_entry_count": intra["entry_count"],
                    "inter_entry_count": inter["entry_count"],
                    "written_files": {
                        "intra": intra.get("written_files"),
                        "inter": inter.get("written_files"),
                    },
                }
            )

    if include_consolidated:
        consolidated_dir = base_dir / "consolidated"
        consolidated_dir.mkdir(parents=True, exist_ok=True)

        intra = export_all_watchlists_csv(
            date_from=start_date.isoformat(),
            date_to=end_date.isoformat(),
            section_name="intra_commodity",
            include_reference=include_reference_bundle,
            output_path=str(consolidated_dir / "intra_commodity.csv"),
            reference_output_path=(
                str(consolidated_dir / "intra_commodity_references.json")
                if include_reference_bundle
                else None
            ),
        )
        inter = export_all_watchlists_csv(
            date_from=start_date.isoformat(),
            date_to=end_date.isoformat(),
            section_name="inter_commodity",
            include_reference=include_reference_bundle,
            output_path=str(consolidated_dir / "inter_commodity.csv"),
            reference_output_path=(
                str(consolidated_dir / "inter_commodity_references.json")
                if include_reference_bundle
                else None
            ),
        )

        consolidated_outputs = {
            "dir": str(consolidated_dir),
            "intra_entry_count": intra["entry_count"],
            "inter_entry_count": inter["entry_count"],
            "written_files": {
                "intra": intra.get("written_files"),
                "inter": inter.get("written_files"),
            },
        }

    return {
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "issue_count": len(newsletters),
        "output_dir": str(base_dir),
        "issue_packages": issue_packages,
        "consolidated": consolidated_outputs,
    }


@mcp.tool()
def get_watchlist_reference(week_ended: str) -> dict[str, Any]:
    """Return the watchlist overview/reference rules for a specific newsletter issue."""
    with database.session() as session:
        newsletter = session.execute(
            select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
        ).scalar_one_or_none()
        if newsletter is None:
            raise ValueError(f"No newsletter found for {week_ended}")

        reference = session.execute(
            select(WatchlistReferenceRecord).where(
                WatchlistReferenceRecord.newsletter_id == newsletter.id
            )
        ).scalar_one_or_none()
        if reference is None:
            return {
                "week_ended": newsletter.week_ended.isoformat(),
                "has_watchlist_reference": False,
            }

        return {
            "week_ended": newsletter.week_ended.isoformat(),
            "has_watchlist_reference": True,
            "page_number": reference.page_number,
            "summary": reference.summary_text,
            "column_definitions": reference.column_definitions_json,
            "trading_rules": reference.trading_rules_json,
            "classification_rules": reference.classification_rules_json,
        }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
