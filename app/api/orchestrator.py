from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    IngestResponse,
    SessionCreateResponse,
    SessionStatusResponse,
)
from app.tools.common import TRANSACTION_STORE, get_logger
from app.tools.ingestion import ingest_financial_documents
from app.tools.insights import financial_insights
from app.tools.transactions import list_seed_transactions, set_ingested_transactions, spending_summary

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["orchestrator"])


def _safe_tool_error(message: str, code: int = 400) -> HTTPException:
    return HTTPException(status_code=code, detail={"error": message, "source": "orchestrator"})


def _ensure_session(session_id: str) -> None:
    if not TRANSACTION_STORE.has_session(session_id):
        raise _safe_tool_error("Unknown session_id. Create a session first.", code=404)


@router.post("/session", response_model=SessionCreateResponse)
def create_session() -> SessionCreateResponse:
    session_id = TRANSACTION_STORE.create_session()
    return SessionCreateResponse(session_id=session_id)


@router.get("/session/{session_id}/status", response_model=SessionStatusResponse)
def session_status(session_id: str) -> SessionStatusResponse:
    _ensure_session(session_id)
    metadata = TRANSACTION_STORE.get_metadata(session_id)
    return SessionStatusResponse(
        session_id=session_id,
        has_data=TRANSACTION_STORE.has_data(session_id),
        source_count=int(metadata.get("sources", 0)),
        warning_count=len(metadata.get("warnings", [])),
    )


@router.post("/documents/ingest", response_model=IngestResponse)
async def ingest_documents(session_id: str, files: list[UploadFile] = File(...)) -> IngestResponse:
    _ensure_session(session_id)
    if not files:
        raise _safe_tool_error("At least one PDF file must be uploaded.")

    temp_paths: list[str] = []
    try:
        for idx, upload in enumerate(files, start=1):
            if not upload.filename or not upload.filename.lower().endswith(".pdf"):
                continue
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(await upload.read())
                temp_paths.append(tmp.name)
            logger.info("Accepted upload #%s for ingestion session=%s", idx, session_id)

        if not temp_paths:
            raise _safe_tool_error("No valid PDF files were provided.")

        result = ingest_financial_documents(file_paths=temp_paths)
        set_ingested_transactions(
            transactions=result["transactions"],
            sources=result["sources"],
            warnings=result["warnings"],
            session_id=session_id,
        )
        return IngestResponse(
            session_id=session_id,
            count=result["count"],
            sources=result["sources"],
            warnings=result["warnings"],
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Document ingestion failed for session=%s", session_id)
        raise _safe_tool_error("Failed to ingest financial documents.", code=500)
    finally:
        for path in temp_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                logger.warning("Temporary file cleanup failed for session=%s", session_id)


def _orchestrate_question(session_id: str, question: str) -> tuple[list[str], dict, str, list[str]]:
    q = question.lower()
    warnings: list[str] = []
    tool_calls: list[str] = []
    supporting_data: dict = {}

    if any(k in q for k in ("summary", "spend", "budget", "category")):
        tool_calls.append("get_spending_summary")
        supporting_data["summary"] = spending_summary(session_id=session_id)

    if any(k in q for k in ("anomaly", "unusual", "spike", "insight", "risk")):
        tool_calls.append("financial_insights")
        supporting_data["insights"] = financial_insights(session_id=session_id)

    if any(k in q for k in ("list", "transaction", "recent")) or not tool_calls:
        tool_calls.append("list_transactions")
        supporting_data["transactions"] = list_seed_transactions(limit=20, session_id=session_id)

    if "insights" in supporting_data:
        insight_lines = supporting_data["insights"].get("insights", [])
        answer = " ".join(insight_lines) if insight_lines else "No major signals found."
    elif "summary" in supporting_data:
        total = supporting_data["summary"].get("total_spend")
        answer = f"Total spending in the selected data is {total} USD."
    else:
        count = supporting_data.get("transactions", {}).get("count", 0)
        answer = f"I found {count} transactions in your ingested documents."

    return tool_calls, supporting_data, answer, warnings


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    _ensure_session(request.session_id)
    if not TRANSACTION_STORE.has_data(request.session_id):
        raise _safe_tool_error(
            "No ingested transactions available. Upload PDFs first.",
            code=400,
        )

    try:
        tool_calls, supporting_data, answer, warnings = _orchestrate_question(
            request.session_id, request.question
        )
        return ChatResponse(
            session_id=request.session_id,
            answer=answer,
            tool_calls=tool_calls,
            supporting_data=supporting_data,
            warnings=warnings,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Chat orchestration failed for session=%s", request.session_id)
        raise _safe_tool_error("Failed to process chat request.", code=500)
