# Jira2PR - Autonomous Jira-to-Pull-Request Pipeline

An AI-powered Slack bot that automatically transforms Jira tickets into GitHub Pull Requests using Amazon Bedrock (Claude).

## How It Works

1. **Slack Command**: User types `/do-ticket PROJ-123` (optionally with a repo URL)
2. **Jira Fetch**: The bot fetches the ticket details (summary, description) from Jira
3. **Repo Clone**: Clones the target GitHub repository to a temporary directory
4. **AI Agent**: Amazon Bedrock (Claude) analyzes the ticket and codebase, then implements the required changes using file operation tools
5. **PR Creation**: The bot commits the changes, pushes to a new branch, and creates a Pull Request
6. **Slack Response**: User receives a message with the PR link

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Slack     │────▶│  Slack Bot  │────▶│  Workflow   │────▶│   Bedrock   │
│  /do-ticket │     │  (Socket)   │     │  Orchestr.  │     │   (Claude)  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
                    ▼                          ▼                          ▼
             ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
             │    Jira     │           │   GitHub    │           │  Git Ops    │
             │    API      │◀──────────│ Webhook     │           │  (clone/    │
             │             │    POST   │ Server      │           │   push/PR)  │
             └─────────────┘           └─────────────┘           └─────────────┘
                                        (FastAPI)
```

## Prerequisites

- Python 3.10+
- A Slack workspace with permission to install apps
- A Jira Cloud instance
- A GitHub account with repository access
- Amazon Bedrock access (with Claude model enabled)

## Environment Variables

Create a `.env` file in the project root with the following:

```bash
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token        # Bot User OAuth Token (starts with xoxb-)
SLACK_APP_TOKEN=xapp-your-app-token        # App-Level Token for Socket Mode (starts with xapp-)

# Jira Configuration
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-jira-api-token         # Generate at: https://id.atlassian.com/manage-profile/security/api-tokens

# GitHub Configuration
GITHUB_TOKEN=github_pat_xxxx               # Fine-grained PAT with repo read/write access
REPO_URL=https://github.com/owner/repo     # Default repository (optional, can be overridden in command)

# AWS Bedrock Configuration
AWS_BEARER_TOKEN_BEDROCK=your-bearer-token # Bedrock API key (if using bearer auth)
AWS_DEFAULT_REGION=us-east-1               # AWS region for Bedrock

# Alternative: Standard AWS credentials (if not using bearer token)
# AWS_ACCESS_KEY_ID=your-access-key
# AWS_SECRET_ACCESS_KEY=your-secret-key
```

## Slack App Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app
2. Enable **Socket Mode** under Settings
3. Create an **App-Level Token** with `connections:write` scope
4. Under **OAuth & Permissions**, add these Bot Token Scopes:
   - `chat:write`
   - `commands`
5. Under **Slash Commands**, create a new command:
   - Command: `/do-ticket`
   - Request URL: Not needed for Socket Mode
   - Description: `Process a Jira ticket and create a PR`
   - Usage Hint: `PROJ-123 [repo-url]`
6. Install the app to your workspace
7. Copy the **Bot User OAuth Token** (`xoxb-...`) and **App-Level Token** (`xapp-...`)

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd Jira2PR-main

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env  # Then edit .env with your values
```

## Usage

### Starting the Bot

```bash
# Activate virtual environment
source venv/bin/activate

# Run the Slack bot
python3 -m slack_bot.app

# Run the GitHub webhook server (for PR comment follow-ups)
PORT=8080 python3 -m code_agent.webhook_server
```

You should see:
```
⚡️ Bolt app is running!
```

### Slack Commands

**Basic usage** (uses default `REPO_URL` from `.env`):
```
/do-ticket PROJ-123
```

**With explicit repository URL**:
```
/do-ticket PROJ-123 https://github.com/owner/repo
```

The bot will:
1. Acknowledge your request immediately
2. Send progress updates as it works
3. Reply with a link to the created Pull Request (or an error message)

### GitHub comment webhook (follow-up changes)
- Start the minimal webhook server (FastAPI):
  ```bash
  PORT=9000 uvicorn code_agent.webhook_server:app --reload --port ${PORT:-8000}
  # or
  PORT=9000 python -m code_agent.webhook_server
  ```
- Point a GitHub webhook (or App) at `POST /webhooks/github` (use the correct host/port, e.g., `http://<host>:8000/webhooks/github`).
- Subscribe to `issue_comment` and `pull_request_review_comment` events.
- Comments must start with one of: `ai:`, `ai please`, `/ai`, `@ai` to trigger the agent (case-insensitive).
- Works for both PR conversation comments and inline review comments; the service clones the PR branch, reruns the AI with the comment context, pushes to the same branch, and replies to the comment (or adds a PR comment for general comments).

## Project Structure

```
Jira2PR-main/
├── .env                    # Environment variables (create from .env.example)
├── requirements.txt        # Python dependencies
├── README.md              # This file
│
├── slack_bot/             # Slack Bot Module
│   ├── __init__.py
│   ├── app.py             # Entry point - initializes Slack Bolt app & Socket Mode
│   └── handlers.py        # Slash command handler (/do-ticket), background processing
│
└── code_agent/            # Core AI Agent Module
    ├── __init__.py        # Package exports (process_slack_ticket, process_pr_comment)
    ├── config.py          # Configuration constants (model ID, regions, etc.)
    ├── workflow.py        # Main orchestrator - fetches Jira, clones repo, runs agent
    ├── agent.py           # AI agent loop - Bedrock Converse API with tool use
    ├── tools.py           # File operation tools (read, write, list, create)
    ├── git_ops.py         # Git operations (checkout, commit, push, PR replies)
    └── webhook_server.py  # Minimal FastAPI webhook server for GitHub comments
```

### Key Files Explained

| File | Purpose |
|------|---------|
| `slack_bot/app.py` | Initializes Slack Bolt app, loads `.env`, starts Socket Mode handler |
| `slack_bot/handlers.py` | Handles `/do-ticket` command, parses arguments, spawns background thread |
| `code_agent/workflow.py` | Orchestrates the full flow: Jira fetch → clone → agent → PR |
| `code_agent/agent.py` | Implements the agentic loop using Bedrock's Converse API with tool_use |
| `code_agent/tools.py` | Defines tools the AI can use: `list_directory`, `read_file`, `write_file`, `create_file` |
| `code_agent/git_ops.py` | Handles Git operations and GitHub PR creation via PyGithub |
| `code_agent/config.py` | Centralized configuration (model ID, limits, Jira URL, etc.) |

## Deployment

### Local Development

```bash
source venv/bin/activate
python -m slack_bot.app
```

### EC2 Deployment

1. **Copy project to EC2**:
   ```bash
   scp -r -i your-key.pem Jira2PR-main user@ec2-ip:~/
   ```

2. **SSH into EC2**:
   ```bash
   ssh -i your-key.pem user@ec2-ip
   ```

3. **Set up environment**:
   ```bash
   cd Jira2PR-main
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Configure Git** (required for commits):
   ```bash
   git config --global user.email "your-email@example.com"
   git config --global user.name "Your Name"
   ```

5. **Edit `.env`** with your credentials

6. **Run the bot**:
   ```bash
   python -m slack_bot.app
   ```

   For background execution:
   ```bash
   nohup python -m slack_bot.app > bot.log 2>&1 &
   ```

## How the AI Agent Works

The AI agent uses Amazon Bedrock's Converse API with **tool use** (function calling):

1. **System Prompt**: Instructs the AI to act as a senior developer implementing Jira tickets
2. **Tool Definitions**: The AI has access to file operations:
   - `list_directory` - Browse the codebase
   - `read_file` - Read file contents
   - `write_file` - Modify existing files
   - `create_file` - Create new files
3. **Iterative Loop**: The AI can make multiple tool calls, examining code and making changes
4. **Completion**: When satisfied, the AI signals completion and changes are committed

## Troubleshooting

### "KeyError: 'SLACK_BOT_TOKEN'"
- Ensure `.env` file exists in the `Jira2PR-main` directory
- Verify all required environment variables are set

### "missing_scope" Slack Error
- Add required scopes in Slack App settings under OAuth & Permissions
- Reinstall the app to your workspace after adding scopes

### Git commit fails with "Author identity unknown"
```bash
git config --global user.email "your-email@example.com"
git config --global user.name "Your Name"
```

### "externally-managed-environment" on Ubuntu 24.04
- Use a virtual environment (see Installation section)

### GitHub push authentication fails
- Ensure `GITHUB_TOKEN` has `repo` scope (write access)
- The token must belong to a user with push access to the repository

## Security Notes

- Never commit `.env` files to version control
- Use fine-grained GitHub PATs with minimal required permissions
- Rotate tokens regularly
- The AI agent has path traversal protection to prevent accessing files outside the repo

## License

MIT License
