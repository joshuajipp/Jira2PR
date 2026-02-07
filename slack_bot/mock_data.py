"""
Mock backend for ticket processing.

Provides both a simple ``process_ticket()`` for basic testing and a
``simulate_pipeline()`` that walks through every pipeline step with
delays and progress callbacks -- used when ``MOCK_MODE=1``.
"""

import time
from typing import Callable


# ---------------------------------------------------------------------------
# Simple mock (legacy)
# ---------------------------------------------------------------------------

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
    """
    time.sleep(_SIMULATED_DELAY)

    ticket_key = request["ticket_key"]
    repo_url = request["repo_url"]
    slug = repo_url.rstrip(".git").rsplit("/", 2)[-2:]
    repo_slug = "/".join(slug)

    return {
        "ticket_key": ticket_key,
        "repo_url": repo_url,
        "slack_username": request["slack_username"],
        "pr_url": f"https://github.com/{repo_slug}/pull/42",
        "branch": f"feature/{ticket_key.lower()}-add-auth",
        "title": "Add authentication middleware",
        "files_changed": 5,
        "additions": 120,
        "deletions": 15,
        "status": "success",
    }


# ---------------------------------------------------------------------------
# Full pipeline simulator (for MOCK_MODE=1)
# ---------------------------------------------------------------------------

# Simulated agent iteration count
_MOCK_AGENT_ITERATIONS = 25

# Fake tool calls emitted during the AI step
_FAKE_TOOL_CALLS = [
    ("list_directory", '{"path": "."}'),
    ("read_file", '{"path": "src/main.py"}'),
    ("read_file", '{"path": "src/config.py"}'),
    ("read_file", '{"path": "src/routes/auth.py"}'),
    ("write_file", '{"path": "src/middleware/jwt.py"}'),
    ("read_file", '{"path": "tests/test_auth.py"}'),
    ("write_file", '{"path": "src/middleware/roles.py"}'),
    ("write_file", '{"path": "tests/test_jwt.py"}'),
    ("read_file", '{"path": "src/routes/api.py"}'),
    ("write_file", '{"path": "src/routes/api.py"}'),
    ("write_file", '{"path": "docs/api.md"}'),
]


def simulate_pipeline(
    ticket_key: str,
    repo_url: str,
    username: str,
    on_step: Callable[[int], None],
    on_agent_progress: Callable[[int, int], None],
    on_tool_call: Callable[[str, str], None] | None = None,
) -> dict:
    """Walk through the full pipeline with simulated delays.

    Calls ``on_step(step_index)`` when a step becomes active,
    ``on_agent_progress(current, total)`` during the AI step, and
    ``on_tool_call(tool_name, args_preview)`` for each simulated tool call.

    Returns a mock result dict suitable for ``completed_blocks()``.
    """
    slug = repo_url.rstrip(".git").rsplit("/", 2)[-2:]
    repo_slug = "/".join(slug)

    # Step 0: Fetch Jira ticket
    on_step(0)
    time.sleep(0.8)

    # Step 1: Clone repo
    on_step(1)
    time.sleep(1.2)

    # Step 2: AI analyzing (with progress + tool call logs)
    on_step(2)
    tool_idx = 0
    for i in range(1, _MOCK_AGENT_ITERATIONS + 1):
        on_agent_progress(i, _MOCK_AGENT_ITERATIONS)

        # Emit a fake tool call every ~2 iterations
        if on_tool_call and tool_idx < len(_FAKE_TOOL_CALLS) and i % 2 == 0:
            name, args = _FAKE_TOOL_CALLS[tool_idx]
            on_tool_call(name, args)
            tool_idx += 1

        time.sleep(0.3)

    # Step 3: Creating branch
    on_step(3)
    time.sleep(0.4)

    # Step 4: Staging changes
    on_step(4)
    time.sleep(0.3)

    # Step 5: Committing
    on_step(5)
    time.sleep(0.5)

    # Step 6: Creating pull request
    on_step(6)
    time.sleep(0.8)

    return {
        "ticket_key": ticket_key,
        "pr_url": f"https://github.com/{repo_slug}/pull/42",
        "branch": f"ai/{ticket_key.lower()}",
        "repo_url": repo_url,
        "repo_display": repo_slug,
        "title": f"[{ticket_key}] Add authentication middleware",
        "files_changed": 5,
        "additions": 120,
        "deletions": 15,
        "status": "success",
    }
