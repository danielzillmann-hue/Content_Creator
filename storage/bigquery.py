"""
BigQuery storage layer for post history.

CRUD operations on the content_engine.post_history table.
Stores the full pipeline state: scout output, editor drafts, publish results.
"""
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Optional

from google.cloud import bigquery

from config.settings import settings
from models.schemas import ContentPipeline

logger = logging.getLogger(__name__)

# Full table ID
TABLE_ID = f"{settings.GCP_PROJECT}.{settings.BQ_DATASET}.{settings.BQ_TABLE}"


def _get_client() -> bigquery.Client:
    """Get a BigQuery client using default credentials."""
    return bigquery.Client(project=settings.GCP_PROJECT)


def store_pipeline(pipeline: ContentPipeline) -> str:
    """
    Store a new pipeline record in BigQuery.

    Args:
        pipeline: The ContentPipeline to store.

    Returns:
        The pipeline ID.
    """
    client = _get_client()

    row = {
        "id": pipeline.id,
        "created_at": pipeline.created_at.isoformat(),
        "scout_output": pipeline.scout_output.model_dump_json()
        if pipeline.scout_output
        else None,
        "editor_output": pipeline.editor_output.model_dump_json()
        if pipeline.editor_output
        else None,
        "status": pipeline.status,
        "linkedin_result": pipeline.linkedin_result.model_dump_json()
        if pipeline.linkedin_result
        else None,
        "medium_result": pipeline.medium_result.model_dump_json()
        if pipeline.medium_result
        else None,
        "approved_by": pipeline.approved_by,
        "approved_at": pipeline.approved_at.isoformat()
        if pipeline.approved_at
        else None,
    }

    try:
        errors = client.insert_rows_json(TABLE_ID, [row])
        if errors:
            logger.error(f"BigQuery insert errors: {errors}")
            raise RuntimeError(f"Failed to insert pipeline: {errors}")
        logger.info(f"Pipeline {pipeline.id} stored in BigQuery")
        return pipeline.id
    except Exception as e:
        logger.error(f"Failed to store pipeline: {e}", exc_info=True)
        raise


def get_pipeline(pipeline_id: str) -> Optional[ContentPipeline]:
    """
    Retrieve a pipeline record by ID.

    Args:
        pipeline_id: The pipeline UUID.

    Returns:
        ContentPipeline if found, None otherwise.
    """
    client = _get_client()
    query = f"""
        SELECT *
        FROM `{TABLE_ID}`
        WHERE id = @pipeline_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("pipeline_id", "STRING", pipeline_id)
        ]
    )

    try:
        results = client.query(query, job_config=job_config).result()
        for row in results:
            return _row_to_pipeline(row)
        return None
    except Exception as e:
        logger.error(f"Failed to get pipeline {pipeline_id}: {e}", exc_info=True)
        return None


def list_pipelines(
    status: Optional[str] = None, limit: int = 20
) -> list[ContentPipeline]:
    """
    List pipeline records, optionally filtered by status.

    Args:
        status: Filter by status ("draft", "approved", "rejected", "published").
        limit: Maximum number of records to return.

    Returns:
        List of ContentPipeline records, newest first.
    """
    client = _get_client()

    if status:
        query = f"""
            SELECT *
            FROM `{TABLE_ID}`
            WHERE status = @status
            ORDER BY created_at DESC
            LIMIT @limit
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("status", "STRING", status),
                bigquery.ScalarQueryParameter("limit", "INT64", limit),
            ]
        )
    else:
        query = f"""
            SELECT *
            FROM `{TABLE_ID}`
            ORDER BY created_at DESC
            LIMIT @limit
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("limit", "INT64", limit),
            ]
        )

    try:
        results = client.query(query, job_config=job_config).result()
        return [_row_to_pipeline(row) for row in results]
    except Exception as e:
        logger.error(f"Failed to list pipelines: {e}", exc_info=True)
        return []


def update_pipeline_status(
    pipeline_id: str,
    status: str,
    publish_results: Optional[dict] = None,
    approved_by: str = "",
) -> None:
    """
    Update a pipeline's status and optionally its publish results.

    Args:
        pipeline_id: The pipeline UUID.
        status: New status value.
        publish_results: Optional dict with "linkedin" and/or "medium" results.
        approved_by: Who approved (for audit trail).
    """
    client = _get_client()

    set_clauses = ["status = @status"]
    params = [
        bigquery.ScalarQueryParameter("status", "STRING", status),
        bigquery.ScalarQueryParameter("pipeline_id", "STRING", pipeline_id),
    ]

    if approved_by:
        set_clauses.append("approved_by = @approved_by")
        set_clauses.append("approved_at = @approved_at")
        params.append(
            bigquery.ScalarQueryParameter("approved_by", "STRING", approved_by)
        )
        params.append(
            bigquery.ScalarQueryParameter(
                "approved_at", "STRING", datetime.now(UTC).isoformat()
            )
        )

    if publish_results:
        if "linkedin" in publish_results:
            set_clauses.append("linkedin_result = @linkedin_result")
            params.append(
                bigquery.ScalarQueryParameter(
                    "linkedin_result", "STRING", json.dumps(publish_results["linkedin"])
                )
            )
        if "medium" in publish_results:
            set_clauses.append("medium_result = @medium_result")
            params.append(
                bigquery.ScalarQueryParameter(
                    "medium_result", "STRING", json.dumps(publish_results["medium"])
                )
            )

    query = f"""
        UPDATE `{TABLE_ID}`
        SET {', '.join(set_clauses)}
        WHERE id = @pipeline_id
    """
    job_config = bigquery.QueryJobConfig(query_parameters=params)

    try:
        client.query(query, job_config=job_config).result()
        logger.info(f"Pipeline {pipeline_id} updated to status={status}")
    except Exception as e:
        logger.error(
            f"Failed to update pipeline {pipeline_id}: {e}", exc_info=True
        )
        raise


def update_pipeline_content(
    pipeline_id: str,
    linkedin_content: Optional[str] = None,
    medium_content: Optional[str] = None,
) -> None:
    """
    Update the editor output content (after user edits in dashboard).

    Args:
        pipeline_id: The pipeline UUID.
        linkedin_content: Updated LinkedIn post text.
        medium_content: Updated Medium article markdown.
    """
    pipeline = get_pipeline(pipeline_id)
    if not pipeline or not pipeline.editor_output:
        return

    if linkedin_content:
        pipeline.editor_output.linkedin_draft.content = linkedin_content
    if medium_content:
        pipeline.editor_output.medium_draft.content_markdown = medium_content

    client = _get_client()
    query = f"""
        UPDATE `{TABLE_ID}`
        SET editor_output = @editor_output
        WHERE id = @pipeline_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "editor_output", "STRING", pipeline.editor_output.model_dump_json()
            ),
            bigquery.ScalarQueryParameter("pipeline_id", "STRING", pipeline_id),
        ]
    )

    try:
        client.query(query, job_config=job_config).result()
        logger.info(f"Pipeline {pipeline_id} content updated")
    except Exception as e:
        logger.error(f"Failed to update content: {e}", exc_info=True)


def _row_to_pipeline(row: bigquery.Row) -> ContentPipeline:
    """Convert a BigQuery row to a ContentPipeline model."""
    from models.schemas import EditorOutput, PublishResult, ScoutReport

    scout_output = None
    if row.get("scout_output"):
        scout_output = ScoutReport.model_validate_json(row["scout_output"])

    editor_output = None
    if row.get("editor_output"):
        editor_output = EditorOutput.model_validate_json(row["editor_output"])

    linkedin_result = None
    if row.get("linkedin_result"):
        linkedin_result = PublishResult.model_validate_json(row["linkedin_result"])

    medium_result = None
    if row.get("medium_result"):
        medium_result = PublishResult.model_validate_json(row["medium_result"])

    return ContentPipeline(
        id=row["id"],
        created_at=row["created_at"],
        scout_output=scout_output,
        editor_output=editor_output,
        status=row["status"],
        linkedin_result=linkedin_result,
        medium_result=medium_result,
        approved_by=row.get("approved_by", ""),
        approved_at=row.get("approved_at"),
    )
