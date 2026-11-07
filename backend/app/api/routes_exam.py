from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas import ExamResult, ExamSession, ExamStartRequest, ExamSubmitRequest
from app.services.exam import ExamError, start_exam, submit_exam

router = APIRouter(prefix="/exam", tags=["exam"])


@router.post("/start", response_model=ExamSession)
def start(
    payload: ExamStartRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return start_exam(
            db,
            user,
            skill_ids=payload.skill_ids,
            count=payload.count,
            duration_minutes=payload.duration_minutes,
        )
    except ExamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/submit", response_model=ExamResult)
def submit(
    payload: ExamSubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return submit_exam(
            db,
            user,
            session_id=payload.session_id,
            answers=[item.model_dump() for item in payload.answers],
        )
    except ExamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
