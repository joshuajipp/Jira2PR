"""
Slash-command handler for /do-ticket.

Registers the command on a Slack Bolt ``App`` instance and orchestrates the
full lifecycle: validate -> accept -> progress (with live updates) -> result.

Uses DM + chat_update for unlimited real-time progress updates (response_url
is limited to 5 calls within 30 min).
"""

import os
import re
import tempfile
import threading
import time
from pathlib import Path

from slack_bolt import App

from .messages import (
    pipeline_blocks,
    completed_blocks,
    error_blocks,
)

_TICKET_RE = re.compile(r"^[A-Za-z]+-\d+$")
_URL_RE = re.compile(r"^https?://")

# Default repo URL — override with the REPO_URL env var
_DEFAULT_REPO_URL = "https://github.com/org/repo.git"

# ---------------------------------------------------------------------------
# Pipeline step definitions
# ---------------------------------------------------------------------------

STEP_NAMES = [
    "Fetching Jira ticket",
    "Cloning repository",
    "AI analyzing code",
    "Creating branch",
    "Staging changes",
    "Committing",
    "Creating pull request",
]

_AI_STEP_INDEX = 2  # index of "AI analyzing code" in STEP_NAMES


def _make_steps(active_index: int, error_index: int | None = None) -> list[dict]:
    """Build the steps list with correct states for each step."""
    steps = []
    for i, name in enumerate(STEP_NAMES):
        if error_index is not None and i == error_index:
            state = "error"
        elif i < active_index:
            state = "done"
        elif i == active_index:
            state = "active"
        else:
            state = "pending"
        steps.append({"name": name, "state": state})
    return steps


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(app: App) -> None:
    """Register the /do-ticket slash command on *app*."""

    @app.command("/do-ticket")
    def handle_do_ticket(ack, command, client, logger):
        # --- 1. Parse & validate -------------------------------------------
        raw_text = (command.get("text") or "").strip()
        parts = raw_text.split()

        if not parts or not _TICKET_RE.match(parts[0]):
            ack(
                response_type="ephemeral",
                text=(
                    ":warning:  Please provide a valid ticket key, e.g.\n"
                    "`/do-ticket PROJ-123`\n"
                    "`/do-ticket PROJ-123 https://github.com/owner/repo`"
                ),
            )
            return

        ticket_key = parts[0].upper()

        # Check for optional repo URL (second argument)
        if len(parts) >= 2 and _URL_RE.match(parts[1]):
            repo_url = parts[1]
        else:
            repo_url = os.environ.get("REPO_URL", _DEFAULT_REPO_URL)

        user_id = command["user_id"]
        username = command.get("user_name", "unknown")

        # Acknowledge immediately (Slack requires < 3 s)
        ack(f":thumbsup:  Got it — working on *{ticket_key}*…")

        # --- 2. Kick off async processing in a background thread -----------
        threading.Thread(
            target=_process_in_background,
            args=(client, logger, user_id, username, ticket_key, repo_url),
            daemon=True,
        ).start()

    # Handle the "View PR" button action so Slack doesn't complain
    @app.action("open_pr_link")
    def handle_open_pr(ack, body):
        ack()


# ---------------------------------------------------------------------------
# Background processing — step-by-step with live Slack updates
# ---------------------------------------------------------------------------

def _process_in_background(client, logger, user_id, username, ticket_key, repo_url):
    """Orchestrate the full pipeline with live Slack DM updates."""

    mock_mode = os.environ.get("MOCK_MODE", "").strip() == "1"

    # Open DM channel with the user
    dm = client.conversations_open(users=[user_id])
    channel = dm["channel"]["id"]

    # Rolling log lines (shared mutable list)
    log_lines: list[str] = []

    # Post initial message with all steps pending
    result = client.chat_postMessage(
        channel=channel,
        text=f"Working on {ticket_key}…",
        blocks=pipeline_blocks(ticket_key, username, _make_steps(-1)),
    )
    ts = result["ts"]

    def update(step_index, progress=None, error_index=None):
        """Update the DM message with the current pipeline state."""
        steps = _make_steps(step_index, error_index=error_index)
        try:
            client.chat_update(
                channel=channel,
                ts=ts,
                text=f"Working on {ticket_key}…",
                blocks=pipeline_blocks(
                    ticket_key, username, steps,
                    progress=progress,
                    log_lines=log_lines,
                ),
            )
        except Exception:
            logger.warning("Failed to update Slack message", exc_info=True)

    if mock_mode:
        _run_mock_pipeline(client, logger, channel, ts, ticket_key, username, repo_url, update, log_lines)
    else:
        _run_real_pipeline(client, logger, channel, ts, ticket_key, username, repo_url, update, log_lines)


# ---------------------------------------------------------------------------
# Real pipeline — calls code_agent functions directly
# ---------------------------------------------------------------------------

def _run_real_pipeline(client, logger, channel, ts, ticket_key, username, repo_url, update, log_lines):
    """Execute the real workflow with per-step Slack updates."""
    from code_agent.workflow import fetch_jira_ticket, _clone_repo, _parse_github_repo
    from code_agent.agent import run_agent
    from code_agent.git_ops import (
        _run_git,
        _ensure_authenticated_remote,
        create_pull_request,
    )
    from code_agent.config import BRANCH_PREFIX, BASE_BRANCH

    start = time.monotonic()

    try:
        github_token = os.environ.get("GITHUB_TOKEN")
        if not github_token:
            raise RuntimeError("GITHUB_TOKEN environment variable is required.")

        repo_owner, repo_name = _parse_github_repo(repo_url)

        # --- Step 0: Fetch Jira ticket ------------------------------------
        update(0)
        jira_ticket = fetch_jira_ticket(ticket_key)
        jira_ticket["requested_by"] = username
        ticket_summary = jira_ticket.get("summary", "AI-generated changes")

        # --- Step 1: Clone repository -------------------------------------
        update(1)
        tmpdir = tempfile.mkdtemp(prefix="jira2pr-")
        repo_path = Path(tmpdir) / "repo"
        _clone_repo(repo_url, repo_path, github_token=github_token)

        # --- Step 2: AI analyzing code (with progress bar + logs) ---------
        update(2)

        _last_update_time = [0.0]  # mutable for closure
        _last_progress = [{"current": 0, "total": 1}]  # track latest progress

        def on_agent_progress(iteration, total):
            _last_progress[0] = {"current": iteration, "total": total}
            # Rate-limit Slack updates to at most once per 2 seconds
            now = time.monotonic()
            if now - _last_update_time[0] >= 2.0:
                _last_update_time[0] = now
                update(2, progress=_last_progress[0])

        def on_tool_call(tool_name, args_preview):
            log_lines.append(f"{tool_name}({args_preview})")
            # Rate-limit updates, always keep progress bar visible
            now = time.monotonic()
            if now - _last_update_time[0] >= 1.5:
                _last_update_time[0] = now
                update(2, progress=_last_progress[0])

        change_summary, files_changed = run_agent(
            jira_ticket,
            str(repo_path),
            on_progress=on_agent_progress,
            on_tool_call=on_tool_call,
        )

        # --- Step 3: Creating branch --------------------------------------
        log_lines.clear()
        update(3)
        branch_name = f"{BRANCH_PREFIX}/{ticket_key.lower().replace(' ', '-')}"
        commit_message = f"[{ticket_key}] {ticket_summary}"
        _run_git(str(repo_path), "checkout", "-b", branch_name)

        # --- Step 4: Staging changes --------------------------------------
        update(4)
        _run_git(str(repo_path), "add", ".")

        # --- Step 5: Committing -------------------------------------------
        update(5)
        _run_git(str(repo_path), "commit", "-m", commit_message)
        _ensure_authenticated_remote(str(repo_path), github_token, repo_owner, repo_name)
        _run_git(str(repo_path), "push", "origin", branch_name)

        # --- Step 6: Creating pull request --------------------------------
        update(6)
        from github import Github

        files_list = (
            "\n".join(f"- `{f}`" for f in files_changed)
            if files_changed
            else "- (none tracked)"
        )
        pr_body = (
            f"## AI-Generated Changes for {ticket_key}\n\n"
            f"**Jira Ticket:** {ticket_key} — {ticket_summary}\n\n"
            f"### Summary of Changes\n\n"
            f"{change_summary}\n\n"
            f"### Files Changed\n\n"
            f"{files_list}\n\n"
            f"---\n"
            f"*This PR was automatically generated by the Bedrock Code Agent.*"
        )

        gh = Github(github_token)
        repo = gh.get_repo(f"{repo_owner}/{repo_name}")
        pr = repo.create_pull(
            title=commit_message,
            body=pr_body,
            head=branch_name,
            base=BASE_BRANCH,
        )
        pr_url = pr.html_url

        elapsed = time.monotonic() - start

        # Deduplicate files_changed list
        unique_files = list(dict.fromkeys(files_changed))

        # --- Final: rich boxed PR card ------------------------------------
        pr_data = {
            "ticket_key": ticket_key,
            "pr_url": pr_url,
            "branch": branch_name,
            "repo_url": repo_url,
            "repo_display": f"{repo_owner}/{repo_name}",
            "title": commit_message,
            "files_changed": len(unique_files),
            "additions": pr.additions if hasattr(pr, "additions") else 0,
            "deletions": pr.deletions if hasattr(pr, "deletions") else 0,
        }

        done = completed_blocks(pr_data, elapsed)
        client.chat_update(
            channel=channel,
            ts=ts,
            text=f"Done! PR for {ticket_key}: {pr_url}",
            blocks=done["blocks"],
            attachments=done["attachments"],
        )
        logger.info("Completed %s in %.1fs - PR: %s", ticket_key, elapsed, pr_url)

    except Exception as e:
        logger.exception("Error processing ticket %s", ticket_key)
        try:
            client.chat_update(
                channel=channel,
                ts=ts,
                text=f"Failed to process {ticket_key}",
                blocks=error_blocks(ticket_key, str(e)),
            )
        except Exception:
            logger.exception("Could not send error message for %s", ticket_key)


# ---------------------------------------------------------------------------
# Mock pipeline — simulates the full flow with delays
# ---------------------------------------------------------------------------

def _run_mock_pipeline(client, logger, channel, ts, ticket_key, username, repo_url, update, log_lines):
    """Simulate the pipeline with delays for demo/testing."""
    from .mock_data import simulate_pipeline

    start = time.monotonic()

    try:
        def on_tool_call(tool_name, args_preview):
            log_lines.append(f"{tool_name}({args_preview})")

        result = simulate_pipeline(
            ticket_key=ticket_key,
            repo_url=repo_url,
            username=username,
            on_step=lambda step_idx: update(step_idx),
            on_agent_progress=lambda cur, total: update(
                _AI_STEP_INDEX, progress={"current": cur, "total": total}
            ),
            on_tool_call=on_tool_call,
        )

        elapsed = time.monotonic() - start

        done = completed_blocks(result, elapsed)
        client.chat_update(
            channel=channel,
            ts=ts,
            text=f"Done! PR for {ticket_key}: {result['pr_url']}",
            blocks=done["blocks"],
            attachments=done["attachments"],
        )
        logger.info("Mock completed %s in %.1fs", ticket_key, elapsed)

    except Exception as e:
        logger.exception("Error in mock pipeline for %s", ticket_key)
        try:
            client.chat_update(
                channel=channel,
                ts=ts,
                text=f"Failed to process {ticket_key}",
                blocks=error_blocks(ticket_key, str(e)),
            )
        except Exception:
            logger.exception("Could not send mock error for %s", ticket_key)
