from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.agent.run import run_langgraph_chat
from app.api.schemas import (
    ChatResponse,
    SessionCreateResponse,
    SessionStatusResponse,
)
from app.tools.common import TRANSACTION_STORE, get_logger

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


@router.post("/chat", response_model=ChatResponse)
async def chat(
    session_id: str = Form(...),
    question: str | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
) -> ChatResponse:
    _ensure_session(session_id)
    temp_paths: list[str] = []

    try:
        for idx, upload in enumerate(files or [], start=1):
            if not upload.filename or not upload.filename.lower().endswith(".pdf"):
                continue
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(await upload.read())
                temp_paths.append(tmp.name)
            logger.info("Accepted chat upload #%s for session=%s", idx, session_id)

        result = run_langgraph_chat(
            session_id=session_id,
            question=question,
            attachment_paths=temp_paths,
        )
        if result.get("status") == "error":
            raise _safe_tool_error(
                result.get("error_message") or "Failed to process chat request.",
                code=500,
            )

        return ChatResponse(
            session_id=session_id,
            status=result["status"],
            answer=result["answer"],
            tool_calls=result["tool_calls"],
            supporting_data=result["supporting_data"],
            warnings=result["warnings"],
            missing_input=result.get("missing_input"),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Chat orchestration failed for session=%s", session_id)
        raise _safe_tool_error("Failed to process chat request.", code=500)
    finally:
        for path in temp_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                logger.warning("Temporary file cleanup failed for session=%s", session_id)
