# app/api.py
import json
import os
import re
import shutil
from difflib import SequenceMatcher
from pathlib import Path
from fastapi import Depends, FastAPI, Header, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, List
from pydantic import BaseModel

from app.auth import AuthStore, AuthUser
from app.config import settings
from app.learning_analyzer import analyze_learning_state
from app.learning_profile import adjust_concept_weakness, set_concept_weakness, update_learning_profile
from app.ollama_client import OllamaClient
from app.profile_store import ProfileStore, safe_user_id
from app.review_store import ReviewStore, now_iso as review_now_iso
from app.vector_store import delete_user_memory_collection, get_collection, get_user_memory_collection
from app.ingest import delete_file_records, index_file, main as ingest_main

app = FastAPI(title="Local RAG API")
profile_store = ProfileStore()
review_store = ReviewStore()
auth_store = AuthStore()
BUILTIN_CHAT_MODELS = ("qwen2.5:3b", "deepseek-v4-pro", "deepseek-v4-flash")

FOLLOWUP_HEADING_PATTERN = re.compile(r"^\s*#{1,6}\s*推荐追问\s*$", re.MULTILINE)
FOLLOWUP_ITEM_PATTERN = re.compile(r"^\s*(?:\d+[.)]|[-*])\s*(.+?)\s*$")
FOLLOWUP_PLACEHOLDER_PATTERNS = (
    "针对本轮问题生成",
    "一个与本轮问题",
    "问题中必须包含",
    "具体的相关拓展概念问题",
    "具体的常见易错点",
    "不能使用泛泛的模板句",
    "最相关的拓展概念是什么",
    "最容易混淆的点是什么",
)


def available_chat_models() -> tuple[str, ...]:
    return tuple(dict.fromkeys([*settings.available_chat_models, *BUILTIN_CHAT_MODELS]))


def is_allowed_chat_model(model: str) -> bool:
    return model in available_chat_models()


def infer_followup_topic(question: str, core_terms: list[str] | None = None) -> str:
    if core_terms:
        selected = [term.strip() for term in core_terms if term.strip()]
        if selected:
            return "、".join(selected[:3])
    topic = question.strip().strip("？?。")
    return topic[:40] or "这个主题"


def default_followups(question: str, core_terms: list[str] | None = None) -> list[str]:
    topic = infer_followup_topic(question, core_terms)
    return [
        "这样解释清楚了吗？需要换一种方式或举例再讲一遍吗？",
        f"{topic}和它的相关概念之间有什么区别？",
        f"学习{topic}时最容易出现的误区是什么？",
    ]


def is_placeholder_followup(question: str) -> bool:
    return any(pattern in question for pattern in FOLLOWUP_PLACEHOLDER_PATTERNS)


def clean_followups(questions: list[str]) -> list[str]:
    cleaned: list[str] = []
    for question in questions:
        normalized = normalize_followup_text(question)
        if not normalized or is_placeholder_followup(normalized):
            continue
        cleaned.append(normalized)
        if len(cleaned) == 3:
            break
    return cleaned


def normalize_followup_text(question: str) -> str:
    normalized = question.strip()
    previous = None

    while normalized and normalized != previous:
        previous = normalized
        normalized = normalized.strip()
        normalized = normalized.strip("\"'`，,。 \t\n")
        normalized = normalized.strip()

        if normalized.startswith("[") and normalized.endswith("]"):
            normalized = normalized[1:-1]
            continue

        if normalized.startswith("{") and normalized.endswith("}"):
            normalized = normalized[1:-1]
            continue

    normalized = normalized.replace("\\\"", "\"").replace("\\'", "'")
    return normalized.strip().strip("\"'`，,。 \t\n")


def split_answer_and_followups(answer: str, question: str) -> tuple[str, list[str], bool]:
    """Split the model's fixed follow-up section from the answer body."""
    fallback = default_followups(question)
    match = FOLLOWUP_HEADING_PATTERN.search(answer)
    if not match:
        return answer.strip(), [], False

    body = answer[:match.start()].strip()
    followup_section = answer[match.end():].strip()
    followups: list[str] = []

    for line in followup_section.splitlines():
        item = FOLLOWUP_ITEM_PATTERN.match(line)
        if item:
            text = item.group(1).strip()
            if text:
                followups.append(text)
        if len(followups) == 3:
            break

    followups = clean_followups(followups)
    if len(followups) < 3:
        followups.extend(fallback[len(followups):])

    return body or answer.strip(), followups[:3], True


def parse_followup_response(text: str) -> list[str]:
    """Parse follow-up questions from JSON first, then from numbered/bulleted text."""
    cleaned = text.strip()

    try:
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start != -1 and end > start:
            data = json.loads(cleaned[start:end])
            questions = clean_followups(flatten_string_items(data))
            if len(questions) >= 3:
                return questions[:3]
    except Exception:
        pass

    questions: list[str] = []
    for line in cleaned.splitlines():
        item = FOLLOWUP_ITEM_PATTERN.match(line)
        if item:
            question = item.group(1).strip()
            if question:
                questions.append(question)
        if len(questions) == 3:
            break

    return clean_followups(questions)


def flatten_string_items(value) -> list[str]:
    items: list[str] = []

    if isinstance(value, str):
        text = value.strip()
        if text:
            items.append(text)
        return items

    if isinstance(value, dict):
        for key in ("question", "text", "content", "followup"):
            if key in value:
                items.extend(flatten_string_items(value[key]))
                return items
        for item in value.values():
            items.extend(flatten_string_items(item))
        return items

    if isinstance(value, list):
        for item in value:
            items.extend(flatten_string_items(item))
        return items

    if value is not None:
        text = str(value).strip()
        if text:
            items.append(text)

    return items


def parse_core_terms_response(text: str) -> list[str]:
    cleaned = text.strip()

    try:
        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1
        if start != -1 and end > start:
            data = json.loads(cleaned[start:end])
            terms = [str(item).strip().strip("\"'`，,。") for item in data if str(item).strip()]
            return terms[:8]
    except Exception:
        pass

    terms: list[str] = []
    for part in re.split(r"[,，、\n;；]", cleaned):
        term = part.strip().strip("\"'`，,。")
        if term:
            terms.append(term)
        if len(terms) == 8:
            break
    return terms


def extract_core_terms(ollama: OllamaClient, question: str, model: str | None = None) -> list[str]:
    prompt = f"""请从下面的问题中提取用于知识库检索的核心知识点。

要求：
1. 只提取对检索最有帮助的核心概念、术语、对象、方法名或关键词。
2. 保留原问题中的专业术语，例如算法名、公式名、指标名、英文缩写。
3. 不要解释，不要回答问题。
4. 只输出JSON数组，最多8个字符串。

问题：{question}

JSON数组："""
    response = ollama.chat([{"role": "user", "content": prompt}], model=model, temperature=0.1)
    return parse_core_terms_response(response)


def build_retrieval_query(question: str, core_terms: list[str]) -> str:
    if not core_terms:
        return question
    return f"{question}\n核心知识点：{'、'.join(core_terms)}"


def generate_followups(ollama: OllamaClient, question: str, answer: str, core_terms: list[str] | None = None, model: str | None = None) -> list[str]:
    topic = infer_followup_topic(question, core_terms)
    prompt = f"""请基于用户问题、主题关键词和助手回答，生成正好3个适合用户继续追问的问题。

要求：
1. 第1个问题询问用户是否解释清楚，是否需要换一种方式或举例说明。
2. 第2个问题必须是与本轮主题直接相关的具体拓展概念问题，不能使用泛泛的模板句。
3. 第3个问题必须是与本轮主题相关的具体易错点、误区或常见混淆问题，不能使用泛泛的模板句。
4. 每个问题都必须包含本轮回答中的具体概念名称。
5. 禁止输出“针对本轮问题生成一个...”这类任务说明或占位句。
6. 禁止输出“最相关的拓展概念是什么”“最容易混淆的点是什么”这类模板句。
7. 只输出一维JSON字符串数组，不要嵌套数组，不要输出任何解释文字。

用户问题：{question}

主题关键词：{topic}

助手回答：{answer}

JSON数组："""
    response = ollama.chat([{"role": "user", "content": prompt}], model=model, temperature=0.2)
    return parse_followup_response(response)


def repair_followups(
    ollama: OllamaClient,
    question: str,
    answer: str,
    core_terms: list[str],
    current_followups: list[str],
    model: str | None = None,
) -> list[str]:
    topic = infer_followup_topic(question, core_terms)
    prompt = f"""请把下面的推荐追问修复为正好3个自然、具体、可点击的中文问题。

要求：
1. 保留第1个“是否解释清楚/是否需要举例”的意图，但要结合主题关键词。
2. 第2个必须问一个具体拓展概念，例如某个算法、指标、假设、步骤或应用场景。
3. 第3个必须问一个具体易错点或常见混淆。
4. 不要输出“最相关的拓展概念是什么”“最容易混淆的点是什么”这类模板句。
5. 只输出一维JSON字符串数组。

用户问题：{question}
主题关键词：{topic}
助手回答：{answer}
当前追问：{json.dumps(current_followups, ensure_ascii=False)}

JSON数组："""
    response = ollama.chat([{"role": "user", "content": prompt}], model=model, temperature=0.15)
    return parse_followup_response(response)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def healthcheck():
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "chat_models": list(available_chat_models()),
        "embed_model": settings.embed_model,
    }


@app.get("/")
async def root():
    return FileResponse("index.html")

class MessageItem(BaseModel):
    role: str
    content: str

class QueryRequest(BaseModel):
    question: str
    user_id: str = "default"
    history: List[MessageItem] = []
    chat_model: Optional[str] = None


class ReviewPlanRequest(BaseModel):
    user_id: str
    topic: str
    weak_score: float = 0.0
    difficulty: Optional[int] = None
    mode: str = "topic"
    chat_model: Optional[str] = None


class ReviewAnswerRequest(BaseModel):
    user_id: str
    session_id: str
    step_id: str
    answer: str


class ReviewCompleteRequest(BaseModel):
    user_id: str
    session_id: str
    completed: bool = True


class WeaknessUpdateRequest(BaseModel):
    concept: str
    delta: float
    reason: str = ""


MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 5
WEAKNESS_START_SCORE = 0.6


def clamp_difficulty(value: int | float | str | None) -> int:
    try:
        level = int(value or MIN_DIFFICULTY)
    except Exception:
        level = MIN_DIFFICULTY
    return max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, level))


def difficulty_from_weakness(score: float | int | str | None) -> int:
    try:
        weakness = max(0.0, min(1.0, float(score or 0.0)))
    except Exception:
        weakness = 0.0
    if weakness >= 0.99:
        return 1
    if weakness >= 0.8:
        return 2
    if weakness >= 0.6:
        return 3
    if weakness >= 0.4:
        return 4
    return 5


def next_difficulty_from_correct_count(current: int, correct_count: int) -> int:
    current = clamp_difficulty(current)
    if correct_count >= 4:
        return clamp_difficulty(current + 1)
    if correct_count == 3:
        return current
    return clamp_difficulty(current - 1)


def paper_result_label(correct_count: int) -> str:
    if correct_count >= 4:
        return "excellent"
    if correct_count == 3:
        return "passed"
    return "failed"


class ProfileTagDeleteRequest(BaseModel):
    category: str
    value: str


class AuthRequest(BaseModel):
    email: str
    password: str


def normalize_chat_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized == "bot":
        return "assistant"
    if normalized in {"system", "user", "assistant", "tool"}:
        return normalized
    return "user"


def current_user(authorization: Optional[str] = Header(default=None), access_token: Optional[str] = None) -> AuthUser:
    token = access_token or ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    user = auth_store.user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return user


def assert_user_access(user_id: str, user: AuthUser) -> None:
    if safe_user_id(user_id) != safe_user_id(user.id):
        raise HTTPException(status_code=403, detail="无权访问该用户数据")


def data_dir_for_user(user_id: str) -> Path:
    return settings.user_data_root / safe_user_id(user_id)


def public_data_dir() -> Path:
    return settings.data_dir


@app.post("/api/auth/register")
async def register(request: AuthRequest):
    try:
        user = auth_store.create_user(request.email, request.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"token": auth_store.issue_token(user), "user": {"id": user.id, "email": user.email}}


@app.post("/api/auth/login")
async def login(request: AuthRequest):
    user = auth_store.authenticate(request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    return {"token": auth_store.issue_token(user), "user": {"id": user.id, "email": user.email}}


@app.get("/api/auth/me")
async def me(user: AuthUser = Depends(current_user)):
    return {"user": {"id": user.id, "email": user.email}}


@app.get("/api/models")
async def list_models():
    return {
        "default_chat_model": settings.chat_model,
        "chat_models": list(available_chat_models()),
        "embed_model": settings.embed_model,
    }


def get_all_user_memories(collection, limit: int = 12) -> list[str]:
    try:
        total = collection.count()
        if total <= 0:
            return []
        result = collection.get(limit=min(total, limit), include=["documents"])
        return [str(item) for item in result.get("documents", []) if item]
    except Exception:
        return []


def clean_abstract_evaluation(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = cleaned.strip("\"'`，,。 \t\n")
    if not cleaned:
        return ""
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip("，,；;、 ")
    return cleaned


def fallback_abstract_evaluation(profile: dict, question: str) -> str:
    recent_questions = profile.get("recent_questions") if isinstance(profile.get("recent_questions"), list) else []
    weak_items = profile.get("concept_mastery") if isinstance(profile.get("concept_mastery"), dict) else {}
    active_weak = [
        concept
        for concept, item in weak_items.items()
        if isinstance(item, dict) and float(item.get("score", 0.0) or 0.0) > 0
    ]
    if len(recent_questions) <= 1:
        return f"用户正围绕{question[:18]}建立基础理解。"
    if active_weak:
        return f"用户提问聚焦具体概念，但仍需巩固{str(active_weak[0])[:18]}。"
    return "用户提问较聚焦，正在形成更系统的知识连接。"


def generate_abstract_evaluation(
    ollama: OllamaClient,
    *,
    profile: dict,
    question: str,
    model: str | None = None,
) -> str:
    recent_questions = [
        item.get("question", "")
        for item in profile.get("recent_questions", [])
        if isinstance(item, dict) and item.get("question")
    ][:8]
    recent_insights = [
        {
            "topic": item.get("topic", ""),
            "summary": item.get("summary", ""),
            "weak_concepts": item.get("weak_concepts", []),
        }
        for item in profile.get("recent_insights", [])[:6]
        if isinstance(item, dict)
    ]
    weak_concepts = [
        {"concept": concept, "weakness": data.get("score", 0)}
        for concept, data in (profile.get("concept_mastery", {}) or {}).items()
        if isinstance(data, dict) and float(data.get("score", 0.0) or 0.0) > 0
    ][:8]
    prompt = f"""请基于用户最近的提问方式、提问内容和学习画像，生成一句中文抽象评价。

要求：
1. 只输出一句话，不要标题、编号或解释。
2. 评价用户当前学习状态、提问风格或知识体系特点。
3. 保守判断，不要贴人格标签，不要夸大。
4. 40字以内。

最近提问：
{json.dumps(recent_questions, ensure_ascii=False)}

最近学习洞察：
{json.dumps(recent_insights, ensure_ascii=False)}

当前薄弱概念：
{json.dumps(weak_concepts, ensure_ascii=False)}

当前问题：
{question}

一句话评价："""
    try:
        raw = ollama.chat([{"role": "user", "content": prompt}], model=model, temperature=0.2)
    except Exception:
        return fallback_abstract_evaluation(profile, question)
    return clean_abstract_evaluation(raw) or fallback_abstract_evaluation(profile, question)


def safe_data_file(filename: str, user_id: str, scope: str = "personal") -> Path:
    root_dir = public_data_dir() if scope == "system" else data_dir_for_user(user_id)
    target = (root_dir / filename).resolve()
    root = root_dir.resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=400, detail="非法文件路径")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return target


def parse_json_object(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start:end])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def remove_profile_tag(profile: dict, category: str, value: str) -> dict:
    category = category.strip()
    value = value.strip()
    if not value:
        return profile

    if category == "concept_mastery":
        mastery = profile.get("concept_mastery", {})
        if isinstance(mastery, dict):
            mastery.pop(value, None)
        profile["knowledge_gaps"] = [
            item
            for item in profile.get("knowledge_gaps", [])
            if not isinstance(item, dict) or str(item.get("concept", "")).strip() != value
        ]
        profile["misconceptions"] = [
            item
            for item in profile.get("misconceptions", [])
            if not isinstance(item, dict) or str(item.get("concept", "")).strip() != value
        ]
        profile["recommended_review"] = [
            item for item in profile.get("recommended_review", []) if value not in str(item)
        ]
        profile["weak_history"] = [
            item
            for item in profile.get("weak_history", [])
            if not isinstance(item, dict) or str(item.get("concept", "")).strip() != value
        ]
    elif category == "recommended_review":
        profile["recommended_review"] = [
            item for item in profile.get("recommended_review", []) if str(item).strip() != value
        ]
    elif category == "weak_history":
        profile["weak_history"] = [
            item
            for item in profile.get("weak_history", [])
            if not isinstance(item, dict) or str(item.get("concept", "")).strip() != value
        ]
    elif category == "knowledge_gap":
        profile["knowledge_gaps"] = [
            item
            for item in profile.get("knowledge_gaps", [])
            if not isinstance(item, dict)
            or (str(item.get("concept", "")).strip() != value and str(item.get("gap", item.get("issue", ""))).strip() != value)
        ]
    elif category == "misconception":
        profile["misconceptions"] = [
            item
            for item in profile.get("misconceptions", [])
            if not isinstance(item, dict)
            or (str(item.get("concept", "")).strip() != value and str(item.get("gap", item.get("issue", ""))).strip() != value)
        ]
    elif category == "recent_insight":
        profile["recent_insights"] = [
            item
            for item in profile.get("recent_insights", [])
            if not isinstance(item, dict) or str(item.get("created_at", "")).strip() != value
        ]

    return profile


def default_quiz_step(topic: str, index: int, difficulty: int = 1) -> dict:
    difficulty = clamp_difficulty(difficulty)
    questions = [
        (
            f"{topic} 的核心定义是什么？",
            ["A. 只记忆术语名称", f"B. 理解 {topic} 的定义、条件和用途", "C. 跳过公式和例子", "D. 只关注代码实现"],
            f"B. 理解 {topic} 的定义、条件和用途",
            "学习薄弱概念时，应先建立定义、适用条件和用途之间的联系。",
        ),
        (
            f"使用 {topic} 时最需要先判断什么？",
            ["A. 是否满足适用条件", "B. 是否能直接套用所有公式", "C. 是否可以忽略数据特点", "D. 是否只需要记住结论"],
            "A. 是否满足适用条件",
            "方法是否适用通常取决于问题条件、数据特点和目标。",
        ),
        (
            f"关于 {topic} 的常见误区是哪一项？",
            ["A. 结合例子理解", "B. 比较相近概念", "C. 只背结论而不看前提", "D. 关注变量含义"],
            "C. 只背结论而不看前提",
            "只背结论容易导致迁移应用时混淆条件和边界。",
        ),
        (
            f"如果要判断自己是否掌握了 {topic}，最有效的是哪种方式？",
            ["A. 复述定义并举例说明", "B. 只看一遍讲解", "C. 只记关键词", "D. 跳过易错点"],
            "A. 复述定义并举例说明",
            "能用自己的话解释并举例，说明概念已开始内化。",
        ),
        (
            f"难度 {difficulty}：遇到 {topic} 的变式问题时，应该优先做什么？",
            ["A. 找到问题目标和约束条件", "B. 直接套最近见过的答案", "C. 忽略概念差异", "D. 只看题目中的熟悉词"],
            "A. 找到问题目标和约束条件",
            "变式题的关键是识别目标、条件和概念边界，而不是机械套用。",
        ),
    ]
    question, options, answer, explanation = questions[(index - 1) % len(questions)]
    return {
        "id": f"quiz-{index}",
        "type": "quiz",
        "title": f"第 {index} 题",
        "question": question,
        "options": options,
        "answer": answer,
        "explanation": explanation,
    }


def default_blank_step(topic: str, index: int, difficulty: int = 1) -> dict:
    difficulty = clamp_difficulty(difficulty)
    return {
        "id": f"blank-{index}",
        "type": "blank",
        "title": f"第 {index} 题",
        "question": f"填空：学习 {topic} 时，需要同时理解它的定义、适用条件和____。",
        "answer": "应用场景",
        "accepted_answers": ["应用场景", "用途", "使用场景"],
        "explanation": f"{topic} 不能只记定义，还要知道在什么问题中使用。",
    }


def default_practice_step(topic: str, index: int, difficulty: int = 1) -> dict:
    if index in {2, 5}:
        return default_blank_step(topic, index, difficulty)
    return default_quiz_step(topic, index, difficulty)


def default_review_plan(topic: str, difficulty: int = 1) -> dict:
    difficulty = clamp_difficulty(difficulty)
    return {
        "topic": topic,
        "overview": f"围绕 {topic} 生成 5 道 {difficulty} 级题目，完成后按答对数量自动调整下一套难度。",
        "difficulty": difficulty,
        "steps": [
            {
                "id": "explain-1",
                "type": "explain",
                "title": f"{topic} 核心讲解",
                "content": f"先梳理 {topic} 的定义、适用场景、关键步骤和常见误区。本套为 {difficulty} 级难度，级别越高越强调迁移应用、易错混淆和综合判断。",
            },
            *[default_practice_step(topic, index, difficulty) for index in range(1, 6)],
        ],
    }


def extract_labeled_options(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    matches = re.finditer(r"(?:^|\s)([A-H])[.、．]\s*(.*?)(?=\s+[A-H][.、．]\s*|$)", normalized)
    return [f"{match.group(1)}. {match.group(2).strip()}" for match in matches if match.group(2).strip()]


def strip_inline_options(text: str) -> str:
    raw = str(text or "")
    match = re.search(r"(?:^|\s)[A-H][.、．]\s*", raw)
    return raw[: match.start()].strip() if match and match.start() > 0 else raw.strip()


def option_label(option: str) -> str:
    match = re.match(r"\s*([A-H])(?:[.、．]|\s*$)", str(option or ""))
    return match.group(1) if match else ""


def split_review_options(options, question: str = "") -> list[str]:
    if not isinstance(options, list):
        options = [options] if options else []

    split_options: list[str] = []
    split_options.extend(extract_labeled_options(question))
    for option in options:
        text = str(option or "").strip()
        if not text:
            continue
        parts = [part.strip() for part in re.split(r"\s*(?=[A-H][.、．]\s*)", text) if part.strip()]
        split_options.extend(parts if len(parts) > 1 else [text])

    unique: list[str] = []
    seen_labels: set[str] = set()
    seen_text: set[str] = set()
    for option in split_options:
        label = option_label(option)
        key = label or option
        if (label and label in seen_labels) or option in seen_text:
            continue
        if label:
            seen_labels.add(label)
        seen_text.add(option)
        unique.append(option)

    return unique[:8]


def normalize_question_text(text: str) -> str:
    normalized = str(text or "").lower()
    normalized = re.sub(r"[a-h][.、．]", "", normalized)
    normalized = re.sub(r"[\s，。！？、；：,.!?;:\"'`“”‘’（）()【】\[\]{}<>《》]+", "", normalized)
    return normalized


def review_step_question_text(step: dict) -> str:
    if not isinstance(step, dict):
        return ""
    parts = [
        str(step.get("title", "")),
        str(step.get("question", "")),
    ]
    options = step.get("options")
    if isinstance(options, list):
        parts.extend(str(option) for option in options)
    return " ".join(part for part in parts if part)


def are_similar_questions(left: str, right: str, threshold: float = 0.82) -> bool:
    left_norm = normalize_question_text(left)
    right_norm = normalize_question_text(right)
    if not left_norm or not right_norm:
        return False
    shorter, longer = sorted([left_norm, right_norm], key=len)
    if len(shorter) >= 8 and shorter in longer:
        return True
    return SequenceMatcher(None, left_norm, right_norm).ratio() >= threshold


def collect_review_questions(user_id: str, topic: str | None = None, limit: int = 80) -> list[str]:
    """Collect recent generated questions so the next paper can avoid repeats."""
    questions: list[str] = []
    normalized_topic = normalize_question_text(topic or "")
    for session in review_store.load_all(user_id):
        if not isinstance(session, dict):
            continue
        session_topic = str(session.get("topic", ""))
        if normalized_topic and session_topic:
            same_topic = normalize_question_text(session_topic) == normalized_topic
            related_topic = are_similar_questions(session_topic, topic or "", threshold=0.68)
            if not same_topic and not related_topic:
                continue

        plan = session.get("plan") if isinstance(session.get("plan"), dict) else {}
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        for step in steps:
            if not isinstance(step, dict) or step.get("type") not in {"quiz", "blank", "fill_blank", "question"}:
                continue
            question = review_step_question_text(step)
            if question:
                questions.append(question)
                if len(questions) >= limit:
                    return questions
    return questions


def is_duplicate_review_step(step: dict, selected_steps: list[dict], forbidden_questions: list[str]) -> bool:
    question = review_step_question_text(step)
    if not question:
        return True
    question_only = str(step.get("question", ""))
    previous_questions = [review_step_question_text(item) for item in selected_steps]
    previous_question_only = [str(item.get("question", "")) for item in selected_steps]
    return any(
        are_similar_questions(candidate, previous)
        for candidate in [question, question_only]
        for previous in [*previous_questions, *previous_question_only, *forbidden_questions]
    )


def normalize_review_plan(
    plan: dict,
    topic: str,
    difficulty: int = 1,
    forbidden_questions: list[str] | None = None,
) -> dict:
    difficulty = clamp_difficulty(difficulty)
    if not isinstance(plan, dict):
        return default_review_plan(topic, difficulty)

    steps = plan.get("steps")
    if not isinstance(steps, list):
        return default_review_plan(topic, difficulty)

    forbidden_questions = forbidden_questions or []
    normalized_steps: list[dict] = []
    explain = next((step for step in steps if isinstance(step, dict) and step.get("type") == "explain"), None)
    if isinstance(explain, dict):
        explain.setdefault("id", "explain-1")
        normalized_steps.append(explain)
    else:
        normalized_steps.append(default_review_plan(topic, difficulty)["steps"][0])

    practice_steps = [step for step in steps if isinstance(step, dict) and step.get("type") in {"quiz", "blank", "fill_blank"}]
    selected_practice_steps: list[dict] = []
    for index, step in enumerate(practice_steps, start=1):
        if not isinstance(step, dict):
            continue
        original_type = "blank" if step.get("type") in {"blank", "fill_blank"} else "quiz"
        step = dict(step)
        step["id"] = f"{original_type}-{index}"
        step["type"] = original_type
        step.setdefault("title", f"第 {index} 题")
        if original_type == "quiz":
            step["options"] = split_review_options(step.get("options"), step.get("question", ""))
            step["question"] = strip_inline_options(step.get("question", ""))
            if len(step["options"]) != 4:
                step["options"] = default_quiz_step(topic, index, difficulty)["options"]
            answer = str(step.get("answer", "")).strip()
            matching = next((option for option in step["options"] if option == answer or option.startswith(answer) or option_label(option) == answer), "")
            step["answer"] = matching or default_quiz_step(topic, index, difficulty)["answer"]
            step.setdefault("explanation", default_quiz_step(topic, index, difficulty)["explanation"])
        else:
            fallback = default_blank_step(topic, index, difficulty)
            step.setdefault("question", fallback["question"])
            step.setdefault("answer", fallback["answer"])
            accepted = step.get("accepted_answers")
            if not isinstance(accepted, list) or not accepted:
                step["accepted_answers"] = [str(step.get("answer", fallback["answer"])).strip(), *fallback["accepted_answers"]]
            step.setdefault("explanation", fallback["explanation"])

        if is_duplicate_review_step(step, selected_practice_steps, forbidden_questions):
            continue
        selected_practice_steps.append(step)
        if len(selected_practice_steps) == 5:
            break

    while len(selected_practice_steps) < 5:
        next_index = len(selected_practice_steps) + 1
        fallback = default_practice_step(topic, next_index + difficulty, difficulty)
        fallback["title"] = f"第 {next_index} 题"
        if not is_duplicate_review_step(fallback, selected_practice_steps, forbidden_questions):
            selected_practice_steps.append(fallback)
            continue
        fallback["question"] = f"{fallback.get('question', '')}（补充练习 {next_index}，请结合本次材料作答）"
        selected_practice_steps.append(fallback)

    explain_step = normalized_steps[0]
    practice_only = selected_practice_steps[:5]
    for index, step in enumerate(practice_only, start=1):
        step["id"] = f"{step.get('type', 'quiz')}-{index}"
        step["title"] = f"第 {index} 题"

    plan["steps"] = [explain_step, *practice_only]
    plan["topic"] = plan.get("topic") or topic
    plan["difficulty"] = difficulty
    plan.setdefault("overview", f"围绕 {topic} 生成 5 道 {difficulty} 级题目，完成后按答对数量自动调整下一套难度。")
    return plan


def generate_comprehensive_review_plan(
    ollama: OllamaClient,
    profile: dict,
    difficulty: int = 1,
    model: str | None = None,
    forbidden_questions: list[str] | None = None,
) -> dict:
    topic = "综合学习画像试卷"
    forbidden_questions = forbidden_questions or []
    prompt = f"""请根据用户学习画像生成一张综合试卷，只输出JSON对象。

要求：
1. 主题是：{topic}
2. 覆盖薄弱概念、薄弱历史、知识漏洞、常见误区和建议学习模块。
3. 必须包含 steps 数组：1 个 explain 步骤 + 至少 8 个候选练习步骤；系统会从中筛选 5 个不重复题目。
4. 练习步骤可以是 quiz 或 blank，其中至少 5 个 quiz，至少 2 个 blank。
5. quiz 必须正好有 4 个独立 options，answer 必须等于完整 option。
6. blank 必须包含 answer 和 accepted_answers。
7. 难度等级采用五级制度：1级最简单，5级最难。本套必须是 {difficulty} 级。
8. 禁止生成与“已出现题目”语义相同、只换说法或只替换选项顺序的题目。

学习画像：
{json.dumps(profile, ensure_ascii=False)[:5000]}

已出现题目：
{json.dumps(forbidden_questions[:60], ensure_ascii=False)}

JSON格式同：
{{
  "topic": "{topic}",
  "overview": "综合复习目标",
  "steps": [
    {{"id": "explain-1", "type": "explain", "title": "综合说明", "content": "说明"}},
    {{"id": "quiz-1", "type": "quiz", "title": "第 1 题", "question": "题目", "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"], "answer": "A. 选项1", "explanation": "解释"}},
    {{"id": "blank-2", "type": "blank", "title": "第 2 题", "question": "填空题", "answer": "标准答案", "accepted_answers": ["标准答案"], "explanation": "解释"}}
  ]
}}"""
    raw = ollama.chat([{"role": "user", "content": prompt}], model=model, temperature=0.2)
    plan = parse_json_object(raw) or default_review_plan(topic, difficulty)
    return normalize_review_plan(plan, topic, difficulty, forbidden_questions=forbidden_questions)


def generate_review_plan(
    ollama: OllamaClient,
    topic: str,
    difficulty: int = 1,
    model: str | None = None,
    forbidden_questions: list[str] | None = None,
) -> dict:
    forbidden_questions = forbidden_questions or []
    prompt = f"""请根据用户给定主题和要求生成一张学习试卷，只输出JSON对象。

要求：
1. 主题是：{topic}
2. 难度等级采用五级制度：1级最简单，5级最难。本套必须是 {difficulty} 级；等级越高，题目越强调迁移应用、易错混淆和综合判断。
3. 必须包含 steps 数组：1 个 explain 步骤 + 至少 8 个候选练习步骤；系统会从中筛选 5 个不重复题目。
4. 练习步骤可以是 quiz 或 blank，其中至少 5 个 quiz，至少 2 个 blank。
5. quiz 必须是单选题，不要生成判断题，不要在标题中写“判断题”；每个 quiz 必须正好有 4 个 options，每个选项是独立字符串，格式如 "A. 选项内容"。
6. blank 是填空题，必须包含 answer 和 accepted_answers 数组。
7. quiz 的 answer 必须等于某一个完整 option 字符串，不能只写 A/B/C/D。
8. 涉及数学公式时，必须使用 $...$ 或 $$...$$ 包裹 LaTeX，例如 $x_{{n+1}} = x_n - H^{{-1}}(x_n)\\nabla f(x_n)$。
9. 题目应围绕主题本身、关键概念、适用条件、计算步骤、应用场景和常见误区展开。
10. 禁止生成与“已出现题目”语义相同、只换说法或只替换选项顺序的题目。

已出现题目：
{json.dumps(forbidden_questions[:40], ensure_ascii=False)}

JSON格式：
{{
  "topic": "{topic}",
  "overview": "学习目标",
  "steps": [
    {{"id": "explain-1", "type": "explain", "title": "标题", "content": "讲解内容"}},
    {{"id": "quiz-1", "type": "quiz", "title": "第 1 题", "question": "题目", "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"], "answer": "A. 选项1", "explanation": "解释"}},
    {{"id": "blank-2", "type": "blank", "title": "第 2 题", "question": "填空题", "answer": "标准答案", "accepted_answers": ["标准答案", "近义答案"], "explanation": "解释"}},
    {{"id": "quiz-3", "type": "quiz", "title": "第 3 题", "question": "题目", "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"], "answer": "C. 选项3", "explanation": "解释"}},
    {{"id": "quiz-4", "type": "quiz", "title": "第 4 题", "question": "题目", "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"], "answer": "D. 选项4", "explanation": "解释"}},
    {{"id": "blank-5", "type": "blank", "title": "第 5 题", "question": "填空题", "answer": "标准答案", "accepted_answers": ["标准答案", "近义答案"], "explanation": "解释"}},
    {{"id": "quiz-6", "type": "quiz", "title": "第 6 题", "question": "题目", "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"], "answer": "B. 选项2", "explanation": "解释"}},
    {{"id": "quiz-7", "type": "quiz", "title": "第 7 题", "question": "题目", "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"], "answer": "A. 选项1", "explanation": "解释"}},
    {{"id": "blank-8", "type": "blank", "title": "第 8 题", "question": "填空题", "answer": "标准答案", "accepted_answers": ["标准答案", "近义答案"], "explanation": "解释"}}
  ]
}}"""
    raw = ollama.chat([{"role": "user", "content": prompt}], model=model, temperature=0.2)
    plan = parse_json_object(raw) or default_review_plan(topic, difficulty)
    return normalize_review_plan(plan, topic, difficulty, forbidden_questions=forbidden_questions)

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), user: AuthUser = Depends(current_user)):
    """上传知识文档到指定目录，并只索引该文件"""
    user_data_dir = data_dir_for_user(user.id)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in {".txt", ".md", ".pdf"}:
        raise HTTPException(status_code=400, detail="仅支持 .txt、.md、.pdf 文件")
    file_path = user_data_dir / filename
    with Path(file_path).open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        indexed_chunks = index_file(file_path, user_id=user.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件已上传，但增量索引失败：{e}")

    return {
        "message": f"文件 {filename} 上传成功，已增量更新 {indexed_chunks} 个知识库切片。",
        "filename": filename,
        "indexed_chunks": indexed_chunks,
    }

@app.get("/api/files")
async def list_files(user: AuthUser = Depends(current_user)):
    """列出知识库中的所有文件"""
    system_files: list[str] = []
    if public_data_dir().exists():
        system_files = [
            f.name
            for f in public_data_dir().iterdir()
            if f.is_file() and f.suffix.lower() in {".txt", ".md", ".pdf"}
        ]

    user_data_dir = data_dir_for_user(user.id)
    personal_files: list[str] = []
    if user_data_dir.exists():
        personal_files = [
            f.name
            for f in user_data_dir.iterdir()
            if f.is_file() and f.suffix.lower() in {".txt", ".md", ".pdf"}
        ]

    return {
        "files": sorted(personal_files),
        "personal_files": sorted(personal_files),
        "system_files": sorted(system_files),
        "data_dir": str(user_data_dir),
        "system_data_dir": str(public_data_dir()),
    }


@app.get("/api/files/{filename}/preview")
async def preview_file(filename: str, scope: str = "personal", user: AuthUser = Depends(current_user)):
    """返回知识库文件预览信息。PDF 由前端通过 raw_url 使用 PDF.js 渲染。"""
    if scope not in {"system", "personal"}:
        raise HTTPException(status_code=400, detail="非法知识库范围")
    file_path = safe_data_file(filename, user.id, scope=scope)
    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return {
            "filename": file_path.name,
            "type": suffix.lstrip("."),
            "content": file_path.read_text(encoding="utf-8", errors="ignore"),
        }
    if suffix == ".pdf":
        return {
            "filename": file_path.name,
            "type": "pdf",
            "raw_url": f"/api/files/{file_path.name}/raw",
        }
    raise HTTPException(status_code=400, detail="不支持预览的文件类型")


@app.get("/api/files/{filename}/raw")
async def raw_file(filename: str, scope: str = "personal", user: AuthUser = Depends(current_user)):
    """返回知识库原文件，供前端预览或 PDF.js 渲染。"""
    if scope not in {"system", "personal"}:
        raise HTTPException(status_code=400, detail="非法知识库范围")
    file_path = safe_data_file(filename, user.id, scope=scope)
    return FileResponse(str(file_path), filename=file_path.name)


@app.get("/api/profile/{user_id}")
async def get_learning_profile(user_id: str, user: AuthUser = Depends(current_user)):
    """返回当前用户的结构化学习画像"""
    assert_user_access(user_id, user)
    return {"profile": profile_store.load(user_id)}


@app.post("/api/profile/{user_id}/tag/delete")
async def delete_profile_tag(user_id: str, request: ProfileTagDeleteRequest, user: AuthUser = Depends(current_user)):
    """删除学习画像中的单个标签或条目。"""
    assert_user_access(user_id, user)
    profile = profile_store.load(user_id)
    profile = remove_profile_tag(profile, request.category, request.value)
    profile = profile_store.save(user_id, profile)
    return {"profile": profile}


@app.delete("/api/user/{user_id}/history")
async def clear_user_history(user_id: str, user: AuthUser = Depends(current_user)):
    """清除当前用户的长期记忆和学习画像；前端聊天记录由浏览器本地清除。"""
    assert_user_access(user_id, user)
    delete_user_memory_collection(user_id)
    profile = profile_store.clear(user_id)
    return {"message": "用户问答历史、长期记忆和学习画像已清除", "profile": profile}


@app.delete("/api/user/{user_id}/all-history")
async def clear_all_user_history(user_id: str, user: AuthUser = Depends(current_user)):
    """清除当前用户所有历史数据，但不清空知识库。"""
    assert_user_access(user_id, user)
    delete_user_memory_collection(user_id)
    profile = profile_store.clear(user_id)
    review_store.clear(user_id)
    return {"message": "已清空问答历史、用户画像、学习计划和学习历史，知识库未受影响", "profile": profile}


@app.get("/api/review/history/{user_id}")
async def get_review_history(user_id: str, user: AuthUser = Depends(current_user)):
    assert_user_access(user_id, user)
    sessions = review_store.load_all(user_id)
    changed = False
    normalized_sessions = []
    for session in sessions:
        if not isinstance(session, dict):
            normalized_sessions.append(session)
            continue
        if session.get("status") == "completed":
            normalized_sessions.append(session)
            continue
        plan = session.get("plan") if isinstance(session.get("plan"), dict) else {}
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        practice_count = len([step for step in steps if isinstance(step, dict) and step.get("type") in {"quiz", "blank", "fill_blank"}])
        if practice_count < 5:
            difficulty = int(session.get("difficulty") or plan.get("difficulty") or 1)
            session["plan"] = normalize_review_plan(plan or default_review_plan(session.get("topic", "未命名主题"), difficulty), session.get("topic", "未命名主题"), difficulty)
            session["difficulty"] = difficulty
            changed = True
        normalized_sessions.append(session)
    if changed:
        review_store.save_all(user_id, normalized_sessions)
    return {"sessions": normalized_sessions}


@app.delete("/api/review/{user_id}/{session_id}")
async def delete_review_session(user_id: str, session_id: str, user: AuthUser = Depends(current_user)):
    assert_user_access(user_id, user)
    deleted = review_store.delete(user_id, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="复习计划不存在")
    return {"message": "复习计划已删除", "sessions": review_store.load_all(user_id)}


@app.delete("/api/review/{user_id}/{session_id}/steps/{step_key}")
async def delete_review_step(user_id: str, session_id: str, step_key: str, user: AuthUser = Depends(current_user)):
    assert_user_access(user_id, user)
    updated = review_store.delete_step(user_id, session_id, step_key)
    if not updated:
        raise HTTPException(status_code=404, detail="复习步骤不存在")
    return {"message": "复习模块已删除", "session": updated}


@app.post("/api/review/plan")
async def create_review_plan(request: ReviewPlanRequest, user: AuthUser = Depends(current_user)):
    assert_user_access(request.user_id, user)
    chat_model = (request.chat_model or settings.chat_model).strip()
    if not is_allowed_chat_model(chat_model):
        raise HTTPException(status_code=400, detail=f"不支持的聊天模型：{chat_model}")

    ollama = OllamaClient()
    try:
        ollama.healthcheck()
    except Exception:
        raise HTTPException(status_code=503, detail="Ollama 未启动或不可用")

    difficulty = (
        clamp_difficulty(request.difficulty)
        if request.difficulty is not None
        else difficulty_from_weakness(request.weak_score) if request.weak_score > 0 else 3
    )
    profile = profile_store.load(request.user_id)
    mode = request.mode.strip().lower()
    if mode == "comprehensive":
        topic = "综合学习画像试卷"
        forbidden_questions = collect_review_questions(request.user_id, limit=120)
        plan = generate_comprehensive_review_plan(
            ollama,
            profile,
            difficulty,
            model=chat_model,
            forbidden_questions=forbidden_questions,
        )
    else:
        topic = request.topic
        forbidden_questions = collect_review_questions(request.user_id, topic=topic, limit=80)
        plan = generate_review_plan(
            ollama,
            topic,
            difficulty,
            model=chat_model,
            forbidden_questions=forbidden_questions,
        )
    session = review_store.add(
        request.user_id,
        {
            "user_id": request.user_id,
            "topic": topic,
            "weak_score": request.weak_score,
            "difficulty": difficulty,
            "mode": mode,
            "plan": plan,
            "answers": {},
            "score": 0.0,
            "status": "active",
            "created_at": review_now_iso(),
        },
    )
    return {"session": session}


@app.post("/api/review/answer")
async def judge_review_answer(request: ReviewAnswerRequest, user: AuthUser = Depends(current_user)):
    assert_user_access(request.user_id, user)
    session = review_store.get(request.user_id, request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="复习记录不存在")

    steps = session.get("plan", {}).get("steps", [])
    step = next((item for item in steps if item.get("id") == request.step_id), None)
    if not step:
        raise HTTPException(status_code=404, detail="复习步骤不存在")

    is_correct = False
    feedback = ""
    if step.get("type") == "quiz":
        expected = str(step.get("answer", "")).strip()
        actual = request.answer.strip()
        expected_label = option_label(expected)
        actual_label = option_label(actual)
        is_correct = actual == expected or (
            len(expected) == 1
            and expected.upper() in "ABCDEFGH"
            and actual.upper().startswith(expected.upper())
        ) or (
            bool(expected_label and actual_label)
            and expected_label == actual_label
        )
        feedback = step.get("explanation", "") if is_correct else f"正确答案是：{expected}。{step.get('explanation', '')}"
    elif step.get("type") == "blank":
        actual = re.sub(r"\s+", "", request.answer.strip().lower())
        accepted = [str(item).strip() for item in step.get("accepted_answers", []) if str(item).strip()]
        expected = str(step.get("answer", "")).strip()
        accepted = accepted or [expected]
        is_correct = any(actual == re.sub(r"\s+", "", item.lower()) for item in accepted)
        feedback = step.get("explanation", "") if is_correct else f"参考答案：{expected}。{step.get('explanation', '')}"
    else:
        expected_points = [str(item).strip() for item in step.get("expected_points", []) if str(item).strip()]
        covered = [point for point in expected_points if point.lower() in request.answer.lower()]
        is_correct = len(covered) >= max(1, len(expected_points) // 2)
        missing = [point for point in expected_points if point not in covered]
        feedback = "回答覆盖了关键点。" if is_correct else f"还可以补充这些要点：{'、'.join(missing[:4])}"

    answers = session.get("answers", {})
    answers[request.step_id] = {
        "answer": request.answer,
        "is_correct": is_correct,
        "feedback": feedback,
        "answered_at": review_now_iso(),
    }
    correct_count = sum(1 for item in answers.values() if item.get("is_correct"))
    scored_steps = [item for item in steps if item.get("type") in {"question", "quiz", "blank"}]
    score = correct_count / max(1, len(scored_steps))
    updated = review_store.update(request.user_id, request.session_id, {"answers": answers, "score": round(score, 2)})
    return {
        "is_correct": is_correct,
        "feedback": feedback,
        "session": updated,
        "correct_count": correct_count,
        "total_count": len(scored_steps),
    }


@app.post("/api/review/complete")
async def complete_review(request: ReviewCompleteRequest, user: AuthUser = Depends(current_user)):
    assert_user_access(request.user_id, user)
    session = review_store.get(request.user_id, request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="复习记录不存在")

    steps = session.get("plan", {}).get("steps", [])
    scored_steps = [item for item in steps if isinstance(item, dict) and item.get("type") in {"question", "quiz", "blank"}]
    answers = session.get("answers", {}) if isinstance(session.get("answers"), dict) else {}
    correct_count = sum(1 for item in answers.values() if isinstance(item, dict) and item.get("is_correct"))
    total_count = len(scored_steps)
    score = correct_count / max(1, total_count)
    current_difficulty = clamp_difficulty(session.get("difficulty") or session.get("plan", {}).get("difficulty"))
    next_difficulty = next_difficulty_from_correct_count(current_difficulty, correct_count)
    result = paper_result_label(correct_count)

    profile = profile_store.load(request.user_id)
    topic = session.get("topic", "未命名主题")
    mastery = profile.get("concept_mastery") if isinstance(profile.get("concept_mastery"), dict) else {}
    current_item = mastery.get(topic, {}) if isinstance(mastery, dict) else {}
    current_weakness = float(current_item.get("score", 0.0) or 0.0) if isinstance(current_item, dict) else 0.0
    session_weakness = float(session.get("weak_score", 0.0) or 0.0)
    is_existing_weak_practice = current_weakness > 0 or session_weakness > 0

    weakness_delta = 0.0
    if request.completed and result == "failed":
        next_weakness = min(1.0, max(WEAKNESS_START_SCORE, current_weakness + 0.2 if is_existing_weak_practice else WEAKNESS_START_SCORE))
        weakness_delta = round(next_weakness - current_weakness, 2)
        profile = set_concept_weakness(profile, topic, next_weakness, "答卷不及格，标记为薄弱知识点")
    elif request.completed and is_existing_weak_practice and result == "excellent":
        next_weakness = max(0.0, current_weakness - 0.2)
        weakness_delta = round(next_weakness - current_weakness, 2)
        profile = set_concept_weakness(profile, topic, next_weakness, "答卷达到优秀，降低薄弱度")
    elif request.completed and is_existing_weak_practice and result == "passed":
        kept_weakness = current_weakness or session_weakness
        profile = set_concept_weakness(profile, topic, kept_weakness, "答卷及格，保持当前薄弱度")

    profile = profile_store.save(request.user_id, profile)
    updated = review_store.update(
        request.user_id,
        request.session_id,
        {
            "status": "completed" if request.completed else "incomplete",
            "completed_at": review_now_iso(),
            "score": round(score, 2),
            "correct_count": correct_count,
            "total_count": total_count,
            "result": result,
            "next_difficulty": next_difficulty,
            "weakness_delta": weakness_delta,
        },
    )
    return {
        "session": updated,
        "profile": profile,
        "weakness_delta": weakness_delta,
        "correct_count": correct_count,
        "total_count": total_count,
        "result": result,
        "next_difficulty": next_difficulty,
    }


@app.post("/api/profile/{user_id}/weakness/update")
async def update_profile_weakness(user_id: str, request: WeaknessUpdateRequest, user: AuthUser = Depends(current_user)):
    assert_user_access(user_id, user)
    profile = profile_store.load(user_id)
    profile = adjust_concept_weakness(profile, request.concept, request.delta, request.reason)
    profile = profile_store.save(user_id, profile)
    return {"profile": profile}

@app.delete("/api/files/{filename}")
async def delete_file(filename: str, user: AuthUser = Depends(current_user)):
    """删除知识库中的指定文件，并只删除该文件关联的向量切片"""
    file_path = safe_data_file(filename, user.id)
    
    try:
        deleted_chunks = delete_file_records(file_path.name, user_id=user.id)
        os.remove(file_path)
        return {
            "message": f"文件 {filename} 删除成功，已删除该文件关联的知识库切片",
            "deleted_chunks": deleted_chunks,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ingest")
async def trigger_ingest(user: AuthUser = Depends(current_user)):
    """触发知识库重建"""
    try:
        ingest_main(data_dir=data_dir_for_user(user.id), user_id=user.id)
        return {"message": "知识库重建成功！"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/query")
async def query_knowledge_base(request: QueryRequest, user: AuthUser = Depends(current_user)):
    """提问并返回答案、关联的分块信息"""
    assert_user_access(request.user_id, user)
    chat_model = (request.chat_model or settings.chat_model).strip()
    if not is_allowed_chat_model(chat_model):
        raise HTTPException(status_code=400, detail=f"不支持的聊天模型：{chat_model}")

    ollama = OllamaClient()
    try:
        ollama.healthcheck()
    except Exception:
        raise HTTPException(status_code=503, detail="Ollama 未启动或不可用")

    # 1. 结合历史记录进行查询重写 (Query Rewriting)
    standalone_query = request.question
    if request.history:
        rewrite_prompt = f"Given the following conversation history and the latest user question, rewrite the latest user question to be a standalone query that can be understood without the conversation history. Do NOT answer the question, just rewrite it.\n\nHistory:\n"
        for msg in request.history:
            rewrite_prompt += f"{msg.role}: {msg.content}\n"
        rewrite_prompt += f"\nLatest question: {request.question}\nStandalone query:"
        
        rewritten = ollama.chat([{"role": "user", "content": rewrite_prompt}], model=chat_model)
        if rewritten and len(rewritten.strip()) > 0:
            standalone_query = rewritten.strip()

    # 2. 提取核心知识点，强化用于向量检索的查询文本
    core_terms = extract_core_terms(ollama, standalone_query, model=chat_model)
    retrieval_query = build_retrieval_query(standalone_query, core_terms)
    query_embedding = ollama.embed([retrieval_query])[0]
    
    # 2.1 双路检索：通用知识库 + 用户私有长期记忆库
    from app.query import candidate_count, diverse_results
    documents: list[str] = []
    metadatas: list[dict] = []
    distances: list[float] = []
    for scope, collection in (
        ("system", get_collection(reset=False)),
        ("personal", get_collection(reset=False, user_id=user.id)),
    ):
        try:
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=candidate_count(settings.top_k),
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            continue
        scope_docs = (result.get("documents") or [[]])[0]
        scope_metas = (result.get("metadatas") or [[]])[0]
        scope_distances = (result.get("distances") or [[]])[0]
        for meta in scope_metas:
            if isinstance(meta, dict):
                meta["kb_scope"] = scope
        documents.extend(scope_docs)
        metadatas.extend(scope_metas)
        distances.extend(scope_distances)

    combined = sorted(zip(documents, metadatas, distances), key=lambda item: item[2])
    documents = [item[0] for item in combined]
    metadatas = [item[1] for item in combined]
    distances = [item[2] for item in combined]
    documents, metadatas, distances = diverse_results(
        documents,
        metadatas,
        distances,
        top_k=settings.top_k,
        neighbor_window=3,
        per_source_limit=2,
    )

    # 2.2 检索用户长期记忆 (Long-term memory)
    user_mem_collection = get_user_memory_collection(request.user_id, reset=False)
    user_mem_docs = []
    all_user_memories = get_all_user_memories(user_mem_collection)
    if user_mem_collection.count() > 0:
        mem_result = user_mem_collection.query(
            query_embeddings=[query_embedding],
            n_results=2, # 取最多2条相关记忆
            include=["documents", "metadatas", "distances"],
        )
        user_mem_docs = (mem_result.get("documents") or [[]])[0]

    if not documents and not user_mem_docs:
        current_profile = profile_store.load(request.user_id)
        return {
            "answer": "知识库中暂无相关文档片段。",
            "chunks": [],
            "followups": default_followups(request.question, core_terms),
            "core_terms": core_terms,
            "learning_insight": None,
            "profile": current_profile,
        }

    # 3. 构造大模型上下文 (整合文档、记忆和历史)
    from app.query import build_context, SYSTEM_PROMPT
    context = build_context(documents, metadatas)
    
    # 补充个人记忆提示
    if user_mem_docs:
        context += "\n\n[User Specific Long-Term Memories]\n" + "\n".join(user_mem_docs)

    # 包含历史的消息链拼接
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # 放入最近对话历史 (短期记忆)
    for msg in request.history:
        messages.append({"role": normalize_chat_role(msg.role), "content": msg.content})
        
    user_prompt = f"Context:\n{context}\n\nQuestion:\n{request.question}"
    messages.append({"role": "user", "content": user_prompt})
    
    answer = ollama.chat(messages=messages, model=chat_model)
    answer_body, followups, extracted_followups = split_answer_and_followups(answer, request.question)
    followups = generate_followups(ollama, request.question, answer_body, core_terms, model=chat_model)
    if len(followups) < 3:
        followups = repair_followups(ollama, request.question, answer_body, core_terms, followups, model=chat_model)
    if len(followups) < 3:
        fallback = default_followups(request.question, core_terms)
        followups.extend(fallback[len(followups):])
    followups = followups[:3]

    # 4. 后台提取并更新本轮长期记忆 (落入 ChromaDB)
    # 用一个极简的 prompt 让 LLM 判断是否有值得长期记住的事实
    extract_prompt = f"Extract a brief single sentence of a persistent user preference, fact or characteristic from the following dialogue, if any. If there is no specific user fact to remember, reply with 'NONE'.\nUser: {request.question}\nAssistant: {answer_body}"
    extracted_mem = ollama.chat([{"role": "user", "content": extract_prompt}], model=chat_model)
    if extracted_mem and "NONE" not in extracted_mem.upper() and len(extracted_mem) > 5:
        import uuid
        mem_embed = ollama.embed([extracted_mem])[0]
        user_mem_collection.add(
            ids=[str(uuid.uuid4())],
            embeddings=[mem_embed],
            documents=[extracted_mem],
            metadatas=[{"source": "conversation_memory"}]
        )

    # 整理反馈给前端的内容块列表
    chunks = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        chunks.append({
            "source": meta.get("source", "unknown"),
            "scope": meta.get("kb_scope", "system"),
            "page": meta.get("page", -1),
            "distance": round(dist, 4),
            "text": doc
        })

    current_profile = profile_store.load(request.user_id)
    learning_insight = analyze_learning_state(
        ollama,
        question=request.question,
        answer=answer_body,
        core_terms=core_terms,
        retrieved_chunks=chunks,
        user_memories=all_user_memories,
        profile=current_profile,
        model=chat_model,
    )
    updated_profile = update_learning_profile(current_profile, learning_insight, question=request.question)
    updated_profile["abstract_evaluation"] = generate_abstract_evaluation(
        ollama,
        profile=updated_profile,
        question=request.question,
        model=chat_model,
    )
    updated_profile = profile_store.save(request.user_id, updated_profile)

    return {
        "answer": answer_body,
        "chunks": chunks,
        "followups": followups,
        "core_terms": core_terms,
        "learning_insight": learning_insight,
        "profile": updated_profile,
    }
