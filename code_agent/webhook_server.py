"""Minimal FastAPI server to handle GitHub webhook comments for follow-up runs."""

from __future__ import annotations

import os
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from . import process_pr_comment

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Jira2PR Webhook Server",
    version="1.0.0",
    description="Receives GitHub comment webhooks and triggers follow-up AI changes.",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/github", status_code=202)
async def github_webhook(request: Request) -> dict[str, Any]:
    """Handle GitHub webhook events for PR comments to trigger follow-ups."""
    event_type = request.headers.get("X-GitHub-Event")
    if not event_type:
        raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

    payload = await request.json()

    if event_type not in {"issue_comment", "pull_request_review_comment"}:
        raise HTTPException(status_code=400, detail="Unsupported GitHub event type")

    try:
        result = await run_in_threadpool(process_pr_comment, payload)
        return {"status": "accepted", "detail": result}
    except ValueError as exc:
        return {"status": "ignored", "detail": str(exc)}
    except Exception as exc:  # pragma: no cover - catch-all for webhook errors
        logger.exception("GitHub webhook handling failed: %s", exc)
        raise HTTPException(status_code=500, detail="Webhook handling failed") from exc


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("code_agent.webhook_server:app", host="0.0.0.0", port=port, reload=True)
