# Slack Bot — `/do-ticket`

A Slack bot that accepts a `/do-ticket PROJ-123` slash command, processes the
ticket, and replies with a rich PR summary. Currently uses **mock data** so you
can develop and test the Slack integration without a real backend.

## Prerequisites

- Python 3.10+
- A Slack App with **Socket Mode** enabled
- Bot token scopes: `chat:write`, `commands`, `im:write`, `im:history`
- An App-Level Token with `connections:write` scope

## Quick Start

```bash
# 1. Navigate to the project root
cd Jira2PR

# 2. Create & activate the virtual environment (skip if it already exists)
python3 -m venv slack_bot/venv
source slack_bot/venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create a .env file in the project root with your Slack tokens
cat > .env << 'EOF'
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-level-token
EOF

# 5. Run the bot
python -m slack_bot.app
```

You should see:

```
⚡  Slack bot is running in Socket Mode…
```

## Slack App Configuration

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and select your app.
2. Under **Slash Commands**, create a new command:
   - Command: `/do-ticket`
   - Description: `Process a Jira ticket and create a PR`
   - Usage Hint: `PROJ-123`
3. Under **Socket Mode**, make sure it is **enabled**.
4. No Request URL is needed — everything routes over the websocket.

## Usage

In any Slack channel or DM, type:

```
/do-ticket PROJ-123
```

The bot will:

1. Acknowledge the command immediately.
2. Open a DM with you and post a "Starting work..." message.
3. Update the message to "In Progress" while the agent runs.
4. Replace the message with a rich result containing the PR link, branch,
   summary, and diff stats.

## Mock Data

The bot currently returns **hardcoded mock data** from `slack_bot/mock_data.py`.
This simulates a ~3-second processing delay and returns a fake PR response:

| Field           | Mock Value                                  |
|-----------------|---------------------------------------------|
| PR URL          | `https://github.com/org/repo/pull/42`       |
| Branch          | `feature/proj-123-add-auth`                 |
| Title           | Add authentication middleware               |
| Files Changed   | 5                                           |
| Additions       | +120                                        |
| Deletions       | -15                                         |

To customise the mock response, edit the return value in
`slack_bot/mock_data.py:process_ticket()`.

### Request / Response Contract

When the real FastAPI backend is ready, the bot will POST this payload:

```json
{
  "ticket_key": "PROJ-123",
  "repo_url": "https://github.com/org/repo.git",
  "slack_username": "alice"
}
```

And expect this response:

```json
{
  "ticket_key": "PROJ-123",
  "repo_url": "https://github.com/org/repo.git",
  "slack_username": "alice",
  "pr_url": "https://github.com/org/repo/pull/42",
  "branch": "feature/proj-123-add-auth",
  "title": "Add authentication middleware",
  "summary": "Added JWT-based auth middleware with role-based access control.",
  "files_changed": 5,
  "additions": 120,
  "deletions": 15,
  "status": "success"
}
```

## File Structure

```
slack_bot/
  app.py          Entry point — starts Socket Mode
  handlers.py     /do-ticket slash command handler
  messages.py     Block Kit message builders (accepted / progress / completed / error)
  mock_data.py    Mock backend — returns fake PR data
  README.md       This file
```
