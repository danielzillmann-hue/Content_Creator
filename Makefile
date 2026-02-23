# AI Content Engine - Deployment Makefile
PROJECT_ID := dan-sandpit
REGION := us-central1
SA_EMAIL := content-engine-sa@$(PROJECT_ID).iam.gserviceaccount.com
DASHBOARD_IMAGE := gcr.io/$(PROJECT_ID)/content-engine-dashboard

.PHONY: help setup deploy-dashboard deploy-functions deploy-scheduler deploy-all test lint local-dashboard local-pipeline

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

setup:  ## Enable GCP APIs and create service account
	gcloud config set project $(PROJECT_ID)
	gcloud services enable \
		aiplatform.googleapis.com \
		cloudfunctions.googleapis.com \
		secretmanager.googleapis.com \
		run.googleapis.com \
		cloudscheduler.googleapis.com \
		bigquery.googleapis.com \
		cloudbuild.googleapis.com
	-gcloud iam service-accounts create content-engine-sa \
		--display-name="AI Content Engine SA"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) \
		--member="serviceAccount:$(SA_EMAIL)" \
		--role="roles/aiplatform.user"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) \
		--member="serviceAccount:$(SA_EMAIL)" \
		--role="roles/secretmanager.secretAccessor"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) \
		--member="serviceAccount:$(SA_EMAIL)" \
		--role="roles/bigquery.dataEditor"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) \
		--member="serviceAccount:$(SA_EMAIL)" \
		--role="roles/bigquery.jobUser"

setup-bq:  ## Create BigQuery dataset and table
	-bq mk --dataset --location=US $(PROJECT_ID):content_engine
	-bq mk --table $(PROJECT_ID):content_engine.post_history \
		id:STRING,created_at:TIMESTAMP,scout_output:STRING,editor_output:STRING,\
		status:STRING,linkedin_result:STRING,medium_result:STRING,\
		approved_by:STRING,approved_at:TIMESTAMP

setup-secrets:  ## Create Secret Manager entries (add values manually)
	-gcloud secrets create linkedin-client-id --replication-policy="automatic"
	-gcloud secrets create linkedin-client-secret --replication-policy="automatic"
	-gcloud secrets create linkedin-access-token --replication-policy="automatic"
	-gcloud secrets create medium-integration-token --replication-policy="automatic"
	@echo ""
	@echo "Now add secret values:"
	@echo "  echo -n 'VALUE' | gcloud secrets versions add linkedin-client-id --data-file=-"
	@echo "  echo -n 'VALUE' | gcloud secrets versions add linkedin-client-secret --data-file=-"
	@echo "  echo -n 'VALUE' | gcloud secrets versions add medium-integration-token --data-file=-"

deploy-dashboard:  ## Deploy approval dashboard to Cloud Run
	gcloud builds submit --tag $(DASHBOARD_IMAGE) .
	gcloud run deploy content-engine-dashboard \
		--image $(DASHBOARD_IMAGE) \
		--platform managed \
		--region $(REGION) \
		--allow-unauthenticated \
		--set-env-vars="GCP_PROJECT=$(PROJECT_ID),GCP_REGION=$(REGION)"

deploy-functions:  ## Deploy Cloud Functions (pipeline + publish)
	gcloud functions deploy content-engine-pipeline \
		--gen2 \
		--runtime python311 \
		--region $(REGION) \
		--source . \
		--entry-point run_pipeline \
		--trigger-http \
		--memory 512MB \
		--timeout 300s \
		--service-account $(SA_EMAIL) \
		--set-env-vars="GCP_PROJECT=$(PROJECT_ID),GCP_REGION=$(REGION)"
	gcloud functions deploy content-engine-publish \
		--gen2 \
		--runtime python311 \
		--region $(REGION) \
		--source . \
		--entry-point publish \
		--trigger-http \
		--memory 256MB \
		--timeout 120s \
		--service-account $(SA_EMAIL) \
		--set-env-vars="GCP_PROJECT=$(PROJECT_ID),GCP_REGION=$(REGION)"

deploy-scheduler:  ## Create Cloud Scheduler job (daily 7am AEST)
	-gcloud scheduler jobs create http content-engine-daily \
		--schedule="0 7 * * *" \
		--time-zone="Australia/Sydney" \
		--location=$(REGION) \
		--uri="$$(gcloud functions describe content-engine-pipeline --gen2 --region=$(REGION) --format='value(serviceConfig.uri)')" \
		--http-method=POST \
		--oidc-service-account-email=$(SA_EMAIL)

deploy-all: deploy-dashboard deploy-functions deploy-scheduler  ## Deploy everything

test:  ## Run tests
	python -m pytest tests/ -v

lint:  ## Run linting
	python -m flake8 agents/ config/ models/ storage/ dashboard/ main.py \
		--max-line-length=120 --exclude=__pycache__

local-dashboard:  ## Run dashboard locally on port 8080
	uvicorn dashboard.app:app --reload --port 8080

local-pipeline:  ## Run scout+editor pipeline locally (prints result)
	python -c "\
from agents.scout import ScoutAgent; \
from agents.editor import EditorAgent; \
scout = ScoutAgent(); \
report = scout.search(); \
print(f'Scout found {len(report.items)} items'); \
editor = EditorAgent(); \
output = editor.write(report); \
print('--- LinkedIn ---'); \
print(output.linkedin_draft.content); \
print('--- Medium ---'); \
print(output.medium_draft.content_markdown[:500])"
