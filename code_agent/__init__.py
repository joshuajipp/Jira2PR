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
from typing import Any

from .agent import run_agent
from .git_ops import commit_and_push_to_branch, create_pull_request, reply_to_pr_comment

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


# ---------------------------------------------------------------------------
# PR comment resolution
# ---------------------------------------------------------------------------

# System prompt specifically for resolving PR review comments
_PR_COMMENT_SYSTEM_PROMPT = """\
You are a senior software engineer AI agent. You are resolving review comments \
left on a pull request. You have access to the full repository via tools.

Your job:
1. Read the review comment(s) carefully — each one specifies a file, a line, \
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
    """Extract the relevant fields from a single GitHub webhook payload.

    Returns a normalised dict with the fields the agent needs.
    """
    comment = payload.get("comment", {})
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    head = pr.get("head", {})

    return {
        "comment_id": comment.get("id"),
        "body": comment.get("body", ""),
        "path": comment.get("path", ""),
        "line": comment.get("line") or comment.get("original_line"),
        "diff_hunk": comment.get("diff_hunk", ""),
        "user": comment.get("user", {}).get("login", "unknown"),
        "pr_number": pr.get("number"),
        "pr_title": pr.get("title", ""),
        "branch": head.get("ref", ""),
        "repo_full_name": repo.get("full_name", ""),
        "repo_owner": repo.get("owner", {}).get("login", ""),
        "repo_name": repo.get("name", ""),
        "clone_url": repo.get("clone_url") or repo.get("html_url", ""),
    }


def _build_comment_prompt(comments: list[dict]) -> str:
    """Build the user prompt from one or more parsed review comments."""
    if len(comments) == 1:
        c = comments[0]
        return (
            f"Please resolve this PR review comment on PR #{c['pr_number']} "
            f"(\"{c['pr_title']}\").\n\n"
            f"**Reviewer:** {c['user']}\n"
            f"**File:** `{c['path']}` (line {c['line']})\n"
            f"**Comment:** {c['body']}\n\n"
            f"**Diff context:**\n```\n{c['diff_hunk']}\n```\n\n"
            f"Read the file, make the requested change, and confirm what you did."
        )

    # Multiple comments — batch
    parts = [
        f"Please resolve ALL of the following {len(comments)} review comments "
        f"on PR #{comments[0]['pr_number']} (\"{comments[0]['pr_title']}\").\n"
    ]
    for i, c in enumerate(comments, 1):
        parts.append(
            f"### Comment {i}\n"
            f"**Reviewer:** {c['user']}\n"
            f"**File:** `{c['path']}` (line {c['line']})\n"
            f"**Comment:** {c['body']}\n\n"
            f"**Diff context:**\n```\n{c['diff_hunk']}\n```\n"
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
    """Resolve one or more PR review comments using the AI agent.

    The repo must already be cloned and checked out on the PR branch.

    Parameters
    ----------
    comments : list[dict]
        List of parsed comment dicts (from ``parse_comment_from_payload``).
    repo_path : str
        Absolute path to the cloned repo (on the PR branch).
    github_token : str
        GitHub personal access token.
    repo_owner : str
        GitHub org or username.
    repo_name : str
        Repository name.
    branch_name : str
        The PR branch name (already checked out).
    pr_number : int
        The pull request number.

    Returns
    -------
    str
        The commit SHA of the resolution commit.
    """
    logger.info(
        "Resolving %d comment(s) on PR #%d (%s/%s branch %s)",
        len(comments),
        pr_number,
        repo_owner,
        repo_name,
        branch_name,
    )

    # 1. Build prompt and run the agent
    user_prompt = _build_comment_prompt(comments)
    change_summary, files_changed = run_agent(
        jira_ticket={},  # Not used when user_prompt is provided
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

    # 2. Commit and push to the existing PR branch
    comment_ids = [c["comment_id"] for c in comments if c.get("comment_id")]
    commit_msg = f"Resolve review comment(s): {', '.join(str(cid) for cid in comment_ids)}"

    commit_sha = commit_and_push_to_branch(
        repo_path=repo_path,
        github_token=github_token,
        repo_owner=repo_owner,
        repo_name=repo_name,
        branch_name=branch_name,
        commit_message=commit_msg,
    )

    # 3. Reply to each comment on GitHub
    for c in comments:
        if not c.get("comment_id"):
            continue
        try:
            reply_body = (
                f"Resolved in commit `{commit_sha[:8]}`.\n\n"
                f"**Changes made:**\n{change_summary}\n\n"
                f"*— AI Code Agent*"
            )
            reply_to_pr_comment(
                github_token=github_token,
                repo_owner=repo_owner,
                repo_name=repo_name,
                pr_number=pr_number,
                comment_id=c["comment_id"],
                reply_body=reply_body,
            )
        except Exception as exc:
            logger.error(
                "Failed to reply to comment %s: %s", c["comment_id"], exc
            )

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
