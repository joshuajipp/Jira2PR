"""
Slack Block Kit message builders for /do-ticket responses.

Each function returns Block Kit structures that can be passed
directly to Slack API calls.
"""

import datetime
import math


# ---------------------------------------------------------------------------
# Step state icons
# ---------------------------------------------------------------------------

_ICONS = {
    "pending": ":white_circle:",
    "active": ":gear:",
    "done": ":white_check_mark:",
    "error": ":x:",
}

# Progress bar characters
_BAR_FILLED = "\u2588"   # █
_BAR_EMPTY = "\u2591"    # ░
_BAR_WIDTH = 20

# Maximum number of rolling log lines to display
_MAX_LOG_LINES = 6


# ---------------------------------------------------------------------------
# Pipeline – real-time updating message showing all steps
# ---------------------------------------------------------------------------

def pipeline_blocks(
    ticket_key: str,
    username: str,
    steps: list[dict],
    progress: dict | None = None,
    log_lines: list[str] | None = None,
) -> list[dict]:
    """Build a pipeline progress message.

    Parameters
    ----------
    ticket_key : str
        The Jira ticket key (e.g. ``"PROJ-123"``).
    username : str
        Slack username of the requester.
    steps : list[dict]
        List of ``{"name": "...", "state": "pending|active|done|error"}``.
    progress : dict | None
        Optional ``{"current": 12, "total": 60}`` for the AI step progress bar.
    log_lines : list[str] | None
        Optional rolling list of tool-call log entries to display greyed-out.
    """
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d, %Y %H:%M UTC")

    # Build the step lines
    step_lines = []
    for step in steps:
        icon = _ICONS.get(step["state"], ":white_circle:")
        step_lines.append(f"{icon}  {step['name']}")

        # Insert progress bar below the active AI step
        if step["state"] == "active" and progress is not None:
            bar = _render_progress_bar(progress["current"], progress["total"])
            step_lines.append(f"      {bar}")

    steps_text = "\n".join(step_lines)

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":ticket:  {ticket_key}",
                "emoji": True,
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Requested by *@{username}*  |  {now}",
                },
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": steps_text,
            },
        },
    ]

    # Append rolling log lines (greyed-out context block)
    if log_lines:
        tail = log_lines[-_MAX_LOG_LINES:]
        log_text = "\n".join(f"› `{line}`" for line in tail)
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": log_text},
                ],
            }
        )

    return blocks


# ---------------------------------------------------------------------------
# Completed – rich boxed PR card (using attachments for left-border box)
# ---------------------------------------------------------------------------

def completed_blocks(data: dict, elapsed_seconds: float) -> dict:
    """Final success message with a boxed PR card.

    Returns a dict with ``"blocks"`` (header) and ``"attachments"``
    (the PR details rendered inside a green left-border box).

    Parameters
    ----------
    data : dict
        Must contain: ticket_key, pr_url, branch, repo_url,
        files_changed, additions, deletions, title.
    elapsed_seconds : float
        Wall-clock time the processing took.
    """
    elapsed = _format_elapsed(elapsed_seconds)
    pr_number = data["pr_url"].rsplit("/", 1)[-1]

    # Build a short repo display name
    repo_display = data.get("repo_display", data.get("repo_url", ""))
    if len(repo_display) > 40:
        repo_display = "..." + repo_display[-37:]

    files_changed = data.get("files_changed", 0)
    additions = data.get("additions", 0)
    deletions = data.get("deletions", 0)

    # Top-level blocks (header only)
    header_blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":white_check_mark:  {data['ticket_key']}  —  Done!",
                "emoji": True,
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":stopwatch:  Completed in {elapsed}",
                },
            ],
        },
    ]

    # Attachment blocks (inside the green box)
    pr_card_blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*<{data['pr_url']}|{data.get('title', data['ticket_key'])}>*\n"
                    f"#{pr_number}  opened by ai-agent"
                ),
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": ":link:  View PR",
                    "emoji": True,
                },
                "url": data["pr_url"],
                "action_id": "open_pr_link",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Repo*\n{repo_display}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Branch*\n`{data['branch']}`",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Files changed*\n{files_changed}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Diff*\n`+{additions}`  `−{deletions}`",
                },
            ],
        },
    ]

    return {
        "blocks": header_blocks,
        "attachments": [
            {
                "color": "#2ea44f",   # GitHub green left border
                "blocks": pr_card_blocks,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Error – something went wrong
# ---------------------------------------------------------------------------

def error_blocks(ticket_key: str, error_message: str) -> list[dict]:
    """Error state message."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":x:  {ticket_key}  --  Failed",
                "emoji": True,
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":warning:  *Something went wrong*\n```{error_message}```",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Please try again or contact the team if the issue persists.",
                },
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_progress_bar(current: int, total: int) -> str:
    """Render a text-based progress bar with percentage."""
    if total <= 0:
        return ""
    ratio = min(current / total, 1.0)
    filled = math.floor(ratio * _BAR_WIDTH)
    empty = _BAR_WIDTH - filled
    pct = int(ratio * 100)
    return f"{_BAR_FILLED * filled}{_BAR_EMPTY * empty}  {pct}%  ({current} / {total})"


def _format_elapsed(seconds: float) -> str:
    """Return a human-friendly elapsed time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs}s"
