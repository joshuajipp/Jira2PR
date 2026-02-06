"""
Mock backend for ticket processing.

Mirrors the request/response contract of the future FastAPI backend.
Swap `process_ticket` for an `httpx.post()` call when the real backend is ready.
"""

import time

# Simulated processing delay in seconds
_SIMULATED_DELAY = 3


def process_ticket(request: dict) -> dict:
    """Process a ticket and return mock PR data.

    Parameters
    ----------
    request : dict
        {
            "ticket_key":     "PROJ-123",
            "repo_url":       "https://github.com/org/repo.git",
            "slack_username":  "alice",
        }

    Returns
    -------
    dict
        Mock response matching the future FastAPI response schema.
    """
    time.sleep(_SIMULATED_DELAY)

    ticket_key = request["ticket_key"]
    repo_url = request["repo_url"]
    slug = repo_url.rstrip(".git").rsplit("/", 2)[-2:]  # ["org", "repo"]
    repo_slug = "/".join(slug)

    return {
        "ticket_key": ticket_key,
        "repo_url": repo_url,
        "slack_username": request["slack_username"],
        "pr_url": f"https://github.com/{repo_slug}/pull/42",
        "branch": f"feature/{ticket_key.lower()}-add-auth",
        "title": "Add authentication middleware",
        "summary": (
            "Added JWT-based auth middleware with role-based access control. "
            "Integrated token validation, added unit tests, and updated API docs."
        ),
        "files_changed": 5,
        "additions": 120,
        "deletions": 15,
        "status": "success",
    }
