"""End-to-end workflows for Slack tickets and PR comment follow-ups."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from github import Github

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
    """Inject GitHub token into the repo URL for authenticated access."""
    if not token:
        return repo_url

    if repo_url.startswith("git@github.com:"):
        path = repo_url.replace("git@github.com:", "")
        return f"https://{token}@github.com/{path}"

    if repo_url.startswith("https://github.com"):
        return repo_url.replace("https://github.com", f"https://{token}@github.com")

    if "@github.com" in repo_url:
        return repo_url

    return repo_url


def _clone_repo(
    repo_url: str,
    dest: Path,
    github_token: str | None = None,
    branch: str | None = None,
) -> None:
    """Clone the given repo URL into ``dest``."""
    clone_url = _make_authenticated_url(repo_url, github_token) if github_token else repo_url

    logger.info("Cloning repo %s into %s (branch=%s)", repo_url, dest, branch or "default")
    cmd = ["git", "clone", "--depth", "1", clone_url, str(dest)]
    if branch:
        cmd.extend(["--branch", branch])
    subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
    )


def _clone_repo_branch(
    repo_url: str, dest: Path, branch: str, github_token: str | None = None
) -> None:
    """Clone a specific branch of a repo into ``dest`` for PR comment handling."""
    clone_url = _make_authenticated_url(repo_url, github_token) if github_token else repo_url

    logger.info("Cloning branch '%s' of %s into %s", branch, repo_url, dest)
    subprocess.run(
        ["git", "clone", "--branch", branch, "--single-branch", clone_url, str(dest)],
        check=True,
        text=True,
        capture_output=True,
    )

    # Configure git user for commits in follow-up flows
    subprocess.run(
        ["git", "config", "user.email", "ai-agent@hackathon.local"],
        cwd=str(dest),
        check=True,
        text=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "AI Code Agent"],
        cwd=str(dest),
        check=True,
        text=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Slack ticket workflow
# ---------------------------------------------------------------------------

def process_slack_ticket(ticket_key: str, repo_url: str, slack_username: str) -> str:
    """End-to-end flow for a Slack command (Jira ticket -> PR)."""
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

TRIGGER_PREFIXES = ("ai:", "ai please", "/ai", "@ai")


def _is_ai_trigger(text: str) -> bool:
    stripped = (text or "").strip().lower()
    return any(stripped.startswith(prefix) for prefix in TRIGGER_PREFIXES)


def process_pr_comment(
    webhook_payload: dict,
    additional_payloads: list[dict] | None = None,
) -> str:
    """Resolve PR comments (review or general) via GitHub webhook payloads."""
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise RuntimeError("GITHUB_TOKEN environment variable is required.")

    # Late import to avoid circular dependency at load time
    from . import handle_pr_comments, parse_comment_from_payload

    comments = [parse_comment_from_payload(webhook_payload)]
    if additional_payloads:
        for payload in additional_payloads:
            comments.append(parse_comment_from_payload(payload))

    if not _is_ai_trigger(comments[0]["body"]):
        raise ValueError("Ignored: comment did not include AI trigger.")

    first = comments[0]
    repo_owner = first["repo_owner"]
    repo_name = first["repo_name"]
    branch_name = first.get("branch") or ""
    pr_number = first["pr_number"]
    clone_url = first["clone_url"]
    pr_title = first.get("pr_title", "")

    if not pr_number:
        raise ValueError("PR number missing from comment payload.")

    # If branch/clone_url missing (e.g., issue_comment), fetch PR details
    if not branch_name or not clone_url:
        gh = Github(github_token)
        repo = gh.get_repo(f"{repo_owner}/{repo_name}")
        pr = repo.get_pull(pr_number)
        branch_name = pr.head.ref
        clone_url = pr.head.repo.clone_url
        pr_title = pr.title
        for c in comments:
            if not c.get("branch"):
                c["branch"] = branch_name
            if not c.get("pr_title"):
                c["pr_title"] = pr_title

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
