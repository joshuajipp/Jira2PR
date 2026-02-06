"""Bedrock Code Agent — AI-powered code changes from Jira tickets.

Usage
-----
>>> from code_agent import handle_ticket
>>> pr_url = handle_ticket(
...     jira_ticket={"key": "PROJ-123", "summary": "Add validation", "description": "..."},
...     repo_path="/tmp/repos/my-repo",
...     github_token=os.environ["GITHUB_TOKEN"],
...     repo_owner="my-org",
...     repo_name="my-repo",
... )
>>> print(pr_url)  # https://github.com/my-org/my-repo/pull/42
"""

from __future__ import annotations

import logging

from .agent import run_agent
from .git_ops import create_pull_request

logger = logging.getLogger(__name__)

# Configure basic logging so callers see agent progress by default
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


def handle_ticket(
    jira_ticket: dict,
    repo_path: str,
    github_token: str,
    repo_owner: str,
    repo_name: str,
) -> str:
    """Take a Jira ticket and a cloned repo, make AI changes, and open a PR.

    This is the main entry point your teammates should call.

    Parameters
    ----------
    jira_ticket : dict
        Jira ticket data. Expected keys:
        - ``key`` (str): Ticket ID, e.g. ``"PROJ-123"``
        - ``summary`` (str): One-line title
        - ``description`` (str): Full ticket description
        - ``acceptance_criteria`` (str, optional): AC if available
    repo_path : str
        Absolute path to the locally cloned repository.
    github_token : str
        GitHub personal access token with ``repo`` scope.
    repo_owner : str
        GitHub organisation or user that owns the repository.
    repo_name : str
        Name of the GitHub repository.

    Returns
    -------
    str
        The URL of the newly created pull request.
    """
    ticket_key = jira_ticket.get("key", "UNKNOWN")
    ticket_summary = jira_ticket.get("summary", "AI-generated changes")

    logger.info(
        "Starting agent for ticket %s: %s", ticket_key, ticket_summary
    )

    # 1. Run the AI agent to explore the repo and make changes
    change_summary, files_changed = run_agent(jira_ticket, repo_path)

    if not files_changed:
        logger.warning("Agent finished but reported no file changes.")

    logger.info(
        "Agent complete. %d file(s) changed: %s",
        len(files_changed),
        files_changed,
    )

    # 2. Commit, push, and create a pull request
    pr_url = create_pull_request(
        repo_path=repo_path,
        github_token=github_token,
        repo_owner=repo_owner,
        repo_name=repo_name,
        ticket_key=ticket_key,
        ticket_summary=ticket_summary,
        change_summary=change_summary,
        files_changed=files_changed,
    )

    logger.info("PR created: %s", pr_url)
    return pr_url


from .workflow import fetch_jira_ticket, process_slack_ticket

__all__ = ["handle_ticket", "process_slack_ticket", "fetch_jira_ticket"]
