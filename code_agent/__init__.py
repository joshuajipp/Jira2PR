"""Bedrock Code Agent — AI-powered code changes from Jira tickets and PR comments."""

from __future__ import annotations

import logging
from typing import Any

from .agent import run_agent
from .git_ops import (
    commit_and_push_to_branch,
    create_pull_request,
    reply_to_issue_comment,
    reply_to_pr_comment,
)

logger = logging.getLogger(__name__)

# Configure basic logging so callers see agent progress by default
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


# ---------------------------------------------------------------------------
# Ticket handling
# ---------------------------------------------------------------------------

def handle_ticket(
    jira_ticket: dict,
    repo_path: str,
    github_token: str,
    repo_owner: str,
    repo_name: str,
) -> str:
    """Take a Jira ticket and a cloned repo, make AI changes, and open a PR."""
    ticket_key = jira_ticket.get("key", "UNKNOWN")
    ticket_summary = jira_ticket.get("summary", "AI-generated changes")

    logger.info("Starting agent for ticket %s: %s", ticket_key, ticket_summary)

    change_summary, files_changed = run_agent(jira_ticket, repo_path)

    if not files_changed:
        logger.warning("Agent finished but reported no file changes.")

    logger.info(
        "Agent complete. %d file(s) changed: %s",
        len(files_changed),
        files_changed,
    )

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


# ---------------------------------------------------------------------------
# PR comment resolution
# ---------------------------------------------------------------------------

_PR_COMMENT_SYSTEM_PROMPT = """\
You are a senior software engineer AI agent. You are resolving review comments \
left on a pull request. You have access to the full repository via tools.

Your job:
1. Read the review comment(s) carefully — each one may specify a file, a line, \
   the surrounding diff context, and what the reviewer wants changed.
2. Explore the repository to understand the codebase context if needed.
3. Make the requested changes using write_file, patch_file, or create_file.
4. After ALL changes are made, respond with a brief summary of what you did \
   for each comment.

Rules:
- Be surgical. Only change what the reviewer asked for.
- Do NOT refactor unrelated code.
- Follow the existing code style.
- If a comment is unclear, make your best reasonable interpretation and note it.
- Always read the target file first before modifying it."""


def parse_comment_from_payload(payload: dict) -> dict:
    """Extract relevant fields from a GitHub webhook payload (review or issue comment)."""
    comment = payload.get("comment", {}) or {}
    repo = payload.get("repository", {}) or {}
    pr = payload.get("pull_request", {}) or {}
    issue = payload.get("issue", {}) or {}

    is_issue_comment = bool(issue.get("pull_request"))
    pr_number = pr.get("number") or issue.get("number")
    pr_title = pr.get("title") or issue.get("title", "")

    head = pr.get("head", {}) if pr else {}
    branch = head.get("ref", "")

    clone_url = repo.get("clone_url") or repo.get("html_url", "")
    if not clone_url and head.get("repo"):
        clone_url = head["repo"].get("clone_url") or clone_url

    comment_type = "issue_comment" if is_issue_comment else "review_comment"

    return {
        "comment_id": comment.get("id"),
        "body": comment.get("body", ""),
        "path": comment.get("path", ""),
        "line": comment.get("line") or comment.get("original_line"),
        "diff_hunk": comment.get("diff_hunk", ""),
        "user": comment.get("user", {}).get("login", "unknown"),
        "pr_number": pr_number,
        "pr_title": pr_title,
        "branch": branch,
        "repo_full_name": repo.get("full_name", ""),
        "repo_owner": repo.get("owner", {}).get("login", ""),
        "repo_name": repo.get("name", ""),
        "clone_url": clone_url,
        "comment_type": comment_type,
    }


def _build_comment_prompt(comments: list[dict]) -> str:
    """Build the user prompt from one or more parsed review comments."""
    if len(comments) == 1:
        c = comments[0]
        location = (
            f"**File:** `{c['path']}` (line {c['line']})\n"
            if c.get("path")
            else ""
        )
        diff = f"**Diff context:**\n```\n{c['diff_hunk']}\n```\n\n" if c.get("diff_hunk") else ""
        return (
            f"Please resolve this PR comment on PR #{c['pr_number']} "
            f"(\"{c['pr_title']}\").\n\n"
            f"**Reviewer:** {c['user']}\n"
            f"{location}"
            f"**Comment:** {c['body']}\n\n"
            f"{diff}"
            f"Read the relevant code, make the requested change, and confirm what you did."
        )

    parts = [
        f"Please resolve ALL of the following {len(comments)} comments "
        f"on PR #{comments[0]['pr_number']} (\"{comments[0]['pr_title']}\").\n"
    ]
    for i, c in enumerate(comments, 1):
        location = (
            f"**File:** `{c['path']}` (line {c['line']})\n"
            if c.get("path")
            else ""
        )
        diff = f"**Diff context:**\n```\n{c['diff_hunk']}\n```\n" if c.get("diff_hunk") else ""
        parts.append(
            f"### Comment {i}\n"
            f"**Reviewer:** {c['user']}\n"
            f"{location}"
            f"**Comment:** {c['body']}\n\n"
            f"{diff}"
        )
    parts.append(
        "Read the relevant files, make ALL requested changes, then provide "
        "a brief summary of what you did for each comment."
    )
    return "\n".join(parts)


def handle_pr_comments(
    comments: list[dict],
    repo_path: str,
    github_token: str,
    repo_owner: str,
    repo_name: str,
    branch_name: str,
    pr_number: int,
) -> str:
    """Resolve one or more PR comments using the AI agent."""
    logger.info(
        "Resolving %d comment(s) on PR #%d (%s/%s branch %s)",
        len(comments),
        pr_number,
        repo_owner,
        repo_name,
        branch_name,
    )

    user_prompt = _build_comment_prompt(comments)
    change_summary, files_changed = run_agent(
        jira_ticket={},
        repo_path=repo_path,
        user_prompt=user_prompt,
        system_prompt=_PR_COMMENT_SYSTEM_PROMPT,
    )

    if not files_changed:
        logger.warning("Agent finished but reported no file changes for PR comments.")

    logger.info(
        "Agent complete. %d file(s) changed: %s",
        len(files_changed),
        files_changed,
    )

    comment_ids = [str(c["comment_id"]) for c in comments if c.get("comment_id")]
    commit_msg = (
        f"Resolve comment(s): {', '.join(comment_ids)}" if comment_ids else "Resolve PR comments"
    )

    commit_sha = commit_and_push_to_branch(
        repo_path=repo_path,
        github_token=github_token,
        repo_owner=repo_owner,
        repo_name=repo_name,
        branch_name=branch_name,
        commit_message=commit_msg,
    )

    # Post replies
    reply_body = (
        f"Resolved in commit `{commit_sha[:8]}`.\n\n"
        f"**Summary of changes:**\n{change_summary}\n\n"
        f"*— AI Code Agent*"
    )
    for c in comments:
        try:
            if c.get("comment_type") == "review_comment" and c.get("comment_id"):
                reply_to_pr_comment(
                    github_token=github_token,
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    pr_number=pr_number,
                    comment_id=c["comment_id"],
                    reply_body=reply_body,
                )
            else:
                reply_to_issue_comment(
                    github_token=github_token,
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    pr_number=pr_number,
                    reply_body=reply_body,
                )
        except Exception as exc:
            logger.error("Failed to reply to comment %s: %s", c.get("comment_id"), exc)

    logger.info("Resolved PR comments. Commit: %s", commit_sha[:8])
    return commit_sha


from .workflow import fetch_jira_ticket, process_pr_comment, process_slack_ticket

__all__ = [
    "handle_ticket",
    "handle_pr_comments",
    "parse_comment_from_payload",
    "process_slack_ticket",
    "process_pr_comment",
    "fetch_jira_ticket",
]
