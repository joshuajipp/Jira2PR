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

from .mock_data import process_ticket
from .messages import (
    accepted_blocks,
    in_progress_blocks,
    completed_blocks,
    error_blocks,
)

_TICKET_RE = re.compile(r"^[A-Za-z]+-\d+$")

# Default repo URL — override with the REPO_URL env var
_DEFAULT_REPO_URL = "https://github.com/org/repo.git"


def register(app: App) -> None:
    """Register the /do-ticket slash command on *app*."""

    @app.command("/do-ticket")
    def handle_do_ticket(ack, command, client, logger):
        # --- 1. Parse & validate -------------------------------------------
        raw_text = (command.get("text") or "").strip()
        if not raw_text or not _TICKET_RE.match(raw_text):
            ack(
                response_type="ephemeral",
                text=(
                    ":warning:  Please provide a valid ticket key, e.g. `/do-ticket PROJ-123`"
                ),
            )
            return

        ticket_key = raw_text.upper()
        user_id = command["user_id"]
        username = command.get("user_name", "unknown")

        # Acknowledge immediately (Slack requires < 3 s)
        ack(f":thumbsup:  Got it — working on *{ticket_key}*…")

        # --- 2. Kick off async processing in a background thread -----------
        threading.Thread(
            target=_process_in_background,
            args=(client, logger, user_id, username, ticket_key),
            daemon=True,
        ).start()

    # Also handle the button action so Slack doesn't complain
    @app.action("open_pr_link")
    def handle_open_pr(_ack, _body):
        _ack()


def _process_in_background(client, logger, user_id, username, ticket_key):
    """Run the (mock) ticket processing and post updates to the user's DM."""
    try:
        # Open / fetch the DM channel with the user
        dm = client.conversations_open(users=[user_id])
        channel = dm["channel"]["id"]

        # --- Post "accepted" message --------------------------------------
        result = client.chat_postMessage(
            channel=channel,
            text=f"Working on {ticket_key}…",
            blocks=accepted_blocks(ticket_key),
        )
        ts = result["ts"]

        # Short pause then update to "in progress"
        time.sleep(1)
        client.chat_update(
            channel=channel,
            ts=ts,
            text=f"In progress: {ticket_key}",
            blocks=in_progress_blocks(ticket_key, "Cloning repo & running agent"),
        )

        # --- Call the (mock) backend --------------------------------------
        repo_url = os.environ.get("REPO_URL", _DEFAULT_REPO_URL)
        request_payload = {
            "ticket_key": ticket_key,
            "repo_url": repo_url,
            "slack_username": username,
        }

        start = time.monotonic()
        response = process_ticket(request_payload)
        elapsed = time.monotonic() - start

        # --- Post final result --------------------------------------------
        if response.get("status") == "success":
            client.chat_update(
                channel=channel,
                ts=ts,
                text=f"Done! PR for {ticket_key}: {response['pr_url']}",
                blocks=completed_blocks(response, elapsed),
            )
        else:
            client.chat_update(
                channel=channel,
                ts=ts,
                text=f"Failed to process {ticket_key}",
                blocks=error_blocks(
                    ticket_key,
                    response.get("error", "Unknown error from backend."),
                ),
            )

    except Exception:
        logger.exception("Error processing ticket %s", ticket_key)
        # Best-effort error message
        try:
            client.chat_update(
                channel=channel,
                ts=ts,
                text=f"Failed to process {ticket_key}",
                blocks=error_blocks(ticket_key, "An unexpected error occurred."),
            )
        except Exception:
            logger.exception("Could not send error message for %s", ticket_key)
