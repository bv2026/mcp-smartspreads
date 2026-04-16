from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class WatchlistSummaryDraft:
    entry_count: int
    section_counts: dict[str, int]
    classification_counts: dict[str, int]
    category_counts: dict[str, int]
    volatility_counts: dict[str, int]
    tradeable_count: int
    blocked_count: int
    dominant_category: dict[str, Any] | None
    dominant_classification: dict[str, Any] | None
    dominant_volatility: dict[str, Any] | None
    top_categories: list[dict[str, Any]]
    top_classifications: list[dict[str, Any]]
    blocked_examples: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_count": self.entry_count,
            "section_counts": self.section_counts,
            "classification_counts": self.classification_counts,
            "category_counts": self.category_counts,
            "volatility_counts": self.volatility_counts,
            "tradeable_count": self.tradeable_count,
            "blocked_count": self.blocked_count,
            "dominant_category": self.dominant_category,
            "dominant_classification": self.dominant_classification,
            "dominant_volatility": self.dominant_volatility,
            "top_categories": self.top_categories,
            "top_classifications": self.top_classifications,
            "blocked_examples": self.blocked_examples,
        }


@dataclass(frozen=True, slots=True)
class IssueBriefDraft:
    headline: str
    executive_summary: str
    key_themes: list[str]
    notable_risks: list[str]
    notable_opportunities: list[str]
    watchlist_summary: dict[str, Any]
    change_summary: dict[str, Any]


class IssueBriefService:
    """Build business-layer issue briefs from normalized newsletter records."""

    @staticmethod
    def summarize_watchlist_rows(rows: list[Any]) -> dict[str, Any]:
        return IssueBriefService.build_watchlist_summary(rows).as_dict()

    @staticmethod
    def build_watchlist_summary(rows: list[Any]) -> WatchlistSummaryDraft:
        section_counts = Counter(row.section_name for row in rows)
        classification_counts = Counter(
            row.trade_quality or row.portfolio or "unclassified" for row in rows
        )
        category_counts = Counter(row.category for row in rows)
        volatility_counts = Counter(
            getattr(row, "volatility_structure", None) or "unclassified" for row in rows
        )
        tradeable_count = sum(
            1
            for row in rows
            if getattr(row, "tradeable", None) is not False
        )
        blocked_count = sum(
            1
            for row in rows
            if getattr(row, "tradeable", None) is False
        )
        blocked_examples = [
            {
                "commodity_name": row.commodity_name,
                "spread_code": row.spread_code,
                "blocked_reason": getattr(row, "blocked_reason", None),
            }
            for row in rows
            if getattr(row, "tradeable", None) is False
        ][:3]

        def _dominant(counter: Counter) -> dict[str, Any] | None:
            if not counter:
                return None
            label, count = counter.most_common(1)[0]
            return {"label": label, "count": count}

        def _rank(counter: Counter, *, top_n: int = 3) -> list[dict[str, Any]]:
            return [
                {"label": label, "count": count}
                for label, count in counter.most_common(top_n)
            ]

        return WatchlistSummaryDraft(
            entry_count=len(rows),
            section_counts=dict(section_counts),
            classification_counts=dict(classification_counts),
            category_counts=dict(category_counts),
            volatility_counts=dict(volatility_counts),
            tradeable_count=tradeable_count,
            blocked_count=blocked_count,
            dominant_category=_dominant(category_counts),
            dominant_classification=_dominant(classification_counts),
            dominant_volatility=_dominant(volatility_counts),
            top_categories=_rank(category_counts),
            top_classifications=_rank(classification_counts),
            blocked_examples=blocked_examples,
        )

    @staticmethod
    def build_issue_brief(
        *,
        title: str,
        executive_summary: str,
        entries: list[Any],
        delta: Any | None = None,
        reference: Any | None = None,
    ) -> IssueBriefDraft:
        watchlist_summary = IssueBriefService.build_watchlist_summary(entries).as_dict()
        change_summary = IssueBriefService._build_change_summary(delta)
        return IssueBriefDraft(
            headline=title,
            executive_summary=executive_summary,
            key_themes=IssueBriefService._build_key_themes(entries, watchlist_summary),
            notable_risks=IssueBriefService._build_notable_risks(entries, reference),
            notable_opportunities=IssueBriefService._build_notable_opportunities(entries),
            watchlist_summary=watchlist_summary,
            change_summary=change_summary,
        )

    @staticmethod
    def build_issue_brief_markdown(
        *,
        week_ended: str,
        title: str,
        executive_summary: str,
        entries: list[Any],
        brief_data: IssueBriefDraft,
        delta_summary_text: str | None,
        reference: Any | None,
    ) -> str:
        lines = [
            f"# SmartSpreads Issue Brief - {week_ended}",
            "",
            f"- Title: {title}",
            f"- Week Ended: {week_ended}",
            f"- Entry Count: {len(entries)}",
            "",
            "## Executive Summary",
            "",
            executive_summary,
            "",
            "## Watchlist Summary",
            "",
            f"- Total entries: {brief_data.watchlist_summary.get('entry_count', len(entries))}",
            f"- Section counts: {json.dumps(brief_data.watchlist_summary.get('section_counts', {}), sort_keys=True)}",
            f"- Classification counts: {json.dumps(brief_data.watchlist_summary.get('classification_counts', {}), sort_keys=True)}",
            f"- Category counts: {json.dumps(brief_data.watchlist_summary.get('category_counts', {}), sort_keys=True)}",
            "",
            "## Key Themes",
            "",
        ]
        lines.extend(f"- {theme}" for theme in brief_data.key_themes)
        lines.extend(
            [
                "",
                "## Notable Opportunities",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in brief_data.notable_opportunities)
        lines.extend(
            [
                "",
                "## Notable Risks",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in brief_data.notable_risks)
        lines.extend(
            [
                "",
                "## Changes Vs Prior Issue",
                "",
                delta_summary_text or "No prior issue available for comparison.",
                "",
            ]
        )

        if reference is not None:
            lines.extend(
                [
                    "## Reference Rules",
                    "",
                    *(f"- {rule}" for rule in reference.trading_rules_json[:5]),
                    *(f"- {rule}" for rule in reference.classification_rules_json[:5]),
                    "",
                ]
            )

        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _build_change_summary(delta: Any | None) -> dict[str, Any]:
        if delta is None:
            return {
                "added_count": 0,
                "removed_count": 0,
                "changed_count": 0,
                "summary_text": "No prior issue available for comparison.",
            }
        return {
            "added_count": len(delta.added_entries_json),
            "removed_count": len(delta.removed_entries_json),
            "changed_count": len(delta.changed_entries_json),
            "summary_text": delta.summary_text,
        }

    @staticmethod
    def _build_key_themes(entries: list[Any], watchlist_summary: dict[str, Any]) -> list[str]:
        themes: list[str] = []
        dominant_category = watchlist_summary.get("dominant_category")
        if dominant_category:
            themes.append(
                f"{dominant_category['label']} is the lead market concentration with {dominant_category['count']} setups."
            )
        section_counts = watchlist_summary.get("section_counts", {})
        if section_counts:
            themes.append(
                f"Intra/inter mix: {json.dumps(section_counts, sort_keys=True)}."
            )
        dominant_classification = watchlist_summary.get("dominant_classification")
        if dominant_classification:
            themes.append(
                f"{dominant_classification['label']} is the dominant scoring bucket with {dominant_classification['count']} entries."
            )
        dominant_volatility = watchlist_summary.get("dominant_volatility")
        if dominant_volatility:
            themes.append(
                f"{dominant_volatility['label']} volatility structures lead the book with {dominant_volatility['count']} setups."
            )
        return themes[:5]

    @staticmethod
    def _build_notable_risks(entries: list[Any], reference: Any | None) -> list[str]:
        risks: list[str] = []
        blocked = [row for row in entries if getattr(row, "tradeable", None) is False]
        if blocked:
            sample = blocked[0]
            reason = getattr(sample, "blocked_reason", None) or "Policy or platform restrictions apply."
            risks.append(f"{len(blocked)} setups are currently blocked. Example: {sample.commodity_name} - {reason}")
        low_ridx = [row for row in entries if getattr(row, "ridx", 0) < 30]
        if low_ridx:
            risks.append(f"{len(low_ridx)} setups are below the RIDX threshold of 30.")
        if reference is not None and reference.trading_rules_json:
            risks.append(f"Interpret trades using the issue rules, starting with: {reference.trading_rules_json[0]}")
        return risks[:5] or ["No major structural risks were flagged in the current issue brief draft."]

    @staticmethod
    def _build_notable_opportunities(entries: list[Any]) -> list[str]:
        ranked = sorted(
            entries,
            key=lambda row: (
                0 if (row.trade_quality or "") == "Tier 1" else 1,
                -(getattr(row, "win_pct", 0) or 0),
                -(getattr(row, "avg_profit", 0) or 0),
            ),
        )
        opportunities: list[str] = []
        for row in ranked:
            if getattr(row, "tradeable", None) is False:
                continue
            if row.trade_quality:
                score = row.trade_quality
            elif row.portfolio:
                score = row.portfolio
            elif row.risk_level is not None:
                score = f"Risk {row.risk_level}"
            else:
                score = "unclassified"
            opportunities.append(
                f"{row.commodity_name} ({row.spread_code}) is a {score} setup with {row.win_pct:.0f}% win rate and average profit {row.avg_profit}."
            )
            if len(opportunities) == 3:
                break
        return opportunities or ["No clearly tradeable standout setup was identified in the current issue draft."]
