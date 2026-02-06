"""
Slack bot entry point.

Starts the bot in Socket Mode and registers the /do-ticket slash command.
"""

import os

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from .handlers import register

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = App(token=os.environ["SLACK_BOT_TOKEN"])

# Register all command/event handlers
register(app)

if __name__ == "__main__":
    print("⚡  Slack bot is running in Socket Mode…")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
