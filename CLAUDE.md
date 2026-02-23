# Project: AI Agent Content Engine (GCP)

## Project Overview

An automated pipeline that crawls tech news, relates it to internal project documentation, and drafts LinkedIn/Medium posts using Vertex AI. Fully standalone — no relation to other projects.

## Tech Stack

- **Language:** Python 3.11+
- **Orchestration:** Custom agent pipeline (Scout → Editor → Publisher)
- **LLM:** Gemini 2.0 Flash (Scout/search), Gemini 2.0 Pro (Editor/writing)
- **SDK:** `google-genai` (NOT deprecated `vertexai` module)
- **Infrastructure:** Cloud Functions Gen 2, Cloud Scheduler, Cloud Run (Dashboard)
- **Data:** BigQuery (post history), Secret Manager (API tokens)
- **APIs:** LinkedIn Posts API (OAuth 2.0), Medium API (integration token)

## GCP Configuration

- **Project:** `dan-sandpit`
- **Account:** `daniel.zillmann@intelia.com.au`
- **Region:** `us-central1`
- **Service Account:** `content-engine-sa@dan-sandpit.iam.gserviceaccount.com`

## Development Standards

- **Error Handling:** Always use try-except blocks with `logging.error` for API calls.
- **Environment Variables:** Use GCP Secret Manager for `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, and `MEDIUM_TOKEN`. Do not use `.env` for production.
- **GCP Auth:** Use `google.auth.default()` for local development and Service Account impersonation for production.
- **Formatting:** Follow PEP 8; use Type Hints for all function signatures.
- **Models:** Use Pydantic v2 for all data models.

## Agent Personas

1. **The Scout:** Focuses on high-recall web searching and summarization of AI trends. Uses Google Search grounding via Vertex AI.
2. **The Editor:** Professional, slightly witty, tech-savvy tone. Focuses on "How-To" and "Lessons Learned." Produces both LinkedIn posts (short-form) and Medium articles (long-form).
3. **The Publisher:** Purely functional; handles OAuth2 flows and Markdown-to-HTML conversion for Medium.

## Pipeline Flow

```
Cloud Scheduler (7am AEST daily)
    → Cloud Function: run_pipeline()
        → ScoutAgent.search() [Gemini 2.0 Flash + Google Search grounding]
        → EditorAgent.write() [Gemini 2.0 Pro + persona prompt]
        → BigQuery: store (status=draft)
    → Dashboard (Cloud Run - FastAPI)
        → User reviews/edits/approves
    → Cloud Function: publish()
        → LinkedInPublisher.publish_post()
        → MediumPublisher.publish_article()
        → BigQuery: update (status=published)
```

## Deployment Commands

```bash
# Deploy Cloud Functions
gcloud functions deploy content-engine-pipeline --gen2 --runtime python311 --trigger-http
gcloud functions deploy content-engine-publish --gen2 --runtime python311 --trigger-http

# Deploy Dashboard
gcloud run deploy content-engine-dashboard --source . --region us-central1

# Create Scheduler
gcloud scheduler jobs create http content-engine-daily \
  --schedule="0 7 * * *" --time-zone="Australia/Sydney"
```

## Current Progress

- [x] Initialize Repository
- [x] Project structure scaffolded
- [ ] Configure GCP Service Account
- [ ] Implement Scout Agent (Search Grounding)
- [ ] Implement Editor Agent (Style Alignment)
- [ ] Setup Publisher (LinkedIn/Medium API)
- [ ] Build Approval Dashboard
- [ ] Deploy to GCP
