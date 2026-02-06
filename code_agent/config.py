"""Configuration constants for the Bedrock code agent."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (parent of code_agent/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# Bedrock model to use for code generation
MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-20250514-v1:0",
)

# AWS region for Bedrock
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

# Maximum number of agent loop iterations (safety cap)
MAX_AGENT_ITERATIONS = 30

# Git branch prefix for AI-generated branches
BRANCH_PREFIX = "ai"

# Base branch to create PRs against
BASE_BRANCH = os.environ.get("BASE_BRANCH", "main")

# Jira credentials (used by the Slack workflow)
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")

# System prompt that instructs the model how to behave
SYSTEM_PROMPT = """You are a senior software engineer AI agent. You are given a Jira ticket \
with requirements, and you have access to a code repository via tools.

Your job:
1. First, explore the repository structure using list_directory to understand the codebase.
2. Read relevant files to understand the existing code, conventions, and style.
3. Plan your changes based on the Jira ticket requirements.
4. Make the necessary code changes using write_file or create_file.
5. After ALL changes are made, respond with a clear summary of what you changed and why.

Rules:
- Be thorough but focused. Only change what is needed to fulfill the ticket requirements.
- Write clean, production-quality code.
- Follow the existing code style and conventions in the repository.
- If you need to add dependencies, mention them in your summary.
- Do NOT make unrelated changes.
- Always explore the repo structure first before making any changes."""
