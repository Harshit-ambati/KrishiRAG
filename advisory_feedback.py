import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from advisory_api import advisory_transaction
from advisory_log import latest_run
from evidence_admin import require_admin

Rating = Literal["useful", "unclear", "potentially_incorrect"]
router = APIRouter()


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    rating: Rating


@router.post("/api/advisories/{advisory_id}/feedback")
def save_feedback(advisory_id: UUID, feedback: Feedback):
    with advisory_transaction() as connection:
        run = latest_run(connection, advisory_id, feedback.session_id)
        if not run:
            raise HTTPException(404, detail="advisory_not_found")
        connection.execute("""
            INSERT INTO advisory_feedback (advisory_id, run_id, rating) VALUES (?, ?, ?)
            ON CONFLICT(advisory_id) DO UPDATE SET
                run_id = excluded.run_id, rating = excluded.rating, recorded_at = CURRENT_TIMESTAMP
        """, (str(advisory_id), run["id"], feedback.rating))
    return {"advisory_id": advisory_id, "rating": feedback.rating}


@router.get("/api/admin/advisory-feedback", dependencies=[Depends(require_admin)])
def review_feedback(offset: int = 0):
    with advisory_transaction() as connection:
        rows = connection.execute("""
            SELECT f.rating, f.recorded_at, ar.context, ar.response, ar.provider_model
            FROM advisory_feedback f JOIN advisory_runs ar ON ar.id = f.run_id
            ORDER BY f.recorded_at DESC, f.advisory_id LIMIT 50 OFFSET ?
        """, (max(0, offset),)).fetchall()
    return [{
        "rating": row["rating"], "recorded_at": row["recorded_at"],
        "question": json.loads(row["context"])["question"],
        "response": json.loads(row["response"]), "provider_model": row["provider_model"],
    } for row in rows]
