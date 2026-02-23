# AI Content Engine

Multi-agent pipeline that discovers trending AI/tech news, drafts LinkedIn posts and Medium articles, and publishes after human approval.

## Architecture

```
Cloud Scheduler (7am AEST)
    -> Scout Agent (Gemini 2.0 Flash + Google Search grounding)
    -> Editor Agent (Gemini 2.0 Pro with persona prompt)
    -> BigQuery (store as draft)
    -> Approval Dashboard (Cloud Run - FastAPI)
    -> Publisher Agent (LinkedIn + Medium APIs)
```

## Quick Start

### 1. Prerequisites

- Python 3.11+
- GCP project (`dan-sandpit`) with billing enabled
- `gcloud` CLI authenticated as `daniel.zillmann@intelia.com.au`

### 2. Setup

```bash
# Clone and install
cd AI-Content-Engine
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Copy env template
cp .env.example .env
# Edit .env with your values

# Enable GCP APIs and create resources
make setup
make setup-bq
make setup-secrets
```

### 3. Local Development

```bash
# Run the dashboard
make local-dashboard
# Visit http://localhost:8080

# Run the pipeline manually
make local-pipeline

# Run tests
make test
```

### 4. Deploy to GCP

```bash
make deploy-all
```

## Agent Details

| Agent | Model | Purpose |
|-------|-------|---------|
| Scout | Gemini 2.0 Flash | Web search grounding — finds trending AI/tech news |
| Editor | Gemini 2.0 Pro | Writes LinkedIn posts + Medium articles with persona |
| Publisher | N/A (API calls) | LinkedIn OAuth 2.0 + Medium integration token |

## LinkedIn Setup

See [docs/LINKEDIN_SETUP.md](LINKEDIN_SETUP.md) for detailed LinkedIn App creation instructions.

## Project Structure

```
agents/         - Scout, Editor, Publisher agent implementations
config/         - Settings and Secret Manager utilities
dashboard/      - FastAPI approval UI (Cloud Run)
models/         - Pydantic data models
storage/        - BigQuery CRUD operations
tests/          - Unit tests
docs/           - Documentation
main.py         - Cloud Functions entry points
```
