from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.profile_store import now_iso


WEAKNESS_UPDATE_STEP = 0.2


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def merge_unique_text(items: list[str], new_items: list[str], limit: int = 12) -> list[str]:
    seen = set()
    merged: list[str] = []

    for item in [*new_items, *items]:
        text = normalize_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
        if len(merged) == limit:
            break

    return merged


def merge_issue_list(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index: dict[tuple[str, str], dict[str, Any]] = {}

    for item in existing:
        concept = normalize_text(item.get("concept"))
        issue = normalize_text(item.get("gap") or item.get("issue") or item.get("description"))
        if not concept and not issue:
            continue
        normalized = dict(item)
        normalized.setdefault("concept", concept or "未命名知识点")
        normalized.setdefault("evidence_count", 1)
        key = (normalized["concept"], issue)
        index[key] = normalized
        merged.append(normalized)

    for item in incoming:
        concept = normalize_text(item.get("concept")) or "未命名知识点"
        issue = normalize_text(item.get("gap") or item.get("issue") or item.get("description"))
        if not issue:
            continue
        key = (concept, issue)
        severity = int(item.get("severity", 2) or 2)
        evidence = normalize_text(item.get("evidence"))

        if key in index:
            current = index[key]
            current["severity"] = max(int(current.get("severity", 1) or 1), severity)
            current["evidence_count"] = int(current.get("evidence_count", 1) or 1) + 1
            current["last_seen"] = now_iso()
            if evidence:
                current["latest_evidence"] = evidence
            continue

        field = "gap" if "gap" in item else "issue"
        created = {
            "concept": concept,
            field: issue,
            "severity": severity,
            "evidence_count": 1,
            "first_seen": now_iso(),
            "last_seen": now_iso(),
        }
        if evidence:
            created["latest_evidence"] = evidence
        index[key] = created
        merged.insert(0, created)

    return merged[:limit]


def analysis_weak_concepts(analysis: dict[str, Any]) -> set[str]:
    weak_concepts = {normalize_text(item) for item in as_list(analysis.get("weak_concepts")) if normalize_text(item)}
    gaps = as_list(analysis.get("knowledge_gaps"))
    misconceptions = as_list(analysis.get("misconceptions"))
    weak_concepts.update(normalize_text(item.get("concept")) for item in gaps if isinstance(item, dict))
    weak_concepts.update(normalize_text(item.get("concept")) for item in misconceptions if isinstance(item, dict))
    weak_concepts.discard("")
    return weak_concepts


def update_weak_history(profile: dict[str, Any], concepts: set[str]) -> None:
    history = as_list(profile.get("weak_history"))
    index: dict[str, dict[str, Any]] = {}

    for item in history:
        if not isinstance(item, dict):
            continue
        concept = normalize_text(item.get("concept"))
        if not concept:
            continue
        normalized = dict(item)
        normalized.setdefault("first_seen", now_iso())
        normalized.setdefault("last_seen", normalized["first_seen"])
        normalized.setdefault("evidence_count", 1)
        index[concept] = normalized

    for concept in concepts:
        current = index.get(concept)
        if current:
            current["last_seen"] = now_iso()
            current["evidence_count"] = int(current.get("evidence_count", 1) or 1) + 1
            current["status"] = "active"
            continue
        index[concept] = {
            "concept": concept,
            "first_seen": now_iso(),
            "last_seen": now_iso(),
            "evidence_count": 1,
            "status": "active",
        }

    profile["weak_history"] = sorted(index.values(), key=lambda item: item.get("last_seen", ""), reverse=True)[:100]


def cleared_concepts(profile: dict[str, Any]) -> set[str]:
    mastery = profile.get("concept_mastery", {})
    cleared: set[str] = set()
    if not isinstance(mastery, dict):
        return cleared

    for concept, item in mastery.items():
        if not isinstance(item, dict):
            continue
        status = normalize_text(item.get("status")).lower()
        try:
            score = float(item.get("score", 0.0))
        except Exception:
            score = 0.0
        if score <= 0 or status in {"familiar", "mastered"}:
            cleared.add(normalize_text(concept))

    cleared.discard("")
    return cleared


def prune_cleared_items(profile: dict[str, Any]) -> None:
    cleared = cleared_concepts(profile)
    if not cleared:
        return

    mastery = profile.get("concept_mastery", {})
    if isinstance(mastery, dict):
        for concept in list(mastery.keys()):
            if normalize_text(concept) in cleared:
                mastery.pop(concept, None)

    for item in as_list(profile.get("weak_history")):
        if isinstance(item, dict) and normalize_text(item.get("concept")) in cleared:
            item["status"] = "cleared"
            item["cleared_at"] = now_iso()

    def keep_issue(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        return normalize_text(item.get("concept")) not in cleared

    profile["knowledge_gaps"] = [item for item in as_list(profile.get("knowledge_gaps")) if keep_issue(item)]
    profile["misconceptions"] = [item for item in as_list(profile.get("misconceptions")) if keep_issue(item)]
    profile["recommended_review"] = [
        item
        for item in as_list(profile.get("recommended_review"))
        if not any(concept and concept in normalize_text(item) for concept in cleared)
    ]


def update_concept_weakness(profile: dict[str, Any], analysis: dict[str, Any]) -> None:
    mastery = profile.setdefault("concept_mastery", {})
    concepts = {normalize_text(item) for item in as_list(analysis.get("core_concepts")) if normalize_text(item)}
    weak_concepts = analysis_weak_concepts(analysis)

    for concept in concepts | weak_concepts:
        current = mastery.get(concept, {})
        score = float(current.get("score", 0.0))
        if concept in weak_concepts:
            score += WEAKNESS_UPDATE_STEP
        else:
            score -= WEAKNESS_UPDATE_STEP
        score = clamp(score)

        status = "weak" if score >= 0.55 else ("learning" if score > 0 else "familiar")
        mastery[concept] = {
            **current,
            "score": round(score, 2),
            "status": status,
            "evidence_count": int(current.get("evidence_count", 0) or 0) + 1,
            "last_seen": now_iso(),
        }


def update_recent_questions(profile: dict[str, Any], question: str | None = None) -> None:
    question_text = normalize_text(question)
    if not question_text:
        return

    item = {
        "created_at": now_iso(),
        "question": question_text[:240],
    }
    profile["recent_questions"] = [item, *as_list(profile.get("recent_questions"))][:12]


def update_learning_profile(profile: dict[str, Any], analysis: dict[str, Any], question: str | None = None) -> dict[str, Any]:
    next_profile = deepcopy(profile)
    update_recent_questions(next_profile, question)
    update_weak_history(next_profile, analysis_weak_concepts(analysis))
    update_concept_weakness(next_profile, analysis)

    next_profile["knowledge_gaps"] = merge_issue_list(
        as_list(next_profile.get("knowledge_gaps")),
        [item for item in as_list(analysis.get("knowledge_gaps")) if isinstance(item, dict)],
    )
    next_profile["misconceptions"] = merge_issue_list(
        as_list(next_profile.get("misconceptions")),
        [item for item in as_list(analysis.get("misconceptions")) if isinstance(item, dict)],
    )
    next_profile["recommended_review"] = merge_unique_text(
        [normalize_text(item) for item in as_list(next_profile.get("recommended_review"))],
        [normalize_text(item) for item in as_list(analysis.get("recommended_review"))],
    )

    insight = {
        "created_at": now_iso(),
        "topic": normalize_text(analysis.get("topic")) or "未命名主题",
        "summary": normalize_text(analysis.get("summary")),
        "weak_concepts": [normalize_text(item) for item in as_list(analysis.get("weak_concepts")) if normalize_text(item)],
    }
    next_profile["recent_insights"] = [insight, *as_list(next_profile.get("recent_insights"))][:10]
    prune_cleared_items(next_profile)
    next_profile["updated_at"] = now_iso()
    return next_profile


def adjust_concept_weakness(profile: dict[str, Any], concept: str, delta: float, reason: str = "") -> dict[str, Any]:
    next_profile = deepcopy(profile)
    concept_name = normalize_text(concept) or "未命名知识点"
    mastery = next_profile.setdefault("concept_mastery", {})
    current = mastery.get(concept_name, {})
    applied_delta = WEAKNESS_UPDATE_STEP if delta > 0 else (-WEAKNESS_UPDATE_STEP if delta < 0 else 0.0)
    score = clamp(float(current.get("score", 0.0)) + applied_delta)
    status = "weak" if score >= 0.55 else ("learning" if score > 0 else "familiar")

    mastery[concept_name] = {
        **current,
        "score": round(score, 2),
        "status": status,
        "evidence_count": int(current.get("evidence_count", 0) or 0) + 1,
        "last_seen": now_iso(),
    }

    if applied_delta > 0:
        update_weak_history(next_profile, {concept_name})
    elif score <= 0:
        history = as_list(next_profile.get("weak_history"))
        found = False
        for item in history:
            if isinstance(item, dict) and normalize_text(item.get("concept")) == concept_name:
                item["status"] = "cleared"
                item["cleared_at"] = now_iso()
                found = True
        if not found:
            history.insert(
                0,
                {
                    "concept": concept_name,
                    "first_seen": now_iso(),
                    "last_seen": now_iso(),
                    "evidence_count": 1,
                    "status": "cleared",
                    "cleared_at": now_iso(),
                },
            )
        next_profile["weak_history"] = history[:100]

    if reason:
        insight = {
            "created_at": now_iso(),
            "topic": concept_name,
            "summary": reason,
            "weak_concepts": [concept_name] if applied_delta > 0 else [],
        }
        next_profile["recent_insights"] = [insight, *as_list(next_profile.get("recent_insights"))][:10]

    prune_cleared_items(next_profile)
    next_profile["updated_at"] = now_iso()
    return next_profile


def set_concept_weakness(profile: dict[str, Any], concept: str, score: float, reason: str = "") -> dict[str, Any]:
    next_profile = deepcopy(profile)
    concept_name = normalize_text(concept) or "未命名知识点"
    weakness = clamp(score)
    mastery = next_profile.setdefault("concept_mastery", {})
    current = mastery.get(concept_name, {})
    status = "weak" if weakness >= 0.55 else ("learning" if weakness > 0 else "familiar")

    mastery[concept_name] = {
        **current,
        "score": round(weakness, 2),
        "status": status,
        "evidence_count": int(current.get("evidence_count", 0) or 0) + 1,
        "last_seen": now_iso(),
    }

    if weakness > 0:
        update_weak_history(next_profile, {concept_name})
    else:
        history = as_list(next_profile.get("weak_history"))
        for item in history:
            if isinstance(item, dict) and normalize_text(item.get("concept")) == concept_name:
                item["status"] = "cleared"
                item["cleared_at"] = now_iso()
        next_profile["weak_history"] = history[:100]

    if reason:
        insight = {
            "created_at": now_iso(),
            "topic": concept_name,
            "summary": reason,
            "weak_concepts": [concept_name] if weakness > 0 else [],
        }
        next_profile["recent_insights"] = [insight, *as_list(next_profile.get("recent_insights"))][:10]

    prune_cleared_items(next_profile)
    next_profile["updated_at"] = now_iso()
    return next_profile
