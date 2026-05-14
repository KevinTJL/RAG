from __future__ import annotations

import json
import re
from typing import Any

from app.ollama_client import OllamaClient


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start == -1 or end <= start:
        return {}

    try:
        data = json.loads(cleaned[start:end])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def clean_text(value: Any, limit: int = 500) -> str:
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def normalize_issue_items(items: list[Any], field: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            text = clean_text(item)
            if text:
                normalized.append({"concept": "未命名知识点", field: text, "severity": 2})
            continue

        if not isinstance(item, dict):
            continue

        concept = clean_text(item.get("concept"), 80) or "未命名知识点"
        issue = clean_text(item.get(field) or item.get("issue") or item.get("gap") or item.get("description"))
        if not issue:
            continue
        try:
            severity = int(item.get("severity", 2) or 2)
        except Exception:
            severity = 2
        severity = max(1, min(5, severity))
        normalized.append(
            {
                "concept": concept,
                field: issue,
                "severity": severity,
                "evidence": clean_text(item.get("evidence"), 240),
            }
        )
    return normalized[:6]


def clean_current_summary(value: Any) -> str:
    summary = clean_text(value, 300)
    historical_markers = (
        "已有学习画像",
        "历史",
        "之前",
        "以往",
        "weak_concepts",
        "长期记忆显示",
        "画像显示",
    )
    if any(marker in summary for marker in historical_markers):
        return ""
    return summary


def normalize_analysis(data: dict[str, Any], core_terms: list[str]) -> dict[str, Any]:
    core_concepts = [clean_text(item, 80) for item in as_list(data.get("core_concepts")) if clean_text(item, 80)]
    if not core_concepts:
        core_concepts = core_terms[:8]

    weak_concepts = [clean_text(item, 80) for item in as_list(data.get("weak_concepts")) if clean_text(item, 80)]
    return {
        "topic": clean_text(data.get("topic"), 120) or (core_concepts[0] if core_concepts else "未命名主题"),
        "summary": clean_current_summary(data.get("summary")),
        "core_concepts": core_concepts[:8],
        "weak_concepts": weak_concepts[:8],
        "knowledge_gaps": normalize_issue_items(as_list(data.get("knowledge_gaps")), "gap"),
        "misconceptions": normalize_issue_items(as_list(data.get("misconceptions")), "issue"),
        "recommended_review": [
            clean_text(item, 160)
            for item in as_list(data.get("recommended_review"))
            if clean_text(item, 160)
        ][:6],
    }


def analyze_learning_state(
    ollama: OllamaClient,
    *,
    question: str,
    answer: str,
    core_terms: list[str],
    retrieved_chunks: list[dict[str, Any]],
    user_memories: list[str],
    profile: dict[str, Any],
    model: str | None = None,
) -> dict[str, Any]:
    chunk_preview = [
        {
            "source": item.get("source", "unknown"),
            "text": clean_text(item.get("text", ""), 300),
        }
        for item in retrieved_chunks[:4]
    ]
    profile_brief = {
        "concept_weakness": profile.get("concept_mastery", {}),
        "knowledge_gaps": profile.get("knowledge_gaps", [])[:8],
        "misconceptions": profile.get("misconceptions", [])[:8],
        "recommended_review": profile.get("recommended_review", [])[:8],
    }
    prompt = f"""你是一个学习诊断助手。请根据本轮问答、检索到的知识片段、用户长期记忆和已有学习画像，判断用户当前可能存在的知识漏洞和知识体系状态。

判断原则：
1. 只根据证据做保守判断，不要过度推断。
2. 必须把“用户长期记忆”和“已有学习画像”纳入判断。
3. 如果用户只是探索性提问，可以标记为 learning，而不是强行判定为严重漏洞。
4. severity 使用 1 到 5，5 表示非常关键且反复暴露的问题。
5. summary 只能概括“本轮用户问题和助手回答”体现出的学习状态，不要复述或带入已有学习画像中的 weak_concepts、历史漏洞或历史误区。
6. 只输出 JSON 对象，不要输出解释文字。

JSON格式：
{{
  "topic": "本轮主要主题",
  "summary": "只基于本轮问答的一句话学习状态概括",
  "core_concepts": ["概念1", "概念2"],
  "weak_concepts": ["薄弱概念1"],
  "knowledge_gaps": [
    {{"concept": "概念", "gap": "具体知识漏洞", "severity": 3, "evidence": "判断依据"}}
  ],
  "misconceptions": [
    {{"concept": "概念", "issue": "可能误区或混淆", "severity": 2, "evidence": "判断依据"}}
  ],
  "recommended_review": ["建议复习内容1", "建议复习内容2"]
}}

用户问题：
{question}

助手回答：
{answer}

本轮核心词：
{json.dumps(core_terms, ensure_ascii=False)}

检索片段摘要：
{json.dumps(chunk_preview, ensure_ascii=False)}

用户长期记忆：
{json.dumps(user_memories[:12], ensure_ascii=False)}

已有学习画像：
{json.dumps(profile_brief, ensure_ascii=False)}

JSON对象："""

    response = ollama.chat([{"role": "user", "content": prompt}], model=model, temperature=0.1)
    data = extract_json_object(response)
    return normalize_analysis(data, core_terms)
