"""FastAPI gateway exposing Jira-to-PR workflow endpoints."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import process_slack_ticket

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Jira2PR Gateway",
    version="1.0.0",
    description="API gateway to fetch Jira tickets, apply AI changes, and open PRs.",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TicketRequest(BaseModel):
    ticket_key: str = Field(..., min_length=3, description="Jira ticket key, e.g. PROJ-123")
    repo_url: str = Field(..., description="GitHub repository URL (SSH or HTTPS).")
    slack_username: str = Field(..., min_length=1, description="Slack user who invoked the command.")


class TicketResponse(BaseModel):
    pr_url: str


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=dict)
async def health() -> dict[str, str]:
    """Simple health check for liveness probes."""
    return {"status": "ok"}


@app.post(
    "/tickets/process",
    response_model=TicketResponse,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
async def process_ticket(payload: TicketRequest) -> Any:
    """Process a Jira ticket and return the generated PR URL."""
    try:
        pr_url = await run_in_threadpool(
            process_slack_ticket,
            payload.ticket_key,
            payload.repo_url,
            payload.slack_username,
        )
        return TicketResponse(pr_url=pr_url)
    except requests.HTTPError as exc:
        logger.exception("Jira request failed: %s", exc)
        status_code = 400 if exc.response is not None and exc.response.status_code < 500 else 502
        raise HTTPException(status_code=status_code, detail="Failed to fetch Jira ticket") from exc
    except Exception as exc:
        logger.exception("Ticket processing failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to process ticket") from exc


__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("code_agent.server:app", host="0.0.0.0", port=port, reload=True)
