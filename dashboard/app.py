"""
Approval Dashboard — FastAPI application for reviewing and publishing content.

Deployed to Cloud Run. Provides:
- List of pending drafts
- Review/edit interface for each draft
- Approve/reject workflow
- LinkedIn OAuth callback handling
- Published post history

Local dev: uvicorn dashboard.app:app --reload --port 8080
"""
import logging
import os
import uuid

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(title="AI Content Engine Dashboard")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-secret-change-in-prod"),
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static",
)


# --- Dashboard Routes ---


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Dashboard home — list pending drafts."""
    from storage.bigquery import list_pipelines

    pipelines = list_pipelines(status="draft")
    return templates.TemplateResponse(
        "index.html", {"request": request, "pipelines": pipelines}
    )


@app.get("/review/{pipeline_id}", response_class=HTMLResponse)
async def review(request: Request, pipeline_id: str):
    """Review a single draft — view, edit, approve, or reject."""
    from storage.bigquery import get_pipeline

    pipeline = get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return templates.TemplateResponse(
        "review.html", {"request": request, "pipeline": pipeline}
    )


@app.post("/approve/{pipeline_id}")
async def approve(
    request: Request,
    pipeline_id: str,
    linkedin_content: str = Form(None),
    medium_content: str = Form(None),
):
    """Approve a draft (optionally with edits)."""
    from storage.bigquery import (
        get_pipeline,
        update_pipeline_content,
        update_pipeline_status,
    )

    pipeline = get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Save any edits
    if linkedin_content or medium_content:
        update_pipeline_content(pipeline_id, linkedin_content, medium_content)

    update_pipeline_status(pipeline_id, "approved", approved_by="dashboard")

    return RedirectResponse(url="/", status_code=303)


@app.post("/reject/{pipeline_id}")
async def reject(request: Request, pipeline_id: str):
    """Reject a draft."""
    from storage.bigquery import update_pipeline_status

    update_pipeline_status(pipeline_id, "rejected")
    return RedirectResponse(url="/", status_code=303)


@app.post("/publish/{pipeline_id}")
async def publish(request: Request, pipeline_id: str):
    """Approve and immediately publish to LinkedIn + Medium."""
    from agents.publisher import LinkedInPublisher, MediumPublisher
    from storage.bigquery import get_pipeline, update_pipeline_status

    pipeline = get_pipeline(pipeline_id)
    if not pipeline or not pipeline.editor_output:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Mark as approved
    update_pipeline_status(pipeline_id, "approved", approved_by="dashboard")

    results = {}

    # Publish to LinkedIn
    try:
        linkedin = LinkedInPublisher()
        result = await linkedin.publish_post(
            pipeline.editor_output.linkedin_draft
        )
        results["linkedin"] = result.model_dump(mode="json")
    except Exception as e:
        logger.error(f"LinkedIn publish failed: {e}")
        results["linkedin"] = {"success": False, "error": str(e)}

    # Publish to Medium
    try:
        medium = MediumPublisher()
        result = await medium.publish_article(
            pipeline.editor_output.medium_draft,
            publish_status="public",
        )
        results["medium"] = result.model_dump(mode="json")
    except Exception as e:
        logger.error(f"Medium publish failed: {e}")
        results["medium"] = {"success": False, "error": str(e)}

    update_pipeline_status(pipeline_id, "published", results)

    return RedirectResponse(url="/history", status_code=303)


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    """Published post history."""
    from storage.bigquery import list_pipelines

    published = list_pipelines(status="published")
    return templates.TemplateResponse(
        "history.html", {"request": request, "pipelines": published}
    )


# --- Manual Content Creation ---


@app.get("/create", response_class=HTMLResponse)
async def create_form(request: Request):
    """Render the manual content creation form."""
    return templates.TemplateResponse(
        "create.html", {"request": request}
    )


@app.post("/create")
async def create_post(
    request: Request,
    input_type: str = Form(...),
    url: str = Form(""),
    text: str = Form(""),
    title: str = Form(""),
):
    """Process manual content input → ContentProcessor → Editor → BigQuery."""
    from datetime import UTC, datetime

    from agents.content_processor import ContentProcessor
    from agents.editor import EditorAgent
    from models.schemas import ContentPipeline
    from storage.bigquery import store_pipeline

    try:
        processor = ContentProcessor()

        if input_type == "url":
            if not url.strip():
                return templates.TemplateResponse(
                    "create.html",
                    {"request": request, "error": "Please enter a URL."},
                )
            scout_report = processor.process_url(url.strip())
        else:
            if not text.strip():
                return templates.TemplateResponse(
                    "create.html",
                    {"request": request, "error": "Please enter some content."},
                )
            scout_report = processor.process_text(
                text.strip(), title=title.strip() or None
            )

        # Generate drafts using the existing Editor agent
        editor = EditorAgent()
        editor_output = editor.write(scout_report)

        # Store in BigQuery for review
        pipeline = ContentPipeline(
            id=str(uuid.uuid4()),
            created_at=datetime.now(UTC),
            scout_output=scout_report,
            editor_output=editor_output,
            status="draft",
        )
        store_pipeline(pipeline)

        logger.info(f"Manual pipeline {pipeline.id} created")
        return RedirectResponse(
            url=f"/review/{pipeline.id}", status_code=303
        )

    except ValueError as e:
        return templates.TemplateResponse(
            "create.html",
            {"request": request, "error": str(e)},
        )
    except Exception as e:
        logger.error(f"Manual content creation failed: {e}", exc_info=True)
        return templates.TemplateResponse(
            "create.html",
            {
                "request": request,
                "error": "Something went wrong. Please try again.",
            },
        )


# --- LinkedIn OAuth ---


@app.get("/auth/linkedin")
async def linkedin_auth(request: Request):
    """Redirect to LinkedIn OAuth authorization page."""
    from agents.publisher import LinkedInPublisher

    state = str(uuid.uuid4())
    request.session["oauth_state"] = state
    publisher = LinkedInPublisher()
    auth_url = publisher.get_authorization_url(state)
    return RedirectResponse(url=auth_url)


@app.get("/auth/linkedin/callback")
async def linkedin_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    """Handle LinkedIn OAuth callback — exchange code for token."""
    if error:
        return HTMLResponse(
            f"<h1>LinkedIn Auth Error</h1><p>{error}</p>"
            '<p><a href="/">Back to Dashboard</a></p>'
        )

    stored_state = request.session.get("oauth_state")
    if state != stored_state:
        raise HTTPException(status_code=401, detail="CSRF state mismatch")

    if not code:
        raise HTTPException(
            status_code=400, detail="No authorization code received"
        )

    from agents.publisher import LinkedInPublisher

    publisher = LinkedInPublisher()
    await publisher.exchange_code_for_token(code)

    return HTMLResponse(
        "<h1>LinkedIn Connected</h1>"
        "<p>Access token stored in Secret Manager. You can now publish posts.</p>"
        '<p><a href="/">Back to Dashboard</a></p>'
    )


# --- Health Check ---


@app.get("/health")
async def health():
    """Health check endpoint for Cloud Run."""
    return {"status": "ok"}
