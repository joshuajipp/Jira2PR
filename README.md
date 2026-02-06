AutoPR

## API Gateway

Run the FastAPI gateway:

```bash
# from repo root, after activating your venv
# PORT is optional (defaults to 8000)
PORT=9000 uvicorn code_agent.server:app --reload --port ${PORT:-8000}
```

Alternatively, run via the module (also honors `PORT`):

```bash
PORT=9000 python -m code_agent.server
```

POST `/tickets/process` with:
- `ticket_key`: Jira ticket key (e.g., `PROJ-123`)
- `repo_url`: GitHub repo URL (SSH or HTTPS)
- `slack_username`: user who initiated the request

Health check: `GET /health`
