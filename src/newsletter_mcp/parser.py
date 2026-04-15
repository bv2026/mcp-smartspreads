from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

from .models import ParsedNewsletter, SectionSummary, WatchlistReference, WatchlistRow


WATCHLIST_ROW_RE = re.compile(
    r"^(?P<commodity_name>.+?)\s+"
    r"(?P<spread_code>[A-Z0-9,*+\-]+)\s+"
    r"(?P<side>BUY|SELL)\s+"
    r"(?P<legs>\d+)\s+"
    r"(?P<category>[A-Za-z]+)\s+"
    r"(?P<enter_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<exit_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<win_pct>\d+)%\s+"
    r"(?P<avg_profit>\(?[\d,]+\)?)\s+"
    r"(?P<avg_best_profit>\(?[\d,]+\)?)\s+"
    r"(?P<avg_worst_loss>\(?[\d,]+\)?)\s+"
    r"(?P<avg_draw_down>\(?[\d,]+\)?)\s+"
    r"(?P<apw_pct>\d+)%\s+"
    r"(?P<ridx>\d+(?:\.\d+)?)\s+"
    r"(?P<five_year_corr>\d+)\s+"
    r"(?P<trade_quality>Tier\s+\d+)\s+"
    r"(?P<volatility_structure>Low|Mid|High)$"
)

LEGACY_WATCHLIST_ROW_RE = re.compile(
    r"^(?P<commodity_name>.+?)\s+"
    r"(?P<spread_code>[A-Z0-9,*+\-]+)\s+"
    r"(?P<side>BUY|SELL)\s+"
    r"(?P<legs>\d+)\s+"
    r"(?P<category>[A-Za-z]+)\s+"
    r"(?P<enter_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<exit_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<win_pct>\d+)%\s+"
    r"(?P<avg_profit>\(?[\d,]+\)?)\s+"
    r"(?P<avg_best_profit>\(?[\d,]+\)?)\s+"
    r"(?P<avg_worst_loss>\(?[\d,]+\)?)\s+"
    r"(?P<avg_draw_down>\(?[\d,]+\)?)\s+"
    r"(?P<portfolio>Calendar|Inter)\s+"
    r"(?P<risk_level>\d+)$"
)

LEGACY_OVERVIEW_ROW_RE = re.compile(
    r"^(?P<commodity_name>.+?)\s+"
    r"(?P<spread_code>[A-Z0-9,*+\-]+)\s+"
    r"(?P<side>BUY|SELL)\s+"
    r"(?P<legs>\d+)\s+"
    r"(?P<category>[A-Za-z]+)\s+"
    r"(?P<enter_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<exit_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<win_pct>\d+)%\s+"
    r"(?P<portfolio>Calendar|Inter)\s+"
    r"(?P<risk_level>\d+)$"
)

TRANSITIONAL_WATCHLIST_ROW_RE = re.compile(
    r"^(?P<commodity_name>.+?)\s+"
    r"(?P<spread_code>[A-Z0-9,*+\-]+)\s+"
    r"(?P<side>BUY|SELL)\s+"
    r"(?P<legs>\d+)\s+"
    r"(?P<category>[A-Za-z|]+)\s+"
    r"(?P<enter_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<exit_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<win_pct>\d+)%\s+"
    r"(?P<avg_profit>\(?[\d,]+\)?)\s+"
    r"(?P<avg_best_profit>\(?[\d,]+\)?)\s+"
    r"(?P<avg_worst_loss>\(?[\d,]+\)?)\s+"
    r"(?P<avg_draw_down>\(?[\d,]+\)?)\s+"
    r"(?P<apw_pct>\d+)%\s+"
    r"(?P<ridx>\d+(?:\.\d+)?)\s+"
    r"(?P<five_year_corr>\d+)\s+"
    r"(?P<portfolio>Calendar|Inter)\s+"
    r"(?P<volatility_structure>Low|Mid|High)$"
)

MID_WATCHLIST_ROW_RE = re.compile(
    r"^(?P<commodity_name>.+?)\s+"
    r"(?P<spread_code>[A-Z0-9,*+\-]+)\s+"
    r"(?P<side>BUY|SELL)\s+"
    r"(?P<legs>\d+)\s+"
    r"(?P<category>[A-Za-z|]+)\s+"
    r"(?P<enter_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<exit_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<win_pct>\d+)%\s+"
    r"(?P<avg_profit>\(?[\d,]+\)?)\s+"
    r"(?P<avg_best_profit>\(?[\d,]+\)?)\s+"
    r"(?P<avg_worst_loss>\(?[\d,]+\)?)\s+"
    r"(?P<avg_draw_down>\(?[\d,]+\)?)\s+"
    r"(?P<ridx>\d+(?:\.\d+)?)\s+"
    r"(?P<five_year_corr>\d+)\s+"
    r"(?P<portfolio>Calendar|Inter)\s+"
    r"(?P<risk_level>\d+)$"
)

WEEK_ENDED_RE = re.compile(r"Week Ended ([A-Za-z]+ \d{1,2}, \d{4})")


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\x00", "")).strip()


def _parse_date(value: str):
    return datetime.strptime(value, "%m/%d/%Y").date()


def _parse_money(value: str) -> int:
    value = value.replace(",", "")
    if value.startswith("(") and value.endswith(")"):
        return -int(value[1:-1])
    return int(value)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_pages(path: Path) -> list[str]:
    reader = PdfReader(str(path))
    return [_clean_text(page.extract_text() or "") for page in reader.pages]


def _slice_summary(text: str, max_sentences: int = 4) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join(sentence.strip() for sentence in sentences if sentence.strip()[:1].isalnum())
    if not summary:
        return ""
    condensed = re.sub(r"\s+", " ", summary).strip()
    return " ".join(condensed.split()[: max_sentences * 24])


def _append_rule(target: list[str], line: str) -> None:
    target.append(line.strip())


def _normalize_rule_text(rule: str) -> str:
    rule = re.sub(r"\s+Port-\s*folio Risk Level$", "", rule).strip()
    rule = re.sub(r"\s+Portfolio Risk Level$", "", rule).strip()
    return rule


def _extend_previous_rule(target: list[str], line: str) -> bool:
    if not target:
        return False

    stripped = line.strip()
    if not stripped:
        return False

    if re.fullmatch(r"(?:\d+\s+)+\d+", stripped):
        return False

    if stripped in {
        "Watch List",
        "Overview",
        "Watch List Addition",
        "Column # Explanation",
        "Worst and DD Example",
    }:
        return False

    if "Risk Level" in stripped and ("Port-" in stripped or "Portfolio" in stripped):
        return False

    if stripped.startswith("Commodity Name Side Legs Category Enter Exit"):
        return False

    if re.search(r"\d{1,2}/\d{1,2}/\d{4}", stripped) and (" BUY " in f" {stripped} " or " SELL " in f" {stripped} "):
        return False

    target[-1] = f"{target[-1]} {stripped}".strip()
    return True


def _extract_section_summaries(pages: list[str]) -> list[SectionSummary]:
    sections: list[SectionSummary] = []
    for index, text in enumerate(pages, start=1):
        if not text:
            continue

        first_lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = first_lines[3] if len(first_lines) > 3 else f"Page {index}"

        if "Watch List" in text and index <= 10:
            title = "Watch List"
        elif "Trade Calendar" in text:
            title = "Trade Calendar"
        elif "Margin Summary" in text:
            title = "Margin Summary"
        elif "Macroeconomic" in text:
            title = "Macroeconomic Drivers"

        sections.append(
            SectionSummary(
                name=title[:120],
                page_start=index,
                page_end=index,
                raw_text=text,
                summary_text=_slice_summary(text),
            )
        )
    return sections


def _extract_watchlist_reference(pages: list[str]) -> WatchlistReference | None:
    for page_number, page in enumerate(pages, start=1):
        if "Watch List Overview" not in page and "Watch List\nOverview" not in page:
            continue

        column_definitions: list[dict[str, str]] = []
        trading_rules: list[str] = []
        classification_rules: list[str] = []
        lines = [_clean_text(segment) for segment in page.splitlines() if _clean_text(segment)]
        in_columns = False
        current_column: dict[str, str] | None = None

        for line in lines:
            if not line:
                continue

            if line == "Column # Explanation":
                in_columns = True
                current_column = None
                continue

            if in_columns and (
                line in {"Spreads with 2 Legs:", "Worst and DD Example"}
                or line.startswith(("Tier ", "High", "Mid", "Low"))
                or re.fullmatch(r"(?:\d+\s+)+\d+", line) is not None
            ):
                if current_column is not None:
                    column_definitions.append(current_column)
                    current_column = None
                in_columns = False
            
            if not in_columns and line.startswith(("Tier ", "High", "Mid", "Low")):
                _append_rule(classification_rules, line)
                continue

            if in_columns:
                column_match = re.match(r"^(?P<number>[1-9]|1[0-7]) (?P<description>.+)$", line)
                if column_match:
                    if current_column is not None:
                        column_definitions.append(current_column)
                    current_column = {
                        "column_number": column_match.group("number"),
                        "description": column_match.group("description"),
                    }
                    continue

                if current_column is not None and not re.fullmatch(r"(?:\d+\s+)+\d+", line):
                    current_column["description"] = f"{current_column['description']} {line}".strip()
                continue

            if (
                line in {"Spreads with 2 Legs:", "Spreads with 3 Legs:"}
                or line.startswith("BUY")
                or line.startswith("SELL")
                or "Saturdays are rolled back to Friday" in line
                or "Sundays are rolled forward to Monday" in line
                or "Calendar indicates" in line
                or "Inter indicates" in line
                or "Watch List data is hypothetical" in line
            ):
                _append_rule(trading_rules, line)
                continue

            if (
                "The only exception is weekends and holidays" in line
                and trading_rules
                and trading_rules[-1].startswith("Watch List data is hypothetical")
            ):
                _extend_previous_rule(trading_rules, line)
                continue

            if line.startswith("17 Volatility Structure"):
                _append_rule(classification_rules, line)
                continue

            if line.startswith(("Tier ", "High", "Mid", "Low")):
                _append_rule(classification_rules, line)
                continue

            if (
                line.startswith("Front and Deferred Contracts.")
                and classification_rules
                and classification_rules[-1].startswith("17 Volatility Structure")
            ):
                _extend_previous_rule(classification_rules, line)
                continue

            if _extend_previous_rule(trading_rules, line):
                continue

            _extend_previous_rule(classification_rules, line)

        if current_column is not None:
            column_definitions.append(current_column)

        trading_rules = [_normalize_rule_text(rule) for rule in trading_rules if _normalize_rule_text(rule)]
        classification_rules = [
            _normalize_rule_text(rule)
            for rule in classification_rules
            if _normalize_rule_text(rule)
        ]

        summary_parts = [
            f"Column definitions captured: {len(column_definitions)}",
            f"Trading rules captured: {len(trading_rules)}",
            f"Classification rules captured: {len(classification_rules)}",
        ]

        return WatchlistReference(
            page_number=page_number,
            raw_text=page,
            summary_text=". ".join(summary_parts),
            column_definitions=column_definitions,
            trading_rules=trading_rules,
            classification_rules=classification_rules,
        )

    return None


def _extract_watchlist_rows(pages: list[str]) -> list[WatchlistRow]:
    rows: list[WatchlistRow] = []
    current_section = "overview"

    for page_number, page in enumerate(pages, start=1):
        page_has_both_sections = (
            ("Watch List\nIntra-Commodity" in page or "Watch List Intra-Commodity" in page)
            and "Inter-Commodity" in page
        )
        page_row_count = 0

        if "Watch List\nIntra-Commodity" in page or "Watch List Intra-Commodity" in page:
            current_section = "intra_commodity"
        elif "Inter-Commodity" in page:
            current_section = "inter_commodity"
        elif "Watch List Overview" in page or "Watch List\nOverview" in page:
            current_section = "overview"

        for line in (segment.strip() for segment in page.splitlines()):
            if not line or "Watch List" == line:
                continue

            if "Commodity Name" in line:
                if page_has_both_sections and page_row_count > 0:
                    current_section = "inter_commodity"
                continue

            cleaned_line = _clean_text(line)
            if current_section == "overview":
                continue

            match = WATCHLIST_ROW_RE.match(cleaned_line)
            if match:
                data = match.groupdict()
                row_section = current_section
                if page_has_both_sections:
                    row_section = (
                        "inter_commodity"
                        if "," in data["commodity_name"]
                        else "intra_commodity"
                    )
                rows.append(
                    WatchlistRow(
                        commodity_name=data["commodity_name"],
                        spread_code=data["spread_code"],
                        side=data["side"],
                        legs=int(data["legs"]),
                        category=data["category"],
                        enter_date=_parse_date(data["enter_date"]),
                        exit_date=_parse_date(data["exit_date"]),
                        win_pct=float(data["win_pct"]),
                        avg_profit=_parse_money(data["avg_profit"]),
                        avg_best_profit=_parse_money(data["avg_best_profit"]),
                        avg_worst_loss=_parse_money(data["avg_worst_loss"]),
                        avg_draw_down=_parse_money(data["avg_draw_down"]),
                        apw_pct=float(data["apw_pct"]),
                        ridx=float(data["ridx"]),
                        five_year_corr=int(data["five_year_corr"]),
                        portfolio=None,
                        risk_level=None,
                        trade_quality=data["trade_quality"],
                        volatility_structure=data["volatility_structure"],
                        section_name=row_section,
                        page_number=page_number,
                        raw_row=cleaned_line,
                    )
                )
                page_row_count += 1
                continue

            match = LEGACY_WATCHLIST_ROW_RE.match(cleaned_line)
            if match:
                data = match.groupdict()
                row_section = current_section
                if page_has_both_sections:
                    row_section = (
                        "inter_commodity"
                        if "," in data["commodity_name"]
                        else "intra_commodity"
                    )
                rows.append(
                    WatchlistRow(
                        commodity_name=data["commodity_name"],
                        spread_code=data["spread_code"],
                        side=data["side"],
                        legs=int(data["legs"]),
                        category=data["category"],
                        enter_date=_parse_date(data["enter_date"]),
                        exit_date=_parse_date(data["exit_date"]),
                        win_pct=float(data["win_pct"]),
                        avg_profit=_parse_money(data["avg_profit"]),
                        avg_best_profit=_parse_money(data["avg_best_profit"]),
                        avg_worst_loss=_parse_money(data["avg_worst_loss"]),
                        avg_draw_down=_parse_money(data["avg_draw_down"]),
                        apw_pct=0.0,
                        ridx=0.0,
                        five_year_corr=0,
                        portfolio=data["portfolio"],
                        risk_level=int(data["risk_level"]),
                        trade_quality=None,
                        volatility_structure=None,
                        section_name=row_section,
                        page_number=page_number,
                        raw_row=cleaned_line,
                    )
                )
                page_row_count += 1
                continue

            match = TRANSITIONAL_WATCHLIST_ROW_RE.match(cleaned_line)
            if match:
                data = match.groupdict()
                row_section = current_section
                if page_has_both_sections:
                    row_section = (
                        "inter_commodity"
                        if "," in data["commodity_name"]
                        else "intra_commodity"
                    )
                rows.append(
                    WatchlistRow(
                        commodity_name=data["commodity_name"],
                        spread_code=data["spread_code"],
                        side=data["side"],
                        legs=int(data["legs"]),
                        category=data["category"],
                        enter_date=_parse_date(data["enter_date"]),
                        exit_date=_parse_date(data["exit_date"]),
                        win_pct=float(data["win_pct"]),
                        avg_profit=_parse_money(data["avg_profit"]),
                        avg_best_profit=_parse_money(data["avg_best_profit"]),
                        avg_worst_loss=_parse_money(data["avg_worst_loss"]),
                        avg_draw_down=_parse_money(data["avg_draw_down"]),
                        apw_pct=float(data["apw_pct"]),
                        ridx=float(data["ridx"]),
                        five_year_corr=int(data["five_year_corr"]),
                        portfolio=data["portfolio"],
                        risk_level=None,
                        trade_quality=None,
                        volatility_structure=data["volatility_structure"],
                        section_name=row_section,
                        page_number=page_number,
                        raw_row=cleaned_line,
                    )
                )
                page_row_count += 1
                continue

            match = MID_WATCHLIST_ROW_RE.match(cleaned_line)
            if match:
                data = match.groupdict()
                row_section = current_section
                if page_has_both_sections:
                    row_section = (
                        "inter_commodity"
                        if "," in data["commodity_name"]
                        else "intra_commodity"
                    )
                rows.append(
                    WatchlistRow(
                        commodity_name=data["commodity_name"],
                        spread_code=data["spread_code"],
                        side=data["side"],
                        legs=int(data["legs"]),
                        category=data["category"],
                        enter_date=_parse_date(data["enter_date"]),
                        exit_date=_parse_date(data["exit_date"]),
                        win_pct=float(data["win_pct"]),
                        avg_profit=_parse_money(data["avg_profit"]),
                        avg_best_profit=_parse_money(data["avg_best_profit"]),
                        avg_worst_loss=_parse_money(data["avg_worst_loss"]),
                        avg_draw_down=_parse_money(data["avg_draw_down"]),
                        apw_pct=0.0,
                        ridx=float(data["ridx"]),
                        five_year_corr=int(data["five_year_corr"]),
                        portfolio=data["portfolio"],
                        risk_level=int(data["risk_level"]),
                        trade_quality=None,
                        volatility_structure=None,
                        section_name=row_section,
                        page_number=page_number,
                        raw_row=cleaned_line,
                    )
                )
                page_row_count += 1
                continue

            match = LEGACY_OVERVIEW_ROW_RE.match(cleaned_line)
            if match:
                # Overview/example rows explain the columns and should not be treated
                # as live watchlist entries for the current newsletter issue.
                continue
    return rows


def parse_newsletter(path: Path) -> ParsedNewsletter:
    pages = _extract_pages(path)
    raw_text = "\n\n".join(pages)
    first_page = pages[0] if pages else ""
    week_match = WEEK_ENDED_RE.search(first_page)
    if not week_match:
        raise ValueError(f"Could not determine issue date from {path.name}")

    week_ended = datetime.strptime(week_match.group(1), "%B %d, %Y").date()
    title = f"Smart Spreads newsletter for week ended {week_ended.isoformat()}"
    watchlist_rows = _extract_watchlist_rows(pages)
    section_summaries = _extract_section_summaries(pages)
    watchlist_reference = _extract_watchlist_reference(pages)

    overview_parts = [
        f"Issue date: {week_ended.isoformat()}",
        f"Pages: {len(pages)}",
        f"Watchlist rows imported: {len(watchlist_rows)}",
    ]
    if watchlist_rows:
        tier_counts: dict[str, int] = {}
        for row in watchlist_rows:
            label = row.trade_quality or row.portfolio or "unclassified"
            tier_counts[label] = tier_counts.get(label, 0) + 1
        tier_summary = ", ".join(f"{tier}: {count}" for tier, count in sorted(tier_counts.items()))
        overview_parts.append(f"Watchlist mix: {tier_summary}")

    narrative_pages = [
        section.summary_text
        for section in section_summaries
        if section.name in {"Watch List", "Macroeconomic Drivers", "Margin Summary"}
    ]
    if watchlist_reference is not None:
        overview_parts.append(watchlist_reference.summary_text)
    overall_summary = ". ".join(part for part in overview_parts + narrative_pages[:3] if part).strip()

    metadata = {
        "page_count": len(pages),
        "source_filename": path.name,
    }

    return ParsedNewsletter(
        source_file=path,
        file_hash=_hash_file(path),
        title=title,
        week_ended=week_ended,
        raw_text=raw_text,
        metadata=metadata,
        overall_summary=overall_summary,
        section_summaries=section_summaries,
        watchlist_reference=watchlist_reference,
        watchlist_rows=watchlist_rows,
    )
