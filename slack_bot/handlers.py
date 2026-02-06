"""
Slash-command handler for /do-ticket.

Registers the command on a Slack Bolt ``App`` instance and orchestrates the
full lifecycle: validate → accept → progress → result (or error).
"""

import os
import re
import threading
import time

from slack_bolt import App

from code_agent.workflow import process_slack_ticket
from .messages import (
    accepted_blocks,
    in_progress_blocks,
    completed_blocks,
    error_blocks,
)

_TICKET_RE = re.compile(r"^[A-Za-z]+-\d+$")
_URL_RE = re.compile(r"^https?://")

# Default repo URL — override with the REPO_URL env var
_DEFAULT_REPO_URL = "https://github.com/org/repo.git"


def register(app: App) -> None:
    """Register the /do-ticket slash command on *app*."""

    @app.command("/do-ticket")
    def handle_do_ticket(ack, command, client, logger):
        # --- 1. Parse & validate -------------------------------------------
        raw_text = (command.get("text") or "").strip()
        parts = raw_text.split()
        
        # Must have at least a ticket key
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
        response_url = command["response_url"]  # Use response URL to reply

        # Acknowledge immediately (Slack requires < 3 s)
        ack(f":thumbsup:  Got it — working on *{ticket_key}* with repo `{repo_url}`…")

        # --- 2. Kick off async processing in a background thread -----------
        threading.Thread(
            target=_process_in_background,
            args=(client, logger, response_url, user_id, username, ticket_key, repo_url),
            daemon=True,
        ).start()

    # Also handle the button action so Slack doesn't complain
    @app.action("open_pr_link")
    def handle_open_pr(_ack, _body):
        _ack()


def _process_in_background(client, logger, response_url, user_id, username, ticket_key, repo_url):
    """Run the ticket processing and post updates via response_url."""
    import requests
    
    def send_response(text, blocks=None):
        """Send a message using the Slack response URL."""
        payload = {"text": text, "response_type": "in_channel"}
        if blocks:
            payload["blocks"] = blocks
        requests.post(response_url, json=payload, timeout=10)
    
    try:
        # --- Post "in progress" message -----------------------------------
        send_response(
            f"<@{user_id}> Working on *{ticket_key}*… :hourglass_flowing_sand:",
        )

        # --- Call the real backend -----------------------------------------
        start = time.monotonic()
        logger.info("Starting workflow for %s with repo %s", ticket_key, repo_url)
        
        # Call the real workflow function
        pr_url = process_slack_ticket(ticket_key, repo_url, username)
        elapsed = time.monotonic() - start

        # --- Post final result --------------------------------------------
        send_response(
            f"<@{user_id}> :white_check_mark: *Done!* PR for *{ticket_key}* created in {elapsed:.1f}s\n\n"
            f":link: <{pr_url}|View Pull Request>",
        )
        logger.info("Completed %s in %.1fs - PR: %s", ticket_key, elapsed, pr_url)

    except Exception as e:
        logger.exception("Error processing ticket %s", ticket_key)
        # Best-effort error message
        try:
            send_response(
                f"<@{user_id}> :x: *Failed* to process *{ticket_key}*\n\nError: {e}",
            )
        except Exception:
            logger.exception("Could not send error message for %s", ticket_key)
