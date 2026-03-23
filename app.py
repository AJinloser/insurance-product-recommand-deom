"""Minimal web frontend for the Insurance Recommendation Demo."""

from __future__ import annotations

import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from src import InsuranceRecommendationAgent, Settings, RecommendationInput, UserProfile
from src.database.connection import DatabaseConnection
from src.database.repository import ProductRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = Settings.from_env()

CHAT_SYSTEM_PROMPT = (
    "你是一位专业的保险顾问助手。请用简洁、清晰的中文回答用户关于保险的问题。"
    "回答控制在200字以内，不要使用markdown格式。"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing application resources")

    agent = InsuranceRecommendationAgent(settings)
    agent.load_data()

    db = DatabaseConnection(settings.db_path)
    repo = ProductRepository(db)

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        temperature=0.7,
        **({"base_url": settings.llm_base_url} if settings.llm_base_url else {}),
    )

    app.state.agent = agent
    app.state.repo = repo
    app.state.llm = llm

    try:
        yield
    finally:
        logger.info("Closing application resources")
        agent.close()
        db.close()


app = FastAPI(title="Insurance Recommendation Demo", lifespan=lifespan)


def _app_state() -> tuple[InsuranceRecommendationAgent, ProductRepository, ChatOpenAI]:
    return app.state.agent, app.state.repo, app.state.llm


# ── Request / Response models ────────────────────────────────────
class ChatRequest(BaseModel):
    messages: list[dict[str, str]]  # [{"role": "user"/"assistant", "content": "..."}]
    system_extra: str = ""  # extra context injected into system prompt


class ChatResponse(BaseModel):
    reply: str


class RecommendRequest(BaseModel):
    messages: list[dict[str, str]]


class RecommendResponse(BaseModel):
    status: str
    recommendations: list[dict]  # [{product_name, recommendation_reason, fields_by_group}]
    error_message: str | None = None


# ── API endpoints ────────────────────────────────────────────────
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    _, _, llm = _app_state()
    system_prompt = CHAT_SYSTEM_PROMPT
    if req.system_extra:
        system_prompt += "\n\n以下是已推荐给用户的保险产品信息，用户可能会就此进行提问：\n" + req.system_extra

    lc_messages = [SystemMessage(content=system_prompt)]
    for m in req.messages:
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        else:
            lc_messages.append(AIMessage(content=m["content"]))

    resp = llm.invoke(lc_messages)
    return ChatResponse(reply=resp.content)


@app.post("/api/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    agent, repo, _ = _app_state()
    # Build query from last user message; full history as dialogue_history
    if not req.messages:
        return RecommendResponse(status="failed", recommendations=[], error_message="没有对话记录")

    query = ""
    dialogue_history: list[dict[str, str]] = []
    for m in req.messages:
        if m["role"] == "user":
            query = m["content"]
        dialogue_history.append({"role": m["role"], "content": m["content"]})

    input_data = RecommendationInput(
        dialogue_history=dialogue_history,
        query=query,
        user_profile=UserProfile(),
    )
    result = agent.recommend(input_data)

    recs = []
    for r in result.recommendations:
        # Fetch all field values for this product, grouped by field_group
        all_values = repo.get_product_all_values(r.product_id)
        fields_by_group: dict[str, list[dict[str, str]]] = {}
        for v in all_values:
            display = v["value_text"] or ""
            if not display and v["value_numeric"] is not None:
                display = str(v["value_numeric"])
            if not display and v["value_boolean"] is not None:
                display = "是" if v["value_boolean"] else "否"
            if not display:
                continue
            group = v["field_group"] or "其他"
            fields_by_group.setdefault(group, []).append({
                "name": v["field_name"],
                "value": display,
            })
        recs.append({
            "product_name": r.product_name,
            "recommendation_reason": r.recommendation_reason,
            "fields_by_group": fields_by_group,
        })

    return RecommendResponse(
        status=result.status,
        recommendations=recs,
        error_message=result.error_message,
    )


# ── Serve frontend ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    return (Path(__file__).parent / "frontend.html").read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict[str, Any]:
    repo = app.state.repo
    product_count = len(repo.get_all_products())
    return {
        "status": "ok",
        "product_count": product_count,
        "db_path": str(settings.db_path),
    }
