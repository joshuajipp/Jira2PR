"""
Slack Block Kit message builders for /do-ticket responses.

Each function returns a list of Block Kit blocks that can be passed
directly to `blocks=` in Slack API calls.
"""

import datetime


# ---------------------------------------------------------------------------
# Accepted – first message posted right after the command is received
# ---------------------------------------------------------------------------

def accepted_blocks(ticket_key: str) -> list[dict]:
    """Initial acknowledgement message."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":ticket:  {ticket_key}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":hourglass_flowing_sand:  *Starting work on your ticket…*\nHang tight — I'm spinning things up.",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Received at {now}",
                },
            ],
        },
    ]


# ---------------------------------------------------------------------------
# In-progress – updated onto the same message while work is happening
# ---------------------------------------------------------------------------

def in_progress_blocks(ticket_key: str, step: str = "Cloning repo & running agent") -> list[dict]:
    """Progress update message."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":ticket:  {ticket_key}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":gear:  *In Progress*\n{step}…",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": ":arrows_counterclockwise:  Working on it — I'll update this message when done.",
                },
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Completed – final rich result with PR link and stats
# ---------------------------------------------------------------------------

def completed_blocks(data: dict, elapsed_seconds: float) -> list[dict]:
    """Final success message with PR details.

    Parameters
    ----------
    data : dict
        Response payload from process_ticket().
    elapsed_seconds : float
        Wall-clock time the processing took.
    """
    elapsed = _format_elapsed(elapsed_seconds)

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":white_check_mark:  {data['ticket_key']} — Done!",
                "emoji": True,
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*<{data['pr_url']}|:merged:  Pull Request #{data['pr_url'].rsplit('/', 1)[-1]}>*\n{data['title']}",
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Open PR",
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
                    "text": f"*Branch*\n`{data['branch']}`",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Repo*\n`{data['repo_url']}`",
                },
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Summary*\n{data['summary']}",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Files changed*\n{data['files_changed']}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Diff*\n+{data['additions']}  -{data['deletions']}",
                },
            ],
        },
        {"type": "divider"},
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
                "text": f":x:  {ticket_key} — Failed",
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

def _format_elapsed(seconds: float) -> str:
    """Return a human-friendly elapsed time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs}s"
