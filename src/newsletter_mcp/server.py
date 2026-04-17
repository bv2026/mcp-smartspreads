from __future__ import annotations

from collections import Counter
import csv
import hashlib
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from math import gcd
import json
from io import StringIO
from pathlib import Path
import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader
from sqlalchemy import desc, select

from .config import Settings
from .business import IssueBriefDraft, IssueBriefService
from .database import (
    ContractMonthCode,
    Database,
    IssueBrief,
    IssueDelta,
    Newsletter,
    NewsletterSection,
    NewsletterCommodityCatalog,
    ParserRun,
    PublicationArtifact,
    PublicationRun,
    StrategyDocument,
    StrategyPrinciple,
    StrategySection,
    SchwabFuturesCatalog,
    WatchlistEntry,
    WatchlistReferenceRecord,
)
from .parser import parse_newsletter
from .principle_evaluation import HistoricalContext, PrincipleEvaluationService


PARSER_VERSION = "phase1-v1"
PUBLICATION_SCHEMA_VERSION = "1.0"
CONTRACT_CODE_RE = re.compile(r"^(?P<root>[A-Z]+)(?P<month>[FGHJKMNQUVXZ])(?P<year>\d{2})$")
SPREAD_TOKEN_RE = re.compile(r"([+-]?)(?:(\d+)\*)?([A-Z]+[FGHJKMNQUVXZ]\d{2})")
COMMODITY_DETAILS_ROW_RE = re.compile(
    r"(?P<commodity>[A-Za-z0-9#&/().' -]+?)\s+"
    r"(?P<exchange>NYMEX|COMEX|CBOT|KCBT|CME|NYCE|LIF|ICE)\s+"
    r"(?P<unit>[\d,]+)\s+"
    r"(?P<newsletter_root>[A-Z]{1,3})\s+"
    r"(?P<globex_root>[A-Z]{1,4})"
)
ROOT_SYMBOL_MAP = {
    "BO": "/ZL",
    "C": "/ZC",
    "CC": "/CC",
    "CL": "/CL",
    "CT": "/CT",
    "FC": "/GF",
    "GC": "/GC",
    "GO": None,
    "HG": "/HG",
    "HO": "/HO",
    "KW": "/KE",
    "LC": "/LE",
    "LH": "/HE",
    "MW": "/MWE",
    "NG": "/NG",
    "RB": "/RB",
    "S": "/ZS",
    "SB": "/SB",
    "SI": "/SI",
    "SM": "/ZM",
    "VX": "/VX",
    "W": "/ZW",
}
ROOT_BLOCK_REASONS = {
    "BC": "Brent crude is not available in TOS.",
    "FC": "Feeder Cattle is in the doghouse and should never be traded.",
    "GO": "Gasoil is not available in TOS.",
    "SB": "Sugar #11 is not tradeable as a spread in TOS.",
}
settings = Settings.from_env()
database = Database(settings.database_url)
database.create_schema()
mcp = FastMCP("newsletter-mcp")
DEFAULT_SCHWAB_CATALOG_CSV = Path(r"C:\Users\vsbra\OneDrive\Downloads1\futures-tradelog - Sheet13.csv")
MONTH_NAME_ORDER = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
DEFAULT_STRATEGY_MANUAL_PATH = Path(r"C:\work\SmartSpreads\reference\strategy\The Smart Spreads Strategy S.pdf")
STRATEGY_CHAPTER_RE = re.compile(r"Chapter\s+(?P<number>\d+)\s+[—–-]\s+(?P<title>.+)")
STRATEGY_PART_RE = re.compile(r"Part\s+(?P<number>[IVX]+)\s+[—–-]\s+(?P<title>.+)")
STRATEGY_PRINCIPLE_SEED = [
    {
        "principle_key": "structure_before_conviction",
        "principle_title": "Structure Before Conviction",
        "category": "philosophy",
        "priority": 1,
        "summary_text": "The framework prefers structurally durable spread relationships over subjective conviction or directional opinion.",
        "guidance_text": "Use structure and historical persistence as the primary filter before acting on a weekly idea.",
        "chapter_number": 8,
        "applies_to": ["issue_brief", "daily_brief", "action_plan"],
        "anti_patterns": ["trading from conviction alone", "overweighting attractive narratives"],
    },
    {
        "principle_key": "selectivity_not_participation",
        "principle_title": "Selectivity, Not Participation",
        "category": "trade_selection",
        "priority": 1,
        "summary_text": "Not all markets or spread structures deserve capital; selectivity is itself part of the edge.",
        "guidance_text": "Prefer a smaller set of structurally qualified ideas over broad participation in every seasonal pattern.",
        "chapter_number": 9,
        "applies_to": ["issue_brief", "blocked_trade_explanation", "action_plan"],
        "anti_patterns": ["overtrading", "equating frequency with edge"],
    },
    {
        "principle_key": "trade_selection_dominates_trade_management",
        "principle_title": "Trade Selection Dominates Trade Management",
        "category": "trade_selection",
        "priority": 1,
        "summary_text": "The quality of the trade chosen matters more than later attempts to rescue weak structures with management tricks.",
        "guidance_text": "Emphasize screening, filtering, and qualification before discussing exits, stops, or profit taking.",
        "chapter_number": 11,
        "applies_to": ["issue_brief", "daily_brief", "blocked_trade_explanation"],
        "anti_patterns": ["using management to justify weak entries"],
    },
    {
        "principle_key": "volatility_as_constraint",
        "principle_title": "Volatility Is a Structural Constraint",
        "category": "volatility",
        "priority": 2,
        "summary_text": "Volatility should be treated as a design and survivability constraint, not merely a market condition.",
        "guidance_text": "Use volatility structure to shape position selection, holding expectations, and action-plan confidence.",
        "chapter_number": 10,
        "applies_to": ["issue_brief", "daily_brief", "portfolio_fit"],
        "anti_patterns": ["ignoring volatility structure", "assuming carry always dominates volatility"],
    },
    {
        "principle_key": "margin_as_survivability_constraint",
        "principle_title": "Margin Is a Survivability Constraint",
        "category": "margin",
        "priority": 2,
        "summary_text": "Exchange margin is a minimum clearing requirement, not a permission slip for full capital usage.",
        "guidance_text": "Use margin to judge staying power and resilience, not to maximize deployed exposure.",
        "chapter_number": 16,
        "applies_to": ["daily_brief", "portfolio_fit", "action_plan"],
        "anti_patterns": ["treating margin as target utilization", "sizing positions to the clearing minimum"],
    },
    {
        "principle_key": "portfolio_fit_over_isolated_trade_appeal",
        "principle_title": "Portfolio Fit Over Isolated Trade Appeal",
        "category": "portfolio_construction",
        "priority": 2,
        "summary_text": "A trade should be judged not only on standalone merit but on how it changes concentration, overlap, and resilience in the portfolio.",
        "guidance_text": "Flag leg overlap and same-theme concentration as portfolio-fit issues, not just execution details.",
        "chapter_number": 14,
        "applies_to": ["daily_brief", "action_plan", "portfolio_fit"],
        "anti_patterns": ["adding overlapping exposure without review"],
    },
    {
        "principle_key": "intercommodity_conditional_edge",
        "principle_title": "Inter-Commodity Edge Is Conditional",
        "category": "intercommodity",
        "priority": 3,
        "summary_text": "Inter-commodity spreads can have edge, but they require stricter structural discipline than standard calendars.",
        "guidance_text": "Treat inter-commodity opportunities as conditional and more constraint-sensitive than single-market calendars.",
        "chapter_number": 23,
        "applies_to": ["issue_brief", "blocked_trade_explanation"],
        "anti_patterns": ["treating inter-commodity spreads like ordinary calendars"],
    },
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


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


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_key_part(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized


def _build_entry_key(week_ended: date, row: Any) -> str:
    return "|".join(
        [
            _normalize_key_part(row.section_name),
            _normalize_key_part(row.commodity_name),
            _normalize_key_part(row.spread_code),
            row.side.lower(),
        ]
    )


def _canonical_entry_key(newsletter: Newsletter, entry: WatchlistEntry) -> str:
    return _build_entry_key(newsletter.week_ended, entry)


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


def _int_from_roman(value: str | None) -> int | None:
    if value is None:
        return None
    mapping = {"I": 1, "V": 5, "X": 10}
    total = 0
    previous = 0
    for char in reversed(value.upper()):
        current = mapping.get(char, 0)
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total or None


def _extract_strategy_pdf(path: Path) -> dict[str, Any]:
    reader = PdfReader(str(path))
    pages: list[dict[str, Any]] = []
    current_part_number: int | None = None
    current_part_title: str | None = None
    chapter_starts: list[dict[str, Any]] = []

    for page_index, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        normalized_lines = [" ".join(line.split()) for line in raw_text.splitlines() if line.strip()]
        page_text = "\n".join(normalized_lines)
        pages.append({"page_number": page_index, "text": page_text})
        chapter_matches_on_page = sum(1 for line in normalized_lines if STRATEGY_CHAPTER_RE.search(line))
        is_contents_page = bool(
            (normalized_lines and normalized_lines[0].lower() == "contents")
            or chapter_matches_on_page > 1
        )

        for line in normalized_lines:
            part_match = STRATEGY_PART_RE.search(line)
            if part_match:
                current_part_number = _int_from_roman(part_match.group("number"))
                current_part_title = part_match.group("title").strip()
        if is_contents_page:
            continue
        for line in normalized_lines:
            chapter_match = STRATEGY_CHAPTER_RE.search(line)
            if chapter_match:
                chapter_number = int(chapter_match.group("number"))
                title = chapter_match.group("title").strip()
                if not any(existing["chapter_number"] == chapter_number for existing in chapter_starts):
                    chapter_starts.append(
                        {
                            "chapter_number": chapter_number,
                            "chapter_title": title,
                            "part_number": current_part_number,
                            "part_title": current_part_title,
                            "page_start": page_index,
                        }
                    )
                break

    sections: list[dict[str, Any]] = []
    for index, start in enumerate(chapter_starts):
        next_page = chapter_starts[index + 1]["page_start"] if index + 1 < len(chapter_starts) else len(pages) + 1
        section_pages = [page for page in pages if start["page_start"] <= page["page_number"] < next_page]
        body_text = "\n\n".join(page["text"] for page in section_pages if page["text"]).strip()
        first_paragraph = next((part.strip() for part in body_text.split("\n\n") if part.strip()), "")
        summary_text = first_paragraph[:800] if first_paragraph else None
        keywords = sorted(
            {
                keyword
                for keyword in ["structure", "seasonality", "trade quality", "volatility", "margin", "portfolio", "execution", "inter-commodity"]
                if keyword in body_text.lower()
            }
        )
        sections.append(
            {
                **start,
                "page_end": next_page - 1,
                "heading_path": " > ".join(
                    part
                    for part in [
                        f"Part {start['part_number']}" if start["part_number"] is not None else None,
                        start["part_title"],
                        f"Chapter {start['chapter_number']}",
                        start["chapter_title"],
                    ]
                    if part
                ),
                "body_text": body_text,
                "summary_text": summary_text,
                "keywords": keywords,
            }
        )

    raw_text = "\n\n".join(page["text"] for page in pages if page["text"])
    return {
        "title": "Trading Commodity Spreads",
        "page_count": len(reader.pages),
        "raw_text": raw_text,
        "sections": sections,
    }


def _build_strategy_document_summary(extracted: dict[str, Any]) -> str:
    chapter_count = len(extracted["sections"])
    return (
        f"Strategy manual with {chapter_count} extracted chapters covering foundations, trade quality, "
        f"trade selection, execution, margin, stops, profit taking, framework hierarchy, and appendices."
    )


def _serialize_strategy_document(document: StrategyDocument) -> dict[str, Any]:
    return {
        "id": document.id,
        "title": document.title,
        "source_file": document.source_file,
        "document_type": document.document_type,
        "author": document.author,
        "version_label": document.version_label,
        "published_year": document.published_year,
        "page_count": document.page_count,
        "summary_text": document.summary_text,
        "metadata": document.metadata_json,
    }


def _serialize_strategy_section(section: StrategySection) -> dict[str, Any]:
    return {
        "id": section.id,
        "part_number": section.part_number,
        "part_title": section.part_title,
        "chapter_number": section.chapter_number,
        "chapter_title": section.chapter_title,
        "page_start": section.page_start,
        "page_end": section.page_end,
        "heading_path": section.heading_path,
        "summary_text": section.summary_text,
        "keywords": section.keywords_json,
    }


def _serialize_strategy_principle(principle: StrategyPrinciple) -> dict[str, Any]:
    return {
        "id": principle.id,
        "principle_key": principle.principle_key,
        "principle_title": principle.principle_title,
        "category": principle.category,
        "priority": principle.priority,
        "summary_text": principle.summary_text,
        "guidance_text": principle.guidance_text,
        "applies_to": principle.applies_to_json,
        "examples": principle.examples_json,
        "anti_patterns": principle.anti_patterns_json,
        "chapter_number": principle.metadata_json.get("chapter_number"),
        "chapter_title": principle.metadata_json.get("chapter_title"),
    }


def _parse_contract_code(contract_code: str) -> dict[str, str]:
    match = CONTRACT_CODE_RE.match(contract_code)
    if match is None:
        return {"root": contract_code, "month": "", "year": ""}
    return match.groupdict()


def _resolve_newsletter_root_symbol(root: str) -> dict[str, Any]:
    if root in ROOT_BLOCK_REASONS:
        return {
            "root_code": root,
            "schwab_root": None,
            "blocked_reason": ROOT_BLOCK_REASONS[root],
            "mapping_source": "policy_block",
        }

    with database.session() as session:
        active_schwab_roots = set(
            session.execute(
                select(SchwabFuturesCatalog.symbol_root).where(SchwabFuturesCatalog.is_active.is_(True))
            ).scalars().all()
        )
        has_catalog = bool(active_schwab_roots)
        newsletter_mapping = session.execute(
            select(NewsletterCommodityCatalog).where(NewsletterCommodityCatalog.newsletter_root == root)
        ).scalar_one_or_none()

        if newsletter_mapping is not None and newsletter_mapping.is_tradeable_by_policy is False:
            return {
                "root_code": root,
                "schwab_root": newsletter_mapping.preferred_schwab_root,
                "blocked_reason": newsletter_mapping.policy_block_reason
                or f"Newsletter policy marks {root} as not tradeable.",
                "mapping_source": "newsletter_policy",
            }

        broker_root = None
        if newsletter_mapping is not None:
            broker_root = (
                newsletter_mapping.broker_symbol_root
                or newsletter_mapping.preferred_schwab_root
            )
        if broker_root:
            schwab_root = broker_root
            mapping_source = "newsletter_catalog"
        else:
            direct_root = f"/{root}"
            if direct_root in active_schwab_roots:
                schwab_root = direct_root
                mapping_source = "schwab_catalog_direct"
            else:
                schwab_root = ROOT_SYMBOL_MAP.get(root)
                mapping_source = "fallback_map"

        if schwab_root is None:
            return {
                "root_code": root,
                "schwab_root": None,
                "blocked_reason": f"No Schwab symbol mapping configured for contract root {root}.",
                "mapping_source": mapping_source,
            }

        if has_catalog and schwab_root not in active_schwab_roots:
            return {
                "root_code": root,
                "schwab_root": schwab_root,
                "blocked_reason": f"{schwab_root} is not present in the imported Schwab futures catalog.",
                "mapping_source": mapping_source,
            }

        return {
            "root_code": root,
            "schwab_root": schwab_root,
            "blocked_reason": None,
            "mapping_source": mapping_source,
        }


def _tos_symbol_for_contract(contract_code: str) -> tuple[str | None, str | None, str]:
    parsed = _parse_contract_code(contract_code)
    root = parsed["root"]
    resolution = _resolve_newsletter_root_symbol(root)
    if resolution["schwab_root"] is None:
        return None, resolution["blocked_reason"], root
    return f"{resolution['schwab_root']}{parsed['month']}{parsed['year']}", resolution["blocked_reason"], root


def _parse_spread_legs(spread_code: str) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for sign, multiplier_text, contract_code in SPREAD_TOKEN_RE.findall(spread_code):
        multiplier = int(multiplier_text or "1")
        operator = sign or "+"
        tos_symbol, blocked_reason, root = _tos_symbol_for_contract(contract_code)
        resolution = _resolve_newsletter_root_symbol(root)
        support = _load_schwab_catalog_support(resolution["schwab_root"])
        for copy_index in range(multiplier):
            legs.append(
                {
                    "operator": operator,
                    "multiplier": multiplier,
                    "copy_index": copy_index,
                    "contract_code": contract_code,
                    "root_code": root,
                    "resolved_root": resolution["schwab_root"],
                    "mapping_source": resolution["mapping_source"],
                    "tos_symbol": tos_symbol,
                    "tradeable": blocked_reason is None,
                    "blocked_reason": blocked_reason,
                    "stream_supported": support["stream_supported"],
                    "native_spread_support": support["native_spread_support"],
                    "manual_legs_required": support["manual_legs_required"],
                    "support_notes": support["support_notes"],
                }
            )
    return legs


def _infer_watchlist_type(entry: WatchlistEntry, legs: list[dict[str, Any]]) -> str:
    unique_roots = {leg["root_code"] for leg in legs}
    multiplier_pattern = [leg["multiplier"] for leg in legs]
    if entry.section_name == "inter_commodity" or len(unique_roots) > 1:
        return "intermarket"
    if len(legs) == 2:
        return "calendar"
    if len(legs) >= 3 and max(multiplier_pattern, default=1) >= 2:
        return "butterfly"
    return "multi_leg"


def _derive_watchlist_tier(entry: WatchlistEntry) -> str:
    if entry.trade_quality:
        return entry.trade_quality
    if entry.risk_level is not None:
        return f"Risk {entry.risk_level}"
    if entry.portfolio:
        return entry.portfolio
    return "Unclassified"


def _derive_entry_tradeability(entry: WatchlistEntry, legs: list[dict[str, Any]]) -> tuple[bool, str | None]:
    reasons = [leg["blocked_reason"] for leg in legs if leg["blocked_reason"]]
    if entry.trade_quality == "Tier 4":
        reasons.append("Tier 4 trades are excluded by policy.")
    if entry.ridx < 30:
        reasons.append("RIDX is below the minimum threshold of 30.")
    if reasons:
        deduped = []
        for reason in reasons:
            if reason not in deduped:
                deduped.append(reason)
        return False, " ".join(deduped)
    return True, None


def _combine_blocked_reasons(*reasons: str | None) -> str | None:
    deduped: list[str] = []
    for reason in reasons:
        if not reason:
            continue
        for part in [item.strip() for item in reason.split("  ") if item.strip()]:
            if part not in deduped:
                deduped.append(part)
    if not deduped:
        return None
    return " ".join(deduped)


def _load_issue_principles(session: Any) -> list[StrategyPrinciple]:
    return session.execute(
        select(StrategyPrinciple).order_by(
            StrategyPrinciple.priority.asc(),
            StrategyPrinciple.principle_key.asc(),
        )
    ).scalars().all()


def _evaluate_issue_entries(
    session: Any,
    *,
    newsletter: Newsletter,
    entries: list[WatchlistEntry],
) -> None:
    principles = _load_issue_principles(session)
    if not principles:
        for entry in entries:
            legs = _parse_spread_legs(entry.spread_code)
            policy_tradeable, policy_blocked_reason = _derive_entry_tradeability(entry, legs)
            entry.tradeable = policy_tradeable
            entry.blocked_reason = policy_blocked_reason
            metadata = dict(entry.metadata_json or {})
            metadata.setdefault("principle_evaluation", {})
            entry.metadata_json = metadata
        return

    prior_entries = session.execute(
        select(WatchlistEntry)
        .join(Newsletter, Newsletter.id == WatchlistEntry.newsletter_id)
        .where(Newsletter.week_ended < newsletter.week_ended)
    ).scalars().all()
    historical_context = HistoricalContext.build(current_entries=entries, prior_entries=prior_entries)

    for entry in entries:
        outcome = PrincipleEvaluationService.evaluate_entry(
            entry=entry,
            principles=principles,
            historical_context=historical_context,
        )
        legs = _parse_spread_legs(entry.spread_code)
        policy_tradeable, policy_blocked_reason = _derive_entry_tradeability(entry, legs)
        metadata = dict(entry.metadata_json or {})
        metadata["principle_evaluation"] = outcome.as_metadata()
        entry.metadata_json = metadata
        entry.tradeable = policy_tradeable and outcome.tradeable
        entry.blocked_reason = _combine_blocked_reasons(
            policy_blocked_reason,
            outcome.blocked_reason,
            outcome.blocked_guidance if not outcome.tradeable else None,
        )


def _build_principle_context(entries: list[WatchlistEntry]) -> dict[str, Any]:
    evaluated_entries = [
        entry for entry in entries if (entry.metadata_json or {}).get("principle_evaluation")
    ]
    if not evaluated_entries:
        return {
            "total_entries": len(entries),
            "evaluated_entries": 0,
            "tradeable_entries": sum(1 for entry in entries if entry.tradeable is not False),
            "blocked_by_principles": 0,
            "deferred_for_daily_review": 0,
            "selectivity_ratio": 0.0,
            "top_violations": {},
        }

    violation_counts = Counter()
    deferred_count = 0
    tradeable_count = 0
    for entry in evaluated_entries:
        evaluation = (entry.metadata_json or {}).get("principle_evaluation", {})
        for key in evaluation.get("violations", []):
            violation_counts[key] += 1
        deferred_count += len(evaluation.get("deferred_principles", []))
        if evaluation.get("tradeable") is not False:
            tradeable_count += 1

    return {
        "total_entries": len(entries),
        "evaluated_entries": len(evaluated_entries),
        "tradeable_entries": tradeable_count,
        "blocked_by_principles": len(evaluated_entries) - tradeable_count,
        "deferred_for_daily_review": deferred_count,
        "selectivity_ratio": round(tradeable_count / len(evaluated_entries), 4),
        "top_violations": dict(violation_counts.most_common(5)),
    }


def _build_watchlist_publication_entry(
    newsletter: Newsletter,
    entry: WatchlistEntry,
) -> dict[str, Any]:
    legs = _parse_spread_legs(entry.spread_code)
    policy_tradeable, policy_blocked_reason = _derive_entry_tradeability(entry, legs)
    principle_evaluation = (entry.metadata_json or {}).get("principle_evaluation", {})
    principle_tradeable = principle_evaluation.get("tradeable")
    tradeable = entry.tradeable if entry.tradeable is not None else (
        policy_tradeable if principle_tradeable is None else policy_tradeable and bool(principle_tradeable)
    )
    blocked_reason = entry.blocked_reason or _combine_blocked_reasons(
        policy_blocked_reason,
        principle_evaluation.get("blocked_reason") if principle_tradeable is False else None,
        principle_evaluation.get("blocked_guidance") if principle_tradeable is False else None,
    )
    tos_symbols = [leg["tos_symbol"] for leg in legs if leg["tos_symbol"]]
    unique_symbols = list(dict.fromkeys(tos_symbols))
    unique_roots = list(dict.fromkeys(leg["root_code"] for leg in legs))
    canonical_key = _canonical_entry_key(newsletter, entry)
    stream_supported_values = [leg["stream_supported"] for leg in legs if leg["stream_supported"] is not None]
    native_spread_support_values = [
        leg["native_spread_support"] for leg in legs if leg["native_spread_support"] is not None
    ]
    manual_legs_required_values = [
        leg["manual_legs_required"] for leg in legs if leg["manual_legs_required"] is not None
    ]
    support_notes = [leg["support_notes"] for leg in legs if leg["support_notes"]]
    deduped_support_notes: list[str] = []
    for note in support_notes:
        if note not in deduped_support_notes:
            deduped_support_notes.append(note)

    if len(unique_roots) == 1 and ROOT_SYMBOL_MAP.get(unique_roots[0]) is not None:
        symbol = ROOT_SYMBOL_MAP[unique_roots[0]]
    else:
        symbol = ",".join(symbol for symbol in dict.fromkeys(unique_symbols) if symbol)

    return {
        "id": f"wl_{canonical_key.replace('|', '_')}",
        "entry_key": canonical_key,
        "name": entry.commodity_name,
        "commodity_name": entry.commodity_name,
        "spread_code": entry.spread_code,
        "symbol": symbol,
        "legs": tos_symbols,
        "leg_details": legs,
        "type": _infer_watchlist_type(entry, legs),
        "side": entry.side,
        "section": entry.section_name,
        "category": entry.category,
        "stream_supported": None if not stream_supported_values else all(stream_supported_values),
        "native_spread_support": None
        if not native_spread_support_values
        else all(native_spread_support_values),
        "manual_legs_required": any(manual_legs_required_values),
        "support_notes": deduped_support_notes,
        "enter_date": entry.enter_date.isoformat(),
        "exit_date": entry.exit_date.isoformat(),
        "valid_until": (newsletter.week_ended + timedelta(days=7)).isoformat(),
        "win_pct": entry.win_pct,
        "avg_value": entry.avg_profit,
        "avg_profit": entry.avg_profit,
        "tier": _derive_watchlist_tier(entry),
        "volatility_structure": entry.volatility_structure,
        "portfolio": entry.portfolio,
        "risk_level": entry.risk_level,
        "trade_quality": entry.trade_quality,
        "ridx": entry.ridx,
        "five_year_corr": entry.five_year_corr,
        "page_number": entry.page_number,
        "action": f"Review {entry.section_name} idea from {newsletter.week_ended.isoformat()} newsletter.",
        "tradeable": tradeable,
        "blocked_reason": blocked_reason,
        "blocked_guidance": principle_evaluation.get("blocked_guidance"),
        "decision_summary": principle_evaluation.get("decision_summary"),
        "principle_scores": principle_evaluation.get("principle_scores", {}),
        "principle_status": principle_evaluation.get("principle_status", {}),
        "deferred_principles": principle_evaluation.get("deferred_principles", []),
        "principle_evaluation_ts": principle_evaluation.get("evaluated_at"),
        "evaluation_version": principle_evaluation.get("evaluation_version"),
    }


def _normalize_exit_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []

    for index, position in enumerate(positions):
        spread_id = position.get("spread_id")
        symbol = position.get("symbol")
        legs = position.get("legs")
        if spread_id and symbol and not legs:
            key = str(spread_id)
            group = grouped.setdefault(
                key,
                {
                    "id": key,
                    "name": position.get("spread_name") or position.get("name") or key,
                    "legs": [],
                    "leg_quantities": {},
                },
            )
            normalized_symbol = str(symbol).strip().upper()
            if normalized_symbol:
                leg_quantities: dict[str, int] = group["leg_quantities"]
                leg_quantities[normalized_symbol] = leg_quantities.get(normalized_symbol, 0) + abs(
                    int(position.get("quantity") or 0)
                )
            continue

        normalized = dict(position)
        normalized.setdefault("id", position.get("id") or position.get("position_id") or f"position_{index}")
        normalized.setdefault("name", position.get("name") or position.get("position_name"))
        passthrough.append(normalized)

    normalized_positions = passthrough
    normalized_positions.extend(grouped.values())
    return normalized_positions


def _expand_position_legs(position: dict[str, Any]) -> list[str]:
    expanded = position.get("expanded_legs")
    if expanded:
        return [symbol.strip().upper() for symbol in expanded if symbol and symbol.strip()]

    leg_quantities = position.get("leg_quantities")
    if isinstance(leg_quantities, list):
        legs = position.get("legs", [])
        if len(legs) == len(leg_quantities):
            normalized_quantities = [
                abs(int(quantity))
                for quantity in leg_quantities
                if quantity not in (None, 0, "0")
            ]
            divisor = 0
            for quantity in normalized_quantities:
                divisor = quantity if divisor == 0 else gcd(divisor, quantity)
            divisor = max(divisor, 1)

            values: list[str] = []
            for symbol, quantity in zip(legs, leg_quantities):
                if not symbol or not str(symbol).strip():
                    continue
                copies = max(abs(int(quantity)) // divisor, 1)
                values.extend([str(symbol).strip().upper()] * copies)
            if values:
                return values

    if isinstance(leg_quantities, dict):
        normalized_quantities = [
            abs(int(quantity))
            for quantity in leg_quantities.values()
            if quantity not in (None, 0, "0")
        ]
        divisor = 0
        for quantity in normalized_quantities:
            divisor = quantity if divisor == 0 else gcd(divisor, quantity)
        divisor = max(divisor, 1)

        values: list[str] = []
        for symbol, quantity in leg_quantities.items():
            if not symbol or not str(symbol).strip():
                continue
            copies = max(abs(int(quantity)) // divisor, 1)
            values.extend([str(symbol).strip().upper()] * copies)
        if values:
            return values

    return [symbol.strip().upper() for symbol in position.get("legs", []) if symbol and symbol.strip()]


def _position_leg_signature(legs: list[str]) -> tuple[str, ...]:
    return tuple(sorted(symbol.strip().upper() for symbol in legs if symbol and symbol.strip()))


def _exit_urgency_bucket(exit_date: date | None, *, as_of: date) -> tuple[str, int | None]:
    if exit_date is None:
        return "unknown", None
    days_to_exit = (exit_date - as_of).days
    if days_to_exit < 0:
        return "overdue", days_to_exit
    if days_to_exit == 0:
        return "due_today", days_to_exit
    if days_to_exit <= 7:
        return "due_this_week", days_to_exit
    if days_to_exit <= 14:
        return "next_2_weeks", days_to_exit
    return "later", days_to_exit


def _resolve_open_position_exit_schedules(
    positions: list[dict[str, Any]],
    *,
    as_of: date,
) -> dict[str, Any]:
    normalized_positions = _normalize_exit_positions(positions)
    with database.session() as session:
        current_issue = session.execute(
            select(Newsletter).order_by(desc(Newsletter.week_ended))
        ).scalars().first()

        rows = session.execute(
            select(WatchlistEntry, Newsletter.week_ended)
            .join(Newsletter, WatchlistEntry.newsletter_id == Newsletter.id)
            .order_by(desc(Newsletter.week_ended), WatchlistEntry.page_number, WatchlistEntry.id)
        ).all()

        entries_by_signature: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for entry, week_ended in rows:
            signature = _position_leg_signature(
                [leg["tos_symbol"] for leg in _parse_spread_legs(entry.spread_code)]
            )
            if not signature:
                continue
            entries_by_signature[signature].append(
                {
                    "newsletter_id": entry.newsletter_id,
                    "week_ended": week_ended,
                    "commodity_name": entry.commodity_name,
                    "spread_code": entry.spread_code,
                    "section_name": entry.section_name,
                    "enter_date": entry.enter_date,
                    "exit_date": entry.exit_date,
                    "trade_quality": entry.trade_quality,
                    "portfolio": entry.portfolio,
                }
            )

    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for position in normalized_positions:
        signature = _position_leg_signature(_expand_position_legs(position))
        matches = entries_by_signature.get(signature, [])
        result: dict[str, Any] = {
            "position_id": position.get("id") or position.get("position_id"),
            "position_name": position.get("name") or position.get("position_name"),
            "legs": list(signature),
            "matched": False,
            "alignment_status": "unmatched",
            "matched_week_ended": None,
            "commodity_name": None,
            "spread_code": None,
            "section_name": None,
            "classification": None,
            "enter_date": None,
            "exit_date": None,
            "urgency_bucket": "unknown",
            "days_to_exit": None,
        }
        if matches:
            match = matches[0]
            urgency_bucket, days_to_exit = _exit_urgency_bucket(match["exit_date"], as_of=as_of)
            result.update(
                {
                    "matched": True,
                    "alignment_status": (
                        "current_watchlist"
                        if current_issue is not None and match["week_ended"] == current_issue.week_ended
                        else "legacy_carryover"
                    ),
                    "matched_week_ended": match["week_ended"].isoformat(),
                    "commodity_name": match["commodity_name"],
                    "spread_code": match["spread_code"],
                    "section_name": match["section_name"],
                    "classification": match["trade_quality"] or match["portfolio"],
                    "enter_date": match["enter_date"].isoformat(),
                    "exit_date": match["exit_date"].isoformat(),
                    "urgency_bucket": urgency_bucket,
                    "days_to_exit": days_to_exit,
                }
            )
        counts[result["urgency_bucket"]] += 1
        results.append(result)

    return {
        "as_of": as_of.isoformat(),
        "current_issue_week_ended": current_issue.week_ended.isoformat() if current_issue is not None else None,
        "position_count": len(normalized_positions),
        "urgency_counts": dict(counts),
        "positions": results,
    }


def _build_daily_exit_schedule_from_schwab_positions(
    schwab_futures_positions: dict[str, Any],
    *,
    as_of: date,
) -> dict[str, Any]:
    futures_legs = schwab_futures_positions.get("futures_legs", [])
    spread_rows = {
        row.get("id"): row
        for row in schwab_futures_positions.get("spreads", [])
        if isinstance(row, dict) and row.get("id")
    }

    resolved = _resolve_open_position_exit_schedules(futures_legs, as_of=as_of)
    for position in resolved["positions"]:
        spread = spread_rows.get(position.get("position_id"))
        position["spread_type"] = spread.get("type") if spread else None
        position["entry_value"] = spread.get("entry_value") if spread else None
        position["current_value"] = spread.get("current_value") if spread else None
        position["spread_pl"] = spread.get("spread_pl") if spread else None
        position["marks_live"] = spread.get("marks_live") if spread else None
        position["spread_error"] = spread.get("error") if spread else None

    return resolved


def _serialize_publication_yaml(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2)


def _normalize_catalog_text(value: str | None) -> str:
    if value is None:
        return ""
    cleaned = value.replace("\ufeff", "").replace("Â®", "®").replace("Â", "").strip()
    return cleaned


def _normalize_symbol_root(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    return normalized if normalized.startswith("/") else f"/{normalized.lstrip('/')}"


def _derive_broker_symbol_root(
    *,
    commodity_name: str,
    newsletter_root: str,
    globex_symbol_root: str | None,
    existing_mapping: NewsletterCommodityCatalog | None = None,
) -> tuple[str | None, str]:
    preserved = _normalize_symbol_root(
        getattr(existing_mapping, "broker_symbol_root", None)
        or getattr(existing_mapping, "preferred_schwab_root", None)
    )
    if preserved:
        return preserved, "preserved_mapping"

    normalized_globex = _normalize_symbol_root(globex_symbol_root)
    with database.session() as session:
        active_rows = session.execute(
            select(SchwabFuturesCatalog).where(SchwabFuturesCatalog.is_active.is_(True))
        ).scalars().all()

    active_roots = {row.symbol_root: row for row in active_rows}
    if normalized_globex and normalized_globex in active_roots:
        return normalized_globex, "schwab_catalog_exact"

    commodity_tokens = {
        token.lower()
        for token in re.split(r"[^A-Za-z0-9]+", commodity_name)
        if token
    }
    candidate_matches: list[SchwabFuturesCatalog] = []
    for row in active_rows:
        display_tokens = {
            token.lower()
            for token in re.split(r"[^A-Za-z0-9]+", row.display_name)
            if token
        }
        if commodity_tokens & display_tokens:
            candidate_matches.append(row)

    if len(candidate_matches) == 1:
        return candidate_matches[0].symbol_root, "schwab_catalog_name_match"

    return normalized_globex, "newsletter_globex_fallback"


def _extract_commodity_details_text(raw_text: str) -> str:
    normalized = _normalize_catalog_text(raw_text)
    match = re.search(r"commodity\s+details", normalized, flags=re.IGNORECASE)
    if match is None:
        return ""
    tail = normalized[match.start():]
    stop_candidates = [
        index
        for index in [
            tail.lower().find("what to expect from"),
            tail.lower().find("watch list"),
            tail.lower().find("trade calendar"),
        ]
        if index > 0
    ]
    if stop_candidates:
        tail = tail[: min(stop_candidates)]
    return tail


def _parse_newsletter_commodity_rows(raw_text: str) -> list[dict[str, Any]]:
    details_text = _extract_commodity_details_text(raw_text)
    if not details_text:
        return []

    rows: list[dict[str, Any]] = []
    seen_roots: set[str] = set()
    for match in COMMODITY_DETAILS_ROW_RE.finditer(details_text):
        newsletter_root = match.group("newsletter_root").strip().upper()
        if newsletter_root in seen_roots:
            continue
        seen_roots.add(newsletter_root)

        commodity_name = " ".join(match.group("commodity").split())
        exchange = match.group("exchange").strip().upper()
        globex_root = f"/{match.group('globex_root').strip().upper()}"
        policy_block_reason = ROOT_BLOCK_REASONS.get(newsletter_root)
        rows.append(
            {
                "newsletter_root": newsletter_root,
                "commodity_name": commodity_name,
                "exchange": exchange,
                "globex_symbol_root": globex_root,
                "preferred_schwab_root": globex_root,
                "is_tradeable_by_policy": False if policy_block_reason else None,
                "policy_block_reason": policy_block_reason,
            }
        )

    return rows


def _parse_contract_month_codes(raw_text: str) -> list[dict[str, Any]]:
    details_text = _extract_commodity_details_text(raw_text)
    if not details_text:
        return []

    rows: list[dict[str, Any]] = []
    sort_lookup = {name.lower(): index for index, name in enumerate(MONTH_NAME_ORDER, start=1)}

    def month_pattern(name: str) -> str:
        return r"\s*".join(re.escape(char) for char in name)

    month_code_map = {
        "January": "F",
        "February": "G",
        "March": "H",
        "April": "J",
        "May": "K",
        "June": "M",
        "July": "N",
        "August": "Q",
        "September": "U",
        "October": "V",
        "November": "X",
        "December": "Z",
    }

    for month_name in MONTH_NAME_ORDER:
        month_code = month_code_map[month_name]
        pattern = rf"{month_pattern(month_name)}\s+{re.escape(month_code)}"
        if re.search(pattern, details_text, flags=re.IGNORECASE):
            rows.append(
                {
                    "month_code": month_code,
                    "month_name": month_name,
                    "sort_order": sort_lookup[month_name.lower()],
                }
            )

    rows.sort(key=lambda row: row["sort_order"])
    return rows


def _parse_yes_no(value: str | None) -> bool | None:
    normalized = _normalize_catalog_text(value).lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _is_catalog_section_row(row: list[str]) -> bool:
    if not row:
        return False
    first = _normalize_catalog_text(row[0])
    if not first or first == "View Less":
        return False
    remaining = [_normalize_catalog_text(cell) for cell in row[1:]]
    return all(not cell for cell in remaining)


def _extract_schwab_catalog_rows(csv_path: Path) -> list[dict[str, Any]]:
    parsed_rows: list[dict[str, Any]] = []
    seen_roots: set[str] = set()
    current_category = "Uncategorized"

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for raw_row in reader:
            row = [_normalize_catalog_text(cell) for cell in raw_row]
            if not any(row):
                continue
            if _is_catalog_section_row(row):
                current_category = row[0]
                continue
            if row[0] == "View Less":
                continue
            if row[0] == "" and len(row) > 1 and row[1] == "Symbol":
                continue

            display_name = row[0] if len(row) > 0 else ""
            symbol_root = row[1] if len(row) > 1 else ""
            if not display_name or not symbol_root.startswith("/"):
                continue
            if symbol_root in seen_roots:
                continue
            seen_roots.add(symbol_root)

            parsed_rows.append(
                {
                    "symbol_root": symbol_root,
                    "display_name": display_name,
                    "category": current_category,
                    "options_tradable": _parse_yes_no(row[2] if len(row) > 2 else None),
                    "multiplier": row[3] if len(row) > 3 else None,
                    "minimum_tick_size": row[4] if len(row) > 4 else None,
                    "settlement_type": row[5] if len(row) > 5 else None,
                    "trading_hours": row[6] if len(row) > 6 else None,
                    "is_micro": "micro" in display_name.lower(),
                    "stream_supported": None,
                }
            )

    return parsed_rows


def _serialize_schwab_catalog_row(record: SchwabFuturesCatalog) -> dict[str, Any]:
    return {
        "symbol_root": record.symbol_root,
        "display_name": record.display_name,
        "category": record.category,
        "options_tradable": record.options_tradable,
        "multiplier": record.multiplier,
        "minimum_tick_size": record.minimum_tick_size,
        "settlement_type": record.settlement_type,
        "trading_hours": record.trading_hours,
        "is_micro": record.is_micro,
        "stream_supported": record.stream_supported,
        "native_spread_support": record.native_spread_support,
        "manual_legs_required": record.manual_legs_required,
        "support_notes": record.support_notes,
        "is_active": record.is_active,
        "source_file": record.source_file,
        "source_modified_at": record.source_modified_at.isoformat() if record.source_modified_at else None,
    }


def _load_schwab_catalog_support(symbol_root: str | None) -> dict[str, Any]:
    if not symbol_root:
        return {
            "stream_supported": None,
            "native_spread_support": None,
            "manual_legs_required": None,
            "support_notes": None,
        }
    with database.session() as session:
        record = session.execute(
            select(SchwabFuturesCatalog).where(
                SchwabFuturesCatalog.symbol_root == symbol_root,
                SchwabFuturesCatalog.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if record is None:
            return {
                "stream_supported": None,
                "native_spread_support": None,
                "manual_legs_required": None,
                "support_notes": None,
            }
        return {
            "stream_supported": record.stream_supported,
            "native_spread_support": record.native_spread_support,
            "manual_legs_required": record.manual_legs_required,
            "support_notes": record.support_notes,
        }


def _build_issue_brief_markdown(
    newsletter: Newsletter,
    brief: IssueBrief | None,
    delta: IssueDelta | None,
    reference: WatchlistReferenceRecord | None,
    entries: list[WatchlistEntry],
) -> str:
    brief_data = _issue_brief_fallback(newsletter, entries, delta, reference, brief)
    return IssueBriefService.build_issue_brief_markdown(
        week_ended=newsletter.week_ended.isoformat(),
        title=newsletter.title,
        executive_summary=brief_data.executive_summary,
        entries=entries,
        brief_data=brief_data,
        delta_summary_text=delta.summary_text if delta is not None else None,
        reference=reference,
    )


def _build_weekly_intelligence_payload(
    newsletter: Newsletter,
    entries: list[WatchlistEntry],
    brief: IssueBrief | None,
    delta: IssueDelta | None,
    reference: WatchlistReferenceRecord | None,
) -> dict[str, Any]:
    brief_data = _issue_brief_fallback(newsletter, entries, delta, reference, brief)
    return {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "week_ended": newsletter.week_ended.isoformat(),
        "newsletter_id": newsletter.id,
        "title": newsletter.title,
        "issue_status": newsletter.issue_status,
        "source_file": newsletter.source_file,
        "published_context": {
            "entry_count": len(entries),
            "section_counts": brief_data.watchlist_summary.get("section_counts", {}),
            "principle_context": _build_principle_context(entries),
        },
        "issue_brief": {
            "headline": brief_data.headline,
            "executive_summary": brief_data.executive_summary,
            "watchlist_summary": brief_data.watchlist_summary,
            "change_summary": brief_data.change_summary,
            "key_themes": brief_data.key_themes,
            "notable_risks": brief_data.notable_risks,
            "notable_opportunities": brief_data.notable_opportunities,
        },
        "issue_delta": {
            "summary_text": delta.summary_text if delta is not None else None,
            "added_entries": delta.added_entries_json if delta is not None else [],
            "removed_entries": delta.removed_entries_json if delta is not None else [],
            "changed_entries": delta.changed_entries_json if delta is not None else [],
        },
        "watchlist_reference": _serialize_watchlist_reference(reference),
    }


def _build_publication_manifest(
    *,
    newsletter: Newsletter,
    publication_version: str,
    publication_run_id: int,
    output_root: Path,
    files: dict[str, str],
    watchlist_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "publication_run_id": publication_run_id,
        "publication_version": publication_version,
        "week_ended": newsletter.week_ended.isoformat(),
        "newsletter_id": newsletter.id,
        "title": newsletter.title,
        "published_at": _utcnow().isoformat(),
        "output_root": str(output_root),
        "files": files,
        "watchlist_count": len(watchlist_payload["watchlist"]),
}


def _summarize_watchlist_rows(rows: list[Any]) -> dict[str, Any]:
    return IssueBriefService.summarize_watchlist_rows(rows)


def _build_issue_brief_draft(
    *,
    title: str,
    executive_summary: str,
    entries: list[Any],
    delta: IssueDelta | None,
    reference: WatchlistReferenceRecord | None,
) -> IssueBriefDraft:
    return IssueBriefService.build_issue_brief(
        title=title,
        executive_summary=executive_summary,
        entries=entries,
        delta=delta,
        reference=reference,
    )


def _apply_issue_brief_draft(
    issue_brief: IssueBrief,
    *,
    parser_run_id: int | None,
    brief_data: IssueBriefDraft,
) -> None:
    issue_brief.parser_run_id = parser_run_id
    issue_brief.brief_status = issue_brief.brief_status or "draft"
    issue_brief.headline = brief_data.headline
    issue_brief.executive_summary = brief_data.executive_summary
    issue_brief.key_themes_json = brief_data.key_themes
    issue_brief.notable_risks_json = brief_data.notable_risks
    issue_brief.notable_opportunities_json = brief_data.notable_opportunities
    issue_brief.watchlist_summary_json = brief_data.watchlist_summary
    issue_brief.change_summary_json = brief_data.change_summary


def _issue_brief_fallback(
    newsletter: Newsletter,
    entries: list[WatchlistEntry],
    delta: IssueDelta | None,
    reference: WatchlistReferenceRecord | None,
    brief: IssueBrief | None,
) -> IssueBriefDraft:
    if brief is not None:
        return IssueBriefDraft(
            headline=brief.headline or newsletter.title,
            executive_summary=brief.executive_summary,
            key_themes=brief.key_themes_json,
            notable_risks=brief.notable_risks_json,
            notable_opportunities=brief.notable_opportunities_json,
            watchlist_summary=brief.watchlist_summary_json,
            change_summary=brief.change_summary_json,
        )
    return _build_issue_brief_draft(
        title=newsletter.title,
        executive_summary=newsletter.overall_summary,
        entries=entries,
        delta=delta,
        reference=reference,
    )


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
        canonical_key = _canonical_entry_key(newsletter, entry)
        if entry.entry_key != canonical_key:
            entry.entry_key = canonical_key
        if entry.parser_run_id is None:
            entry.parser_run_id = parser_run.id
        if entry.publication_state is None:
            entry.publication_state = "candidate"
        if entry.metadata_json is None:
            entry.metadata_json = {}

    _evaluate_issue_entries(session, newsletter=newsletter, entries=list(newsletter.watchlist_entries))

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
    if previous_newsletter is None:
        added_entries = []
        removed_entries = []
        changed_entries = []
        delta_summary = "No prior issue available for comparison."
    else:
        added_entries, removed_entries, changed_entries, delta_summary = _compute_issue_delta(
            list(newsletter.watchlist_entries),
            list(previous_entries),
        )

    issue_delta = session.execute(
        select(IssueDelta).where(IssueDelta.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    if issue_delta is None:
        issue_delta = IssueDelta(
            newsletter_id=newsletter.id,
            previous_newsletter_id=previous_newsletter.id if previous_newsletter is not None else None,
            delta_status="generated",
            added_entries_json=added_entries,
            removed_entries_json=removed_entries,
            changed_entries_json=changed_entries,
            summary_text=delta_summary,
        )
        session.add(issue_delta)
    else:
        issue_delta.previous_newsletter_id = previous_newsletter.id if previous_newsletter is not None else None
        issue_delta.delta_status = "generated"
        issue_delta.added_entries_json = added_entries
        issue_delta.removed_entries_json = removed_entries
        issue_delta.changed_entries_json = changed_entries
        issue_delta.summary_text = delta_summary

    issue_brief = session.execute(
        select(IssueBrief).where(IssueBrief.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    brief_data = _build_issue_brief_draft(
        title=newsletter.title,
        executive_summary=newsletter.overall_summary,
        entries=list(newsletter.watchlist_entries),
        delta=issue_delta,
        reference=newsletter.watchlist_reference,
    )
    if issue_brief is None:
        session.add(
            IssueBrief(
                newsletter_id=newsletter.id,
                parser_run_id=parser_run.id,
                brief_status="draft",
                headline=brief_data.headline,
                executive_summary=brief_data.executive_summary,
                key_themes_json=brief_data.key_themes,
                notable_risks_json=brief_data.notable_risks,
                notable_opportunities_json=brief_data.notable_opportunities,
                watchlist_summary_json=brief_data.watchlist_summary,
                change_summary_json=brief_data.change_summary,
            )
        )
    else:
        _apply_issue_brief_draft(
            issue_brief,
            parser_run_id=parser_run.id,
            brief_data=brief_data,
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
        "delta_summary": None if previous_newsletter is None else delta_summary,
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
            run_started_at=_utcnow(),
            run_completed_at=_utcnow(),
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
        _evaluate_issue_entries(session, newsletter=newsletter, entries=current_entries)
        previous_newsletter = _get_previous_newsletter(session, newsletter.week_ended)
        previous_entries: list[WatchlistEntry] = []
        if previous_newsletter is not None:
            previous_entries = session.execute(
                select(WatchlistEntry)
                .where(WatchlistEntry.newsletter_id == previous_newsletter.id)
                .order_by(WatchlistEntry.id)
            ).scalars().all()

        if previous_newsletter is None:
            added_entries = []
            removed_entries = []
            changed_entries = []
            delta_summary = "No prior issue available for comparison."
        else:
            added_entries, removed_entries, changed_entries, delta_summary = _compute_issue_delta(
                current_entries,
                previous_entries,
            )

        issue_delta = IssueDelta(
            newsletter_id=newsletter.id,
            previous_newsletter_id=previous_newsletter.id if previous_newsletter is not None else None,
            delta_status="generated",
            added_entries_json=added_entries,
            removed_entries_json=removed_entries,
            changed_entries_json=changed_entries,
            summary_text=delta_summary,
        )
        session.add(
            issue_delta
        )
        brief_data = _build_issue_brief_draft(
            title=newsletter.title,
            executive_summary=newsletter.overall_summary,
            entries=current_entries,
            delta=issue_delta,
            reference=newsletter.watchlist_reference,
        )
        session.add(
            IssueBrief(
                newsletter_id=newsletter.id,
                parser_run_id=parser_run.id,
                brief_status="draft",
                headline=brief_data.headline,
                executive_summary=brief_data.executive_summary,
                key_themes_json=brief_data.key_themes,
                notable_risks_json=brief_data.notable_risks,
                notable_opportunities_json=brief_data.notable_opportunities,
                watchlist_summary_json=brief_data.watchlist_summary,
                change_summary_json=brief_data.change_summary,
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
            "delta_summary": None if previous_newsletter is None else delta_summary,
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


def _refresh_issue_records(session: Any, week_ended: str) -> tuple[Newsletter, dict[str, Any]]:
    newsletter = session.execute(
        select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
    ).scalar_one_or_none()
    if newsletter is None:
        raise ValueError(f"No newsletter found for {week_ended}")
    seeded = _seed_phase1_records(session, newsletter)
    return newsletter, seeded


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
def refresh_and_publish_issue(
    week_ended: str,
    output_dir: str | None = None,
    publication_version: str | None = None,
    published_by: str | None = None,
) -> dict[str, Any]:
    """Refresh stored Phase 1 intelligence for an issue, then publish the latest artifacts."""
    with database.session() as session:
        newsletter, seeded = _refresh_issue_records(session, week_ended)
        refreshed_summary = {
            "week_ended": newsletter.week_ended.isoformat(),
            "parser_run_id": seeded["parser_run_id"],
            "delta_summary": seeded["delta_summary"],
            "issue_status": newsletter.issue_status,
        }

    published = publish_issue(
        week_ended=week_ended,
        output_dir=output_dir,
        publication_version=publication_version,
        published_by=published_by,
    )
    return {
        "refreshed": refreshed_summary,
        "published": published,
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
def import_schwab_futures_catalog(csv_path: str | None = None) -> dict[str, Any]:
    """Import the Schwab futures symbol catalog from a CSV export into the database."""
    source_path = Path(csv_path) if csv_path else DEFAULT_SCHWAB_CATALOG_CSV
    if not source_path.exists():
        raise ValueError(f"Schwab futures catalog CSV not found at {source_path}")

    parsed_rows = _extract_schwab_catalog_rows(source_path)
    if not parsed_rows:
        raise ValueError(f"No Schwab futures catalog rows were parsed from {source_path}")

    source_modified_at = datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)
    imported = 0
    updated = 0
    seen_roots = {row["symbol_root"] for row in parsed_rows}

    with database.session() as session:
        existing_rows = {
            record.symbol_root: record
            for record in session.execute(select(SchwabFuturesCatalog)).scalars().all()
        }

        for row in parsed_rows:
            existing = existing_rows.get(row["symbol_root"])
            if existing is None:
                session.add(
                    SchwabFuturesCatalog(
                        symbol_root=row["symbol_root"],
                        display_name=row["display_name"],
                        category=row["category"],
                        options_tradable=row["options_tradable"],
                        multiplier=row["multiplier"],
                        minimum_tick_size=row["minimum_tick_size"],
                        settlement_type=row["settlement_type"],
                        trading_hours=row["trading_hours"],
                        is_micro=row["is_micro"],
                        stream_supported=row["stream_supported"],
                        source_file=str(source_path),
                        source_modified_at=source_modified_at,
                        is_active=True,
                        metadata_json={},
                    )
                )
                imported += 1
                continue

            existing.display_name = row["display_name"]
            existing.category = row["category"]
            existing.options_tradable = row["options_tradable"]
            existing.multiplier = row["multiplier"]
            existing.minimum_tick_size = row["minimum_tick_size"]
            existing.settlement_type = row["settlement_type"]
            existing.trading_hours = row["trading_hours"]
            existing.is_micro = row["is_micro"]
            existing.source_file = str(source_path)
            existing.source_modified_at = source_modified_at
            existing.is_active = True
            updated += 1

        for symbol_root, record in existing_rows.items():
            if record.source_file == str(source_path) and symbol_root not in seen_roots:
                record.is_active = False

        category_counts = Counter(row["category"] for row in parsed_rows)

    return {
        "csv_path": str(source_path),
        "source_modified_at": source_modified_at.isoformat(),
        "row_count": len(parsed_rows),
        "imported_count": imported,
        "updated_count": updated,
        "category_counts": dict(category_counts),
        "sample_symbols": sorted(seen_roots)[:10],
    }


@mcp.tool()
def list_schwab_futures_catalog(limit: int = 25, category: str | None = None) -> dict[str, Any]:
    """List rows from the imported Schwab futures symbol catalog."""
    with database.session() as session:
        stmt = select(SchwabFuturesCatalog).where(SchwabFuturesCatalog.is_active.is_(True))
        if category:
            stmt = stmt.where(SchwabFuturesCatalog.category == category)
        stmt = stmt.order_by(SchwabFuturesCatalog.category, SchwabFuturesCatalog.symbol_root).limit(limit)
        rows = session.execute(stmt).scalars().all()

        categories = Counter(
            session.execute(
                select(SchwabFuturesCatalog.category).where(SchwabFuturesCatalog.is_active.is_(True))
            ).scalars().all()
        )

        return {
            "count": len(rows),
            "categories": dict(categories),
            "rows": [_serialize_schwab_catalog_row(row) for row in rows],
        }


@mcp.tool()
def upsert_schwab_futures_support(
    symbol_root: str,
    *,
    stream_supported: bool | None = None,
    native_spread_support: bool | None = None,
    manual_legs_required: bool | None = None,
    support_notes: str | None = None,
) -> dict[str, Any]:
    """Update operational support flags for a Schwab futures symbol."""
    normalized_root = symbol_root.strip().upper()
    if not normalized_root.startswith("/"):
        normalized_root = f"/{normalized_root.lstrip('/')}"

    with database.session() as session:
        record = session.execute(
            select(SchwabFuturesCatalog).where(SchwabFuturesCatalog.symbol_root == normalized_root)
        ).scalar_one_or_none()
        if record is None:
            raise ValueError(f"No Schwab futures catalog row found for {normalized_root}")

        record.stream_supported = stream_supported
        record.native_spread_support = native_spread_support
        record.manual_legs_required = manual_legs_required
        record.support_notes = support_notes

        return {
            "updated": normalized_root,
            "row": _serialize_schwab_catalog_row(record),
        }


def _serialize_newsletter_commodity_mapping(record: NewsletterCommodityCatalog) -> dict[str, Any]:
    return {
        "newsletter_root": record.newsletter_root,
        "commodity_name": record.commodity_name,
        "category": record.category,
        "exchange": record.exchange,
        "globex_symbol_root": record.globex_symbol_root,
        "broker_symbol_root": record.broker_symbol_root or record.preferred_schwab_root,
        "preferred_schwab_root": record.preferred_schwab_root,
        "alternate_schwab_roots": record.alternate_schwab_roots_json,
        "is_tradeable_by_policy": record.is_tradeable_by_policy,
        "policy_block_reason": record.policy_block_reason,
        "mapping_confidence": record.mapping_confidence,
        "mapping_notes": record.mapping_notes,
        "source_issue_week": record.source_issue_week.isoformat() if record.source_issue_week else None,
        "source_page_number": record.source_page_number,
    }


@mcp.tool()
def upsert_newsletter_commodity_mapping(
    newsletter_root: str,
    commodity_name: str,
    preferred_schwab_root: str | None = None,
    globex_symbol_root: str | None = None,
    broker_symbol_root: str | None = None,
    category: str | None = None,
    exchange: str | None = None,
    alternate_schwab_roots: list[str] | None = None,
    is_tradeable_by_policy: bool | None = None,
    policy_block_reason: str | None = None,
    mapping_confidence: float | None = None,
    mapping_notes: str | None = None,
) -> dict[str, Any]:
    """Create or update a newsletter commodity to Schwab root mapping."""
    root = newsletter_root.strip().upper()
    preferred_root = preferred_schwab_root.strip().upper() if preferred_schwab_root else None
    if preferred_root and not preferred_root.startswith("/"):
        preferred_root = f"/{preferred_root.lstrip('/')}"
    globex_root = _normalize_symbol_root(globex_symbol_root)
    broker_root = _normalize_symbol_root(broker_symbol_root) or preferred_root
    preferred_root = preferred_root or broker_root

    alternate_roots = [value.strip().upper() for value in (alternate_schwab_roots or []) if value.strip()]
    alternate_roots = [value if value.startswith("/") else f"/{value.lstrip('/')}" for value in alternate_roots]

    with database.session() as session:
        existing = session.execute(
            select(NewsletterCommodityCatalog).where(NewsletterCommodityCatalog.newsletter_root == root)
        ).scalar_one_or_none()

        if existing is None:
            record = NewsletterCommodityCatalog(
                newsletter_root=root,
                commodity_name=commodity_name,
                category=category,
                exchange=exchange,
                globex_symbol_root=globex_root,
                broker_symbol_root=broker_root,
                preferred_schwab_root=preferred_root,
                alternate_schwab_roots_json=alternate_roots,
                is_tradeable_by_policy=is_tradeable_by_policy,
                policy_block_reason=policy_block_reason,
                mapping_confidence=mapping_confidence,
                mapping_notes=mapping_notes,
                metadata_json={},
            )
            session.add(record)
            session.flush()
            action = "created"
        else:
            existing.commodity_name = commodity_name
            existing.category = category
            existing.exchange = exchange
            existing.globex_symbol_root = globex_root
            existing.broker_symbol_root = broker_root
            existing.preferred_schwab_root = preferred_root
            existing.alternate_schwab_roots_json = alternate_roots
            existing.is_tradeable_by_policy = is_tradeable_by_policy
            existing.policy_block_reason = policy_block_reason
            existing.mapping_confidence = mapping_confidence
            existing.mapping_notes = mapping_notes
            record = existing
            action = "updated"

        return {
            "action": action,
            "mapping": _serialize_newsletter_commodity_mapping(record),
        }


@mcp.tool()
def list_newsletter_commodity_catalog(limit: int = 50) -> dict[str, Any]:
    """List newsletter commodity mappings currently stored in the database."""
    with database.session() as session:
        rows = session.execute(
            select(NewsletterCommodityCatalog)
            .order_by(NewsletterCommodityCatalog.newsletter_root)
            .limit(limit)
        ).scalars().all()
        return {
            "count": len(rows),
            "rows": [_serialize_newsletter_commodity_mapping(row) for row in rows],
        }


@mcp.tool()
def import_newsletter_commodity_catalog(week_ended: str | None = None) -> dict[str, Any]:
    """Import newsletter commodity/root mappings from the Commodity Details page of an issue."""
    with database.session() as session:
        if week_ended:
            newsletter = session.execute(
                select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
            ).scalar_one_or_none()
            if newsletter is None:
                raise ValueError(f"No newsletter found for {week_ended}")
        else:
            newsletter = session.execute(
                select(Newsletter).order_by(desc(Newsletter.week_ended))
            ).scalars().first()
            if newsletter is None:
                raise ValueError("No newsletters available to import commodity mappings from.")

        parsed_rows = _parse_newsletter_commodity_rows(newsletter.raw_text)
        if not parsed_rows:
            raise ValueError(
                f"No commodity details rows were parsed from newsletter {newsletter.week_ended.isoformat()}."
            )

        imported = 0
        updated = 0
        for row in parsed_rows:
            existing = session.execute(
                select(NewsletterCommodityCatalog).where(
                    NewsletterCommodityCatalog.newsletter_root == row["newsletter_root"]
                )
            ).scalar_one_or_none()

            if existing is None:
                broker_root, derivation_source = _derive_broker_symbol_root(
                    commodity_name=row["commodity_name"],
                    newsletter_root=row["newsletter_root"],
                    globex_symbol_root=row.get("globex_symbol_root"),
                )
                session.add(
                    NewsletterCommodityCatalog(
                        newsletter_root=row["newsletter_root"],
                        commodity_name=row["commodity_name"],
                        exchange=row["exchange"],
                        globex_symbol_root=row.get("globex_symbol_root"),
                        broker_symbol_root=broker_root,
                        preferred_schwab_root=broker_root,
                        is_tradeable_by_policy=row["is_tradeable_by_policy"],
                        policy_block_reason=row["policy_block_reason"],
                        source_issue_week=newsletter.week_ended,
                        source_page_number=2,
                        metadata_json={"broker_root_source": derivation_source},
                    )
                )
                imported += 1
                continue

            broker_root, derivation_source = _derive_broker_symbol_root(
                commodity_name=row["commodity_name"],
                newsletter_root=row["newsletter_root"],
                globex_symbol_root=row.get("globex_symbol_root"),
                existing_mapping=existing,
            )
            existing.commodity_name = row["commodity_name"]
            existing.exchange = row["exchange"]
            existing.globex_symbol_root = row.get("globex_symbol_root")
            existing.broker_symbol_root = broker_root
            existing.preferred_schwab_root = broker_root
            existing.is_tradeable_by_policy = row["is_tradeable_by_policy"]
            existing.policy_block_reason = row["policy_block_reason"]
            existing.source_issue_week = newsletter.week_ended
            existing.source_page_number = 2
            existing.metadata_json = {
                **(existing.metadata_json or {}),
                "broker_root_source": derivation_source,
            }
            updated += 1

        return {
            "week_ended": newsletter.week_ended.isoformat(),
            "row_count": len(parsed_rows),
            "imported_count": imported,
            "updated_count": updated,
            "newsletter_roots": [row["newsletter_root"] for row in parsed_rows],
        }


@mcp.tool()
def import_contract_month_codes(week_ended: str | None = None) -> dict[str, Any]:
    """Import contract month-code mappings from the Commodity Details page of an issue."""
    with database.session() as session:
        if week_ended:
            newsletter = session.execute(
                select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
            ).scalar_one_or_none()
            if newsletter is None:
                raise ValueError(f"No newsletter found for {week_ended}")
        else:
            newsletter = session.execute(
                select(Newsletter).order_by(desc(Newsletter.week_ended))
            ).scalars().first()
            if newsletter is None:
                raise ValueError("No newsletters available to import month codes from.")

        parsed_rows = _parse_contract_month_codes(newsletter.raw_text)
        if not parsed_rows:
            raise ValueError(
                f"No contract month codes were parsed from newsletter {newsletter.week_ended.isoformat()}."
            )

        imported = 0
        updated = 0
        for row in parsed_rows:
            existing = session.execute(
                select(ContractMonthCode).where(ContractMonthCode.month_code == row["month_code"])
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    ContractMonthCode(
                        month_code=row["month_code"],
                        month_name=row["month_name"],
                        sort_order=row["sort_order"],
                        source_issue_week=newsletter.week_ended,
                        source_page_number=2,
                        metadata_json={},
                    )
                )
                imported += 1
                continue

            existing.month_name = row["month_name"]
            existing.sort_order = row["sort_order"]
            existing.source_issue_week = newsletter.week_ended
            existing.source_page_number = 2
            updated += 1

        return {
            "week_ended": newsletter.week_ended.isoformat(),
            "row_count": len(parsed_rows),
            "imported_count": imported,
            "updated_count": updated,
            "month_codes": [row["month_code"] for row in parsed_rows],
        }


@mcp.tool()
def list_contract_month_codes() -> dict[str, Any]:
    """List the stored contract month-code mappings."""
    with database.session() as session:
        rows = session.execute(
            select(ContractMonthCode).order_by(ContractMonthCode.sort_order)
        ).scalars().all()
        return {
            "count": len(rows),
            "rows": [
                {
                    "month_code": row.month_code,
                    "month_name": row.month_name,
                    "sort_order": row.sort_order,
                    "source_issue_week": row.source_issue_week.isoformat() if row.source_issue_week else None,
                    "source_page_number": row.source_page_number,
                }
                for row in rows
            ],
        }


@mcp.tool()
def import_strategy_manual(pdf_path: str | None = None) -> dict[str, Any]:
    """Import the Smart Spreads strategy manual into the doctrine knowledge tables."""
    source_path = Path(pdf_path) if pdf_path else DEFAULT_STRATEGY_MANUAL_PATH
    if not source_path.exists():
        raise ValueError(f"Strategy manual PDF not found at {source_path}")

    extracted = _extract_strategy_pdf(source_path)
    if not extracted["sections"]:
        raise ValueError(f"No strategy chapters were extracted from {source_path}")

    file_hash = _sha256_file(source_path)
    source_modified_at = datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)
    summary_text = _build_strategy_document_summary(extracted)
    metadata = {
        "page_count": extracted["page_count"],
        "chapter_count": len(extracted["sections"]),
        "source_modified_at": source_modified_at.isoformat(),
    }

    with database.session() as session:
        document = session.execute(
            select(StrategyDocument).where(StrategyDocument.source_file == str(source_path))
        ).scalar_one_or_none()
        if document is None:
            document = StrategyDocument(
                title=extracted["title"],
                source_file=str(source_path),
                file_hash=file_hash,
                document_type="strategy_manual",
                author="Darren Carl",
                version_label="Smart Spreads Strategy",
                published_year=2014,
                page_count=extracted["page_count"],
                raw_text=extracted["raw_text"],
                summary_text=summary_text,
                metadata_json=metadata,
            )
            session.add(document)
            session.flush()
            status = "imported"
        else:
            document.title = extracted["title"]
            document.file_hash = file_hash
            document.document_type = "strategy_manual"
            document.author = "Darren Carl"
            document.version_label = "Smart Spreads Strategy"
            document.published_year = 2014
            document.page_count = extracted["page_count"]
            document.raw_text = extracted["raw_text"]
            document.summary_text = summary_text
            document.metadata_json = metadata
            document.sections.clear()
            document.principles.clear()
            session.flush()
            status = "updated"

        section_by_chapter: dict[int, StrategySection] = {}
        for section in extracted["sections"]:
            record = StrategySection(
                strategy_document=document,
                part_number=section["part_number"],
                part_title=section["part_title"],
                chapter_number=section["chapter_number"],
                chapter_title=section["chapter_title"],
                section_label=f"Chapter {section['chapter_number']}",
                page_start=section["page_start"],
                page_end=section["page_end"],
                heading_path=section["heading_path"],
                body_text=section["body_text"],
                summary_text=section["summary_text"],
                keywords_json=section["keywords"],
                metadata_json={},
            )
            session.add(record)
            if section["chapter_number"] is not None:
                section_by_chapter[section["chapter_number"]] = record

        for principle in STRATEGY_PRINCIPLE_SEED:
            chapter_number = principle["chapter_number"]
            section = section_by_chapter.get(chapter_number)
            session.add(
                StrategyPrinciple(
                    strategy_document=document,
                    strategy_section=section,
                    principle_key=principle["principle_key"],
                    principle_title=principle["principle_title"],
                    category=principle["category"],
                    priority=principle["priority"],
                    summary_text=principle["summary_text"],
                    guidance_text=principle["guidance_text"],
                    applies_to_json=principle["applies_to"],
                    examples_json=principle.get("examples", []),
                    anti_patterns_json=principle["anti_patterns"],
                    metadata_json={
                        "chapter_number": chapter_number,
                        "chapter_title": section.chapter_title if section is not None else None,
                    },
                )
            )

        session.flush()
        section_count = session.execute(
            select(StrategySection).where(StrategySection.strategy_document_id == document.id)
        ).scalars().all()
        principle_count = session.execute(
            select(StrategyPrinciple).where(StrategyPrinciple.strategy_document_id == document.id)
        ).scalars().all()

        return {
            "status": status,
            "document": _serialize_strategy_document(document),
            "section_count": len(section_count),
            "principle_count": len(principle_count),
        }


@mcp.tool()
def list_strategy_documents() -> dict[str, Any]:
    """List imported strategy/doctrine documents."""
    with database.session() as session:
        rows = session.execute(
            select(StrategyDocument).order_by(desc(StrategyDocument.updated_at))
        ).scalars().all()
        return {
            "count": len(rows),
            "items": [_serialize_strategy_document(row) for row in rows],
        }


@mcp.tool()
def list_strategy_sections(limit: int = 25, chapter_number: int | None = None) -> dict[str, Any]:
    """List extracted strategy manual chapters/sections."""
    with database.session() as session:
        stmt = select(StrategySection).order_by(
            StrategySection.chapter_number.asc(),
            StrategySection.page_start.asc(),
        )
        if chapter_number is not None:
            stmt = stmt.where(StrategySection.chapter_number == chapter_number)
        rows = session.execute(stmt.limit(limit)).scalars().all()
        return {
            "count": len(rows),
            "items": [_serialize_strategy_section(row) for row in rows],
        }


@mcp.tool()
def list_strategy_principles(category: str | None = None) -> dict[str, Any]:
    """List normalized strategy principles derived from the Smart Spreads strategy manual."""
    with database.session() as session:
        stmt = select(StrategyPrinciple).order_by(
            StrategyPrinciple.priority.asc(),
            StrategyPrinciple.principle_key.asc(),
        )
        if category:
            stmt = stmt.where(StrategyPrinciple.category == category)
        rows = session.execute(stmt).scalars().all()
        return {
            "count": len(rows),
            "items": [_serialize_strategy_principle(row) for row in rows],
        }


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
        brief = session.execute(
            select(IssueBrief).where(IssueBrief.newsletter_id == newsletter.id)
        ).scalar_one_or_none()
        delta = session.execute(
            select(IssueDelta).where(IssueDelta.newsletter_id == newsletter.id)
        ).scalar_one_or_none()
        reference = session.execute(
            select(WatchlistReferenceRecord).where(
                WatchlistReferenceRecord.newsletter_id == newsletter.id
            )
        ).scalar_one_or_none()
        entries = session.execute(
            select(WatchlistEntry)
            .where(WatchlistEntry.newsletter_id == newsletter.id)
            .order_by(WatchlistEntry.page_number, WatchlistEntry.id)
        ).scalars().all()
        brief_data = _issue_brief_fallback(newsletter, entries, delta, reference, brief)

        return {
            "week_ended": newsletter.week_ended.isoformat(),
            "title": newsletter.title,
            "summary": newsletter.overall_summary,
            "issue_brief": {
                "headline": brief_data.headline,
                "executive_summary": brief_data.executive_summary,
                "key_themes": brief_data.key_themes,
                "notable_risks": brief_data.notable_risks,
                "notable_opportunities": brief_data.notable_opportunities,
                "watchlist_summary": brief_data.watchlist_summary,
                "change_summary": brief_data.change_summary,
            },
            "issue_delta": {
                "summary_text": delta.summary_text if delta is not None else None,
                "added_entries": delta.added_entries_json if delta is not None else [],
                "removed_entries": delta.removed_entries_json if delta is not None else [],
                "changed_entries": delta.changed_entries_json if delta is not None else [],
            },
            "watchlist_reference": _serialize_watchlist_reference(reference),
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
    principle_evaluation = (entry.metadata_json or {}).get("principle_evaluation", {})
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
        "tradeable": entry.tradeable,
        "blocked_reason": entry.blocked_reason,
        "principle_scores": principle_evaluation.get("principle_scores", {}),
        "principle_status": principle_evaluation.get("principle_status", {}),
        "decision_summary": principle_evaluation.get("decision_summary"),
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


def _get_issue_bundle(session: Any, week_ended: str) -> tuple[Newsletter, list[WatchlistEntry], WatchlistReferenceRecord | None, IssueBrief | None, IssueDelta | None]:
    newsletter = session.execute(
        select(Newsletter).where(Newsletter.week_ended == _parse_issue_date(week_ended))
    ).scalar_one_or_none()
    if newsletter is None:
        raise ValueError(f"No newsletter found for {week_ended}")

    entries = session.execute(
        select(WatchlistEntry)
        .where(WatchlistEntry.newsletter_id == newsletter.id)
        .order_by(WatchlistEntry.page_number, WatchlistEntry.id)
    ).scalars().all()
    reference = session.execute(
        select(WatchlistReferenceRecord).where(WatchlistReferenceRecord.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    brief = session.execute(
        select(IssueBrief).where(IssueBrief.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    delta = session.execute(
        select(IssueDelta).where(IssueDelta.newsletter_id == newsletter.id)
    ).scalar_one_or_none()
    return newsletter, entries, reference, brief, delta


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
def resolve_open_position_exit_schedule(
    positions: list[dict[str, Any]],
    as_of: str | None = None,
) -> dict[str, Any]:
    """Resolve newsletter-derived exit dates and urgency buckets for open spread positions."""
    as_of_date = _parse_issue_date(as_of) if as_of else _utcnow().date()
    return _resolve_open_position_exit_schedules(positions, as_of=as_of_date)


@mcp.tool()
def get_daily_exit_schedule(
    schwab_futures_positions: dict[str, Any],
    as_of: str | None = None,
) -> dict[str, Any]:
    """Resolve newsletter-derived exit dates directly from schwab-smartspreads-file get_futures_positions output."""
    as_of_date = _parse_issue_date(as_of) if as_of else _utcnow().date()
    return _build_daily_exit_schedule_from_schwab_positions(
        schwab_futures_positions,
        as_of=as_of_date,
    )


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
def publish_issue(
    week_ended: str,
    output_dir: str | None = None,
    publication_version: str | None = None,
    published_by: str | None = None,
) -> dict[str, Any]:
    """Publish one issue into file-based Phase 1 artifacts under the published folder."""
    base_dir = Path(output_dir) if output_dir is not None else Path.cwd() / "published"
    if not base_dir.is_absolute():
        base_dir = Path.cwd() / base_dir
    base_dir.mkdir(parents=True, exist_ok=True)

    with database.session() as session:
        newsletter, entries, reference, brief, delta = _get_issue_bundle(session, week_ended)
        if not entries:
            raise ValueError(f"No watchlist entries found for {week_ended}")

        existing_publication_count = session.execute(
            select(PublicationRun).where(PublicationRun.newsletter_id == newsletter.id)
        ).scalars().all()
        resolved_version = publication_version or f"published-{len(existing_publication_count) + 1}"

        publication_run = PublicationRun(
            newsletter_id=newsletter.id,
            publication_version=resolved_version,
            status="published",
            published_by=published_by,
            published_at=_utcnow(),
            output_root=str(base_dir),
            manifest_json={},
            notes=None,
        )
        session.add(publication_run)
        session.flush()

        watchlist_payload = {
            "schema_version": PUBLICATION_SCHEMA_VERSION,
            "publication_version": resolved_version,
            "published_at": publication_run.published_at.isoformat() if publication_run.published_at else _utcnow().isoformat(),
            "week_ended": newsletter.week_ended.isoformat(),
            "newsletter_id": newsletter.id,
            "title": newsletter.title,
            "principle_context": _build_principle_context(entries),
            "source_file": newsletter.source_file,
            "watchlist": [
                _build_watchlist_publication_entry(newsletter, entry)
                for entry in entries
            ],
        }
        weekly_intelligence = _build_weekly_intelligence_payload(newsletter, entries, brief, delta, reference)
        issue_brief_markdown = _build_issue_brief_markdown(newsletter, brief, delta, reference, entries)

        watchlist_yaml_path = _write_text_file(str(base_dir / "watchlist.yaml"), _serialize_publication_yaml(watchlist_payload))
        intelligence_path = _write_text_file(
            str(base_dir / "weekly_intelligence.json"),
            json.dumps(weekly_intelligence, indent=2),
        )
        issue_brief_path = _write_text_file(str(base_dir / "issue_brief.md"), issue_brief_markdown)

        manifest_files = {
            "watchlist_yaml": watchlist_yaml_path,
            "weekly_intelligence_json": intelligence_path,
            "issue_brief_md": issue_brief_path,
        }
        manifest = _build_publication_manifest(
            newsletter=newsletter,
            publication_version=resolved_version,
            publication_run_id=publication_run.id,
            output_root=base_dir,
            files=manifest_files,
            watchlist_payload=watchlist_payload,
        )
        manifest_path = str(base_dir / "publication_manifest.json")
        manifest_files["publication_manifest_json"] = manifest_path
        manifest["files"]["publication_manifest_json"] = manifest_path
        _write_text_file(
            manifest_path,
            json.dumps(manifest, indent=2),
        )
        publication_run.manifest_json = manifest

        artifact_specs = [
            ("watchlist_yaml", watchlist_yaml_path, _serialize_publication_yaml(watchlist_payload), len(watchlist_payload["watchlist"])),
            ("weekly_intelligence_json", intelligence_path, json.dumps(weekly_intelligence, indent=2), len(entries)),
            ("issue_brief_md", issue_brief_path, issue_brief_markdown, None),
            ("publication_manifest_json", manifest_path, json.dumps(manifest, indent=2), None),
        ]
        for artifact_type, file_path, content, row_count in artifact_specs:
            session.add(
                PublicationArtifact(
                    publication_run_id=publication_run.id,
                    artifact_type=artifact_type,
                    file_path=file_path,
                    file_hash=_sha256_text(content),
                    row_count=row_count,
                    metadata_json={},
                )
            )

        for entry in entries:
            legs = _parse_spread_legs(entry.spread_code)
            policy_tradeable, policy_blocked_reason = _derive_entry_tradeability(entry, legs)
            principle_evaluation = (entry.metadata_json or {}).get("principle_evaluation", {})
            principle_tradeable = principle_evaluation.get("tradeable")
            entry.tradeable = (
                policy_tradeable if principle_tradeable is None else policy_tradeable and bool(principle_tradeable)
            )
            entry.blocked_reason = _combine_blocked_reasons(
                policy_blocked_reason,
                principle_evaluation.get("blocked_reason") if principle_tradeable is False else None,
                principle_evaluation.get("blocked_guidance") if principle_tradeable is False else None,
            )
            entry.publication_state = "published"

        newsletter.issue_status = "published"
        newsletter.published_at = publication_run.published_at

        return {
            "week_ended": newsletter.week_ended.isoformat(),
            "publication_version": resolved_version,
            "publication_run_id": publication_run.id,
            "output_dir": str(base_dir),
            "files": manifest_files,
            "watchlist_count": len(watchlist_payload["watchlist"]),
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
