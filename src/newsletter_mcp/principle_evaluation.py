from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Any


EVALUATION_VERSION = "phase3-v1"
CONTRACT_TOKEN_RE = re.compile(r"([A-Z]+)([FGHJKMNQUVXZ])(\d{2})")


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class HistoricalContext:
    prior_occurrence_counts: dict[str, int]
    same_commodity_counts: dict[str, int]
    prior_commodity_counts: dict[str, int]
    prior_structure_signature_counts: dict[tuple[str, str, str], int]
    prior_entry_count: int

    @staticmethod
    def build(*, current_entries: list[Any], prior_entries: list[Any]) -> "HistoricalContext":
        prior_counts = Counter(_occurrence_key(entry) for entry in prior_entries)
        commodity_counts = Counter(_normalize_text(entry.commodity_name) for entry in current_entries)
        prior_commodity_counts = Counter(_normalize_text(entry.commodity_name) for entry in prior_entries)
        prior_structure_signatures = Counter(
            (
                _normalize_text(entry.commodity_name),
                _structure_signature(entry),
                _normalize_text(getattr(entry, "section_name", "")),
            )
            for entry in prior_entries
        )
        return HistoricalContext(
            prior_occurrence_counts=dict(prior_counts),
            same_commodity_counts=dict(commodity_counts),
            prior_commodity_counts=dict(prior_commodity_counts),
            prior_structure_signature_counts=dict(prior_structure_signatures),
            prior_entry_count=len(prior_entries),
        )

    def occurrence_count(self, entry: Any) -> int:
        return self.prior_occurrence_counts.get(_occurrence_key(entry), 0)

    def same_commodity_count(self, entry: Any) -> int:
        return self.same_commodity_counts.get(_normalize_text(entry.commodity_name), 0)

    def prior_commodity_count(self, entry: Any) -> int:
        return self.prior_commodity_counts.get(_normalize_text(entry.commodity_name), 0)

    def prior_structure_signature_count(self, entry: Any) -> int:
        return self.prior_structure_signature_counts.get(
            (
                _normalize_text(entry.commodity_name),
                _structure_signature(entry),
                _normalize_text(getattr(entry, "section_name", "")),
            ),
            0,
        )


@dataclass(frozen=True, slots=True)
class PrincipleEvaluationOutcome:
    evaluation_version: str
    tradeable: bool
    blocked_reason: str | None
    blocked_guidance: str | None
    decision_summary: str
    scores: dict[str, float | None]
    statuses: dict[str, str]
    violations: list[str]
    deferred_principles: list[str]
    evaluated_at: datetime

    def as_metadata(self) -> dict[str, Any]:
        return {
            "evaluation_version": self.evaluation_version,
            "tradeable": self.tradeable,
            "blocked_reason": self.blocked_reason,
            "blocked_guidance": self.blocked_guidance,
            "decision_summary": self.decision_summary,
            "principle_scores": self.scores,
            "principle_status": self.statuses,
            "violations": self.violations,
            "deferred_principles": self.deferred_principles,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


class PrincipleEvaluationService:
    @staticmethod
    def evaluate_entry(
        *,
        entry: Any,
        principles: list[Any],
        historical_context: HistoricalContext,
    ) -> PrincipleEvaluationOutcome:
        scores: dict[str, float | None] = {}
        statuses: dict[str, str] = {}
        violations: list[str] = []
        deferred: list[str] = []
        first_failed_principle: Any | None = None

        for principle in sorted(principles, key=lambda item: (item.priority or 99, item.principle_key)):
            score, status = _evaluate_principle(entry, principle, historical_context)
            scores[principle.principle_key] = score
            statuses[principle.principle_key] = status
            if status == "fail":
                violations.append(principle.principle_key)
                if first_failed_principle is None and (principle.priority or 99) <= 1:
                    first_failed_principle = principle
            elif status == "deferred":
                deferred.append(principle.principle_key)

        tradeable = first_failed_principle is None
        blocked_reason = first_failed_principle.principle_key if first_failed_principle is not None else None
        blocked_guidance = first_failed_principle.guidance_text if first_failed_principle is not None else None

        if not tradeable:
            decision_summary = (
                f"Blocked by {blocked_reason}. "
                f"{blocked_guidance or 'Review the principle guidance before publication.'}"
            )
        elif deferred:
            decision_summary = (
                "Passes Sunday principle screening with "
                f"{len(deferred)} deferred principle review item(s) for Daily workflow."
            )
        else:
            decision_summary = "Passes Sunday principle screening with no blocking principle failure."

        return PrincipleEvaluationOutcome(
            evaluation_version=EVALUATION_VERSION,
            tradeable=tradeable,
            blocked_reason=blocked_reason,
            blocked_guidance=blocked_guidance,
            decision_summary=decision_summary,
            scores=scores,
            statuses=statuses,
            violations=violations,
            deferred_principles=deferred,
            evaluated_at=utcnow(),
        )


def _evaluate_principle(entry: Any, principle: Any, historical_context: HistoricalContext) -> tuple[float | None, str]:
    key = principle.principle_key
    if key == "portfolio_fit_over_isolated_trade_appeal":
        return None, "deferred"
    if key == "margin_as_survivability_constraint":
        return None, "deferred"
    if key == "intercommodity_conditional_edge" and getattr(entry, "section_name", "") != "inter_commodity":
        return None, "not_applicable"

    score = _score_principle(entry, principle, historical_context)
    threshold = _threshold_for(principle)
    status = "pass" if score >= threshold else "fail"
    return round(score, 4), status


def _score_principle(entry: Any, principle: Any, historical_context: HistoricalContext) -> float:
    key = principle.principle_key
    if key == "structure_before_conviction":
        return _score_structure_before_conviction(entry, historical_context)
    if key == "selectivity_not_participation":
        return _score_selectivity(entry, historical_context)
    if key == "trade_selection_dominates_trade_management":
        return _score_trade_selection(entry)
    if key == "volatility_as_constraint":
        return _score_volatility(entry)
    if key == "intercommodity_conditional_edge":
        return _score_intercommodity(entry)
    return 1.0


def _score_structure_before_conviction(entry: Any, historical_context: HistoricalContext) -> float:
    if historical_context.prior_entry_count < 5:
        return 0.8
    occurrences = historical_context.occurrence_count(entry)
    structure_occurrences = historical_context.prior_structure_signature_count(entry)
    commodity_occurrences = historical_context.prior_commodity_count(entry)
    if occurrences >= 8:
        return 1.0
    if occurrences >= 5:
        return 0.85
    if occurrences >= 3:
        return 0.72
    if occurrences >= 1:
        return 0.68
    if structure_occurrences >= 5 or commodity_occurrences >= 8:
        return 0.84
    if structure_occurrences >= 3 or commodity_occurrences >= 5:
        return 0.78
    if structure_occurrences >= 2 or commodity_occurrences >= 3:
        return 0.72
    if structure_occurrences >= 1 or commodity_occurrences >= 2:
        return 0.62
    return 0.35


def _score_selectivity(entry: Any, historical_context: HistoricalContext) -> float:
    same_commodity = historical_context.same_commodity_count(entry)
    score = 0.95
    if same_commodity >= 4:
        score = min(score, 0.45)
    elif same_commodity == 3:
        score = min(score, 0.7)

    tier = (getattr(entry, "trade_quality", None) or "").strip()
    if tier == "Tier 3":
        score = min(score, 0.68)
    elif tier == "Tier 4":
        score = min(score, 0.4)

    ridx = getattr(entry, "ridx", 0) or 0
    if ridx < 30:
        score = min(score, 0.5)
    return score


def _score_trade_selection(entry: Any) -> float:
    tier = (getattr(entry, "trade_quality", None) or "").strip()
    if tier == "Tier 1":
        score = 0.95
    elif tier == "Tier 2":
        score = 0.82
    elif tier == "Tier 3":
        score = 0.62
    elif tier == "Tier 4":
        score = 0.35
    else:
        score = 0.7

    win_pct = getattr(entry, "win_pct", 0) or 0
    if win_pct >= 90:
        score = min(1.0, score + 0.03)
    elif win_pct < 70:
        score = min(score, 0.6)

    ridx = getattr(entry, "ridx", 0) or 0
    if ridx < 30:
        score = min(score, 0.55)
    return score


def _score_volatility(entry: Any) -> float:
    volatility = _normalize_text(getattr(entry, "volatility_structure", None))
    if volatility in {"low", "compressed"}:
        score = 0.9
    elif volatility in {"mid", "medium", "moderate"}:
        score = 0.82
    elif volatility in {"high", "expanded"}:
        score = 0.72
    elif volatility in {"unclassified", ""}:
        score = 0.62
    else:
        score = 0.7

    ridx = getattr(entry, "ridx", 0) or 0
    if ridx < 30:
        score = min(score, 0.58)
    return score


def _score_intercommodity(entry: Any) -> float:
    tier = (getattr(entry, "trade_quality", None) or "").strip()
    win_pct = getattr(entry, "win_pct", 0) or 0
    if tier == "Tier 1" and win_pct >= 85:
        return 0.78
    if tier == "Tier 2" and win_pct >= 80:
        return 0.7
    if tier == "Tier 4":
        return 0.45
    return 0.58


def _threshold_for(principle: Any) -> float:
    metadata = getattr(principle, "metadata_json", {}) or {}
    if isinstance(metadata.get("threshold"), (int, float)):
        return float(metadata["threshold"])
    priority = getattr(principle, "priority", None)
    if priority == 1:
        return 0.75
    if priority == 2:
        return 0.7
    return 0.65


def _occurrence_key(entry: Any) -> str:
    return f"{_normalize_text(entry.commodity_name)}::{_normalize_text(entry.spread_code)}"


def _structure_signature(entry: Any) -> str:
    roots = [match.group(1) for match in CONTRACT_TOKEN_RE.finditer(str(getattr(entry, "spread_code", "") or ""))]
    return "-".join(roots)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()
