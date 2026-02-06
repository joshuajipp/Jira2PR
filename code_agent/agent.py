"""Core agentic loop using Amazon Bedrock's Converse API with tool use.

Sends the Jira ticket to Claude via Bedrock, lets the model iteratively
explore and modify the repository through tool calls, and returns a summary
of all changes made.

Supports two authentication methods:
1. Bearer token via AWS_BEARER_TOKEN_BEDROCK (direct HTTP requests)
2. Standard AWS credentials via boto3 (AWS_ACCESS_KEY_ID/SECRET)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

from .config import AWS_REGION, MAX_AGENT_ITERATIONS, MODEL_ID, SYSTEM_PROMPT
from .tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

# Bedrock API endpoint for converse
BEDROCK_ENDPOINT = f"https://bedrock-runtime.{AWS_REGION}.amazonaws.com"


class BedrockBearerClient:
    """HTTP client for Bedrock API using Bearer token authentication."""

    def __init__(self, bearer_token: str, region: str = AWS_REGION):
        self.bearer_token = bearer_token
        self.region = region
        self.endpoint = f"https://bedrock-runtime.{region}.amazonaws.com"

    def converse(
        self,
        modelId: str,
        messages: list,
        system: list = None,
        toolConfig: dict = None,
    ) -> dict:
        """Call the Bedrock Converse API with Bearer token auth."""
        url = f"{self.endpoint}/model/{modelId}/converse"

        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "messages": messages,
        }
        if system:
            payload["system"] = system
        if toolConfig:
            payload["toolConfig"] = toolConfig

        logger.debug("Calling Bedrock API: %s", url)
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        return response.json()


def _build_bedrock_client() -> Any:
    """Create a Bedrock client using available credentials.

    Priority:
    1. AWS_BEARER_TOKEN_BEDROCK - uses direct HTTP with Bearer token
    2. Standard boto3 auth (AWS_ACCESS_KEY_ID/SECRET or IAM role)
    """
    bearer_token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")

    if bearer_token:
        logger.info("Using Bearer token authentication for Bedrock")
        return BedrockBearerClient(bearer_token, AWS_REGION)

    # Fall back to boto3 standard authentication
    logger.info("Using boto3 standard authentication for Bedrock")
    import boto3
    return boto3.client("bedrock-runtime", region_name=AWS_REGION)


def _format_jira_ticket(jira_ticket: dict) -> str:
    """Turn the Jira ticket dict into a human-readable prompt string."""
    parts = []
    if jira_ticket.get("key"):
        parts.append(f"Ticket ID: {jira_ticket['key']}")
    if jira_ticket.get("summary"):
        parts.append(f"Title: {jira_ticket['summary']}")
    if jira_ticket.get("description"):
        parts.append(f"Description:\n{jira_ticket['description']}")
    if jira_ticket.get("acceptance_criteria"):
        parts.append(f"Acceptance Criteria:\n{jira_ticket['acceptance_criteria']}")

    # Include any extra fields the caller passed
    known_keys = {"key", "summary", "description", "acceptance_criteria"}
    for k, v in jira_ticket.items():
        if k not in known_keys and v:
            parts.append(f"{k}: {v}")

    return "\n\n".join(parts)


def run_agent(
    jira_ticket: dict,
    repo_path: str,
    *,
    user_prompt: str | None = None,
    system_prompt: str | None = None,
) -> tuple[str, list[str]]:
    """Run the agentic loop that modifies the repository.

    Parameters
    ----------
    jira_ticket : dict
        Jira ticket data with at least 'key', 'summary', 'description'.
        Can also be used as a generic task dict with a 'description' key.
    repo_path : str
        Absolute path to the locally cloned repository.
    user_prompt : str, optional
        Custom user prompt to send as the first message.  If not provided,
        a default prompt is built from the jira_ticket dict.
    system_prompt : str, optional
        Custom system prompt.  Defaults to ``SYSTEM_PROMPT`` from config.

    Returns
    -------
    tuple[str, list[str]]
        A tuple of (summary_text, list_of_changed_file_paths).
    """
    client = _build_bedrock_client()
    effective_system = system_prompt or SYSTEM_PROMPT

    if user_prompt is None:
        ticket_text = _format_jira_ticket(jira_ticket)
        user_prompt = (
            "Here is the Jira ticket you need to implement:\n\n"
            "---\n"
            f"{ticket_text}\n"
            "---\n\n"
            "The repository is cloned locally. Start by exploring "
            "the repository structure, then read relevant files, "
            "and make the necessary changes to implement this ticket."
        )

    messages: list[dict] = [
        {
            "role": "user",
            "content": [{"text": user_prompt}],
        }
    ]

    files_changed: list[str] = []

    for iteration in range(1, MAX_AGENT_ITERATIONS + 1):
        logger.info("Agent iteration %d / %d", iteration, MAX_AGENT_ITERATIONS)

        # --- Call Bedrock Converse API ---
        response = client.converse(
            modelId=MODEL_ID,
            messages=messages,
            system=[{"text": effective_system}],
            toolConfig={"tools": TOOL_DEFINITIONS},
        )

        assistant_message = response["output"]["message"]
        stop_reason = response["stopReason"]

        # Append the assistant's reply to the conversation history
        messages.append(assistant_message)

        # --- If the model is done, extract final summary ---
        if stop_reason == "end_turn":
            summary = _extract_text(assistant_message)
            logger.info("Agent finished after %d iterations.", iteration)
            return summary, files_changed

        # --- Process tool use requests ---
        if stop_reason == "tool_use":
            tool_results = _process_tool_calls(
                assistant_message, repo_path, files_changed
            )
            # Feed tool results back as the next user message
            messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason — treat as done
            logger.warning("Unexpected stop reason: %s", stop_reason)
            summary = _extract_text(assistant_message)
            return summary, files_changed

    # Hit the safety cap
    logger.warning("Agent reached max iterations (%d).", MAX_AGENT_ITERATIONS)
    return (
        "Agent reached the maximum number of iterations. "
        "Some changes may be incomplete.",
        files_changed,
    )


def _process_tool_calls(
    assistant_message: dict,
    repo_path: str,
    files_changed: list[str],
) -> list[dict]:
    """Execute every tool call in the assistant message and build results."""
    tool_results = []

    for block in assistant_message["content"]:
        if "toolUse" not in block:
            continue

        tool = block["toolUse"]
        tool_name = tool["name"]
        tool_input = tool["input"]
        tool_id = tool["toolUseId"]

        logger.info(
            "  Tool: %s(%s)",
            tool_name,
            json.dumps(tool_input, default=str)[:120],
        )

        result_text = execute_tool(tool_name, tool_input, repo_path)

        # Track files that were modified
        if not result_text.startswith("Error"):
            if tool_name in ("write_file", "create_file", "patch_file"):
                files_changed.append(tool_input["path"])
            elif tool_name == "delete_file":
                files_changed.append(f"(deleted) {tool_input['path']}")
            elif tool_name == "rename_file":
                files_changed.append(
                    f"(renamed) {tool_input['old_path']} → {tool_input['new_path']}"
                )

        tool_results.append(
            {
                "toolResult": {
                    "toolUseId": tool_id,
                    "content": [{"text": result_text}],
                }
            }
        )

    return tool_results


def _extract_text(message: dict) -> str:
    """Pull all text blocks out of an assistant message."""
    parts = []
    for block in message.get("content", []):
        if "text" in block:
            parts.append(block["text"])
    return "\n".join(parts) if parts else "(no summary provided)"

