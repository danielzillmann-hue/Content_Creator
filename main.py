"""
Cloud Functions entry point for the AI Content Engine.

Two HTTP-triggered functions:
  - run_pipeline: Scout → Editor → BigQuery (status=draft)
  - publish: Reads approved draft → LinkedIn + Medium

Triggered by:
  - Cloud Scheduler (daily at 7am AEST) for run_pipeline
  - Dashboard HTTP POST for publish
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime

import functions_framework
from flask import Request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@functions_framework.http
def run_pipeline(request: Request):
    """
    Main pipeline: Scout → Editor → Store for review.

    Triggered by Cloud Scheduler or manual HTTP POST.
    Optional JSON body: {"topics": ["AI agents", "Gemini"]}
    """
    from agents.editor import EditorAgent
    from agents.scout import ScoutAgent
    from models.schemas import ContentPipeline
    from storage.bigquery import store_pipeline

    try:
        # Parse optional custom topics
        data = request.get_json(silent=True) or {}
        topics = data.get("topics")

        # Step 1: Scout finds trending news
        logger.info("Starting Scout agent...")
        scout = ScoutAgent()
        report = scout.search(topics=topics)
        logger.info(f"Scout found {len(report.items)} items")

        # Step 2: Editor writes drafts
        logger.info("Starting Editor agent...")
        editor = EditorAgent()
        output = editor.write(report)
        logger.info("Editor produced LinkedIn + Medium drafts")

        # Step 3: Store in BigQuery for dashboard review
        pipeline = ContentPipeline(
            id=str(uuid.uuid4()),
            created_at=datetime.now(UTC),
            scout_output=report,
            editor_output=output,
            status="draft",
        )
        store_pipeline(pipeline)
        logger.info(f"Pipeline {pipeline.id} stored for review")

        return jsonify(
            {
                "status": "success",
                "pipeline_id": pipeline.id,
                "items_found": len(report.items),
                "message": "Drafts ready for review in dashboard",
            }
        )

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@functions_framework.http
def publish(request: Request):
    """
    Publish an approved pipeline's content to LinkedIn and/or Medium.

    Called from the dashboard when a user clicks "Approve & Publish".
    JSON body: {"pipeline_id": "uuid", "platforms": ["linkedin", "medium"]}
    """
    from agents.publisher import LinkedInPublisher, MediumPublisher
    from storage.bigquery import get_pipeline, update_pipeline_status

    data = request.get_json(silent=True) or {}
    pipeline_id = data.get("pipeline_id")
    platforms = data.get("platforms", ["linkedin", "medium"])

    if not pipeline_id:
        return jsonify({"error": "pipeline_id required"}), 400

    try:
        pipeline = get_pipeline(pipeline_id)
        if not pipeline:
            return jsonify({"error": "Pipeline not found"}), 404
        if pipeline.status != "approved":
            return jsonify({"error": f"Pipeline status is '{pipeline.status}', not 'approved'"}), 400
        if not pipeline.editor_output:
            return jsonify({"error": "No editor output to publish"}), 400

        results = {}

        if "linkedin" in platforms:
            linkedin = LinkedInPublisher()
            result = asyncio.run(
                linkedin.publish_post(pipeline.editor_output.linkedin_draft)
            )
            results["linkedin"] = result.model_dump(mode="json")

        if "medium" in platforms:
            medium = MediumPublisher()
            result = asyncio.run(
                medium.publish_article(
                    pipeline.editor_output.medium_draft,
                    publish_status="public",
                )
            )
            results["medium"] = result.model_dump(mode="json")

        update_pipeline_status(pipeline_id, "published", results)

        return jsonify({"status": "published", "results": results})

    except Exception as e:
        logger.error(f"Publish failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
