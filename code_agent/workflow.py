"""End-to-end workflow for Slack-triggered Jira tickets.

Given a Jira ticket key, Slack username, and GitHub repo URL, this module:
1) Fetches the ticket details from Jira.
2) Clones the GitHub repo to a temporary directory.
3) Calls ``handle_ticket`` to let the AI implement changes and open a PR.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from .config import JIRA_API_TOKEN, JIRA_BASE_URL, JIRA_EMAIL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Jira helpers
# ---------------------------------------------------------------------------

def fetch_jira_ticket(ticket_key: str) -> dict:
    """Fetch Jira ticket details (summary + description) for a given key."""
    if not (JIRA_BASE_URL and JIRA_EMAIL and JIRA_API_TOKEN):
        raise RuntimeError(
            "Jira credentials missing. Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN."
        )

    url = f"{JIRA_BASE_URL.rstrip('/')}/rest/api/3/issue/{ticket_key}"
    params = {"fields": "summary,description", "expand": "renderedFields"}

    response = requests.get(
        url,
        params=params,
        headers={"Accept": "application/json"},
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        timeout=15,
    )
    response.raise_for_status()

    issue = response.json()
    fields = issue.get("fields", {}) if isinstance(issue, dict) else {}

    summary = fields.get("summary") or "(no summary provided)"
    description = _extract_description(issue)

    return {
        "key": issue.get("key", ticket_key),
        "summary": summary,
        "description": description or "(no description provided)",
    }


def _extract_description(issue: dict) -> str:
    """Try to pull a readable description from Jira issue data."""
    if not isinstance(issue, dict):
        return ""

    fields = issue.get("fields", {}) or {}
    description = fields.get("description")

    text = _flatten_adf(description)
    if text:
        return text.strip()

    rendered = issue.get("renderedFields", {}) or {}
    rendered_desc = rendered.get("description")
    if isinstance(rendered_desc, str):
        return rendered_desc.strip()
    if rendered_desc:
        return str(rendered_desc)

    return ""


def _flatten_adf(node) -> str:
    """Flatten Atlassian Document Format (ADF) content to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text" and "text" in node:
            return node.get("text", "")
        parts = [_flatten_adf(child) for child in node.get("content", [])]
        return "\n".join(p for p in parts if p)
    if isinstance(node, list):
        parts = [_flatten_adf(child) for child in node]
        return "\n".join(p for p in parts if p)
    return ""


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _parse_github_repo(repo_url: str) -> tuple[str, str]:
    """Extract (owner, repo_name) from a GitHub URL."""
    if not repo_url:
        raise ValueError("Repository URL is required.")

    if repo_url.startswith("git@"):
        # git@github.com:owner/repo.git
        path = repo_url.split(":", 1)[-1]
    else:
        parsed = urlparse(repo_url)
        path = parsed.path.lstrip("/")

    if path.endswith(".git"):
        path = path[:-4]

    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Could not parse owner/repo from URL: {repo_url}")

    return parts[0], parts[1]


def _make_authenticated_url(repo_url: str, token: str) -> str:
    """Inject GitHub token into the repo URL for authenticated access.
    
    Converts https://github.com/owner/repo to https://TOKEN@github.com/owner/repo
    """
    if not token:
        return repo_url
    
    # Handle SSH URLs - convert to HTTPS with token
    if repo_url.startswith("git@github.com:"):
        path = repo_url.replace("git@github.com:", "")
        return f"https://{token}@github.com/{path}"
    
    # Handle HTTPS URLs
    if repo_url.startswith("https://github.com"):
        return repo_url.replace("https://github.com", f"https://{token}@github.com")
    
    # Handle URLs that already have a token or other auth
    if "@github.com" in repo_url:
        return repo_url
    
    return repo_url


def _clone_repo(repo_url: str, dest: Path, github_token: str = None) -> None:
    """Clone the given repo URL into ``dest``.
    
    If github_token is provided, it will be used for authentication.
    """
    # Use authenticated URL if token provided
    clone_url = _make_authenticated_url(repo_url, github_token) if github_token else repo_url
    
    # Log without exposing the token
    logger.info("Cloning repo %s into %s", repo_url, dest)
    subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(dest)],
        check=True,
        text=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Public workflow
# ---------------------------------------------------------------------------

def process_slack_ticket(ticket_key: str, repo_url: str, slack_username: str) -> str:
    """End-to-end flow for a Slack command.

    - Fetch Jira ticket details
    - Clone the GitHub repo
    - Call handle_ticket to generate the PR
    """
    logger.info(
        "Received Slack request from %s for ticket %s and repo %s",
        slack_username,
        ticket_key,
        repo_url,
    )

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise RuntimeError("GITHUB_TOKEN environment variable is required.")

    jira_ticket = fetch_jira_ticket(ticket_key)
    jira_ticket["requested_by"] = slack_username

    repo_owner, repo_name = _parse_github_repo(repo_url)

    with tempfile.TemporaryDirectory(prefix="jira2pr-") as tmpdir:
        repo_path = Path(tmpdir) / "repo"
        _clone_repo(repo_url, repo_path, github_token=github_token)

        # Late import to avoid circular import at module load time
        from . import handle_ticket

        pr_url = handle_ticket(
            jira_ticket=jira_ticket,
            repo_path=str(repo_path),
            github_token=github_token,
            repo_owner=repo_owner,
            repo_name=repo_name,
        )

    logger.info("Completed Slack flow for %s. PR: %s", ticket_key, pr_url)
    return pr_url


# ---------------------------------------------------------------------------
# PR comment resolution workflow
# ---------------------------------------------------------------------------

def _clone_repo_branch(
    repo_url: str, dest: Path, branch: str, github_token: str | None = None
) -> None:
    """Clone a specific branch of a repo into ``dest``.

    Unlike ``_clone_repo`` (which does a shallow clone of the default branch),
    this fetches just enough history to push a new commit to ``branch``.
    """
    clone_url = (
        _make_authenticated_url(repo_url, github_token)
        if github_token
        else repo_url
    )

    logger.info("Cloning branch '%s' of %s into %s", branch, repo_url, dest)
    subprocess.run(
        ["git", "clone", "--branch", branch, "--single-branch", clone_url, str(dest)],
        check=True,
        text=True,
        capture_output=True,
    )

    # Configure git user for commits
    subprocess.run(
        ["git", "config", "user.email", "ai-agent@hackathon.local"],
        cwd=str(dest), check=True, text=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "AI Code Agent"],
        cwd=str(dest), check=True, text=True, capture_output=True,
    )


def process_pr_comment(
    webhook_payload: dict,
    additional_payloads: list[dict] | None = None,
) -> str:
    """End-to-end flow for resolving PR review comment(s).

    Accepts one or more GitHub webhook payloads, clones the PR branch,
    runs the AI agent to resolve all comments, commits, pushes, and
    replies to each comment on GitHub.

    Parameters
    ----------
    webhook_payload : dict
        The primary GitHub ``pull_request_review_comment`` webhook payload.
    additional_payloads : list[dict], optional
        Extra comment payloads from the same review to batch together.

    Returns
    -------
    str
        The commit SHA of the resolution commit.
    """
    # Late import to avoid circular dependency at load time
    from . import handle_pr_comments, parse_comment_from_payload

    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise RuntimeError("GITHUB_TOKEN environment variable is required.")

    # Parse all comment payloads
    comments = [parse_comment_from_payload(webhook_payload)]
    if additional_payloads:
        for payload in additional_payloads:
            comments.append(parse_comment_from_payload(payload))

    # Extract repo / PR info from the first comment
    first = comments[0]
    repo_owner = first["repo_owner"]
    repo_name = first["repo_name"]
    branch_name = first["branch"]
    pr_number = first["pr_number"]
    clone_url = first["clone_url"]

    logger.info(
        "Processing %d PR comment(s) on %s/%s PR #%d branch %s",
        len(comments),
        repo_owner,
        repo_name,
        pr_number,
        branch_name,
    )

    with tempfile.TemporaryDirectory(prefix="pr-comment-") as tmpdir:
        repo_path = Path(tmpdir) / "repo"
        _clone_repo_branch(clone_url, repo_path, branch_name, github_token)

        commit_sha = handle_pr_comments(
            comments=comments,
            repo_path=str(repo_path),
            github_token=github_token,
            repo_owner=repo_owner,
            repo_name=repo_name,
            branch_name=branch_name,
            pr_number=pr_number,
        )

    logger.info(
        "Completed PR comment resolution for PR #%d. Commit: %s",
        pr_number,
        commit_sha[:8],
    )
    return commit_sha


__all__ = ["process_slack_ticket", "fetch_jira_ticket", "process_pr_comment"]
