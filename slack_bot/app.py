import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = App(token=os.environ["SLACK_BOT_TOKEN"])

@app.event("message")
def handle_message(event, say):
    if event.get("channel_type") == "im" and event.get("subtype") is None:
        say("👋 Yep, I’m alive. Code is running.")

if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()