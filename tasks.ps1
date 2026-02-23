# AI Content Engine - Task Runner (PowerShell)
# Usage: .\tasks.ps1 <command>
#
# Commands:
#   setup              Enable GCP APIs and create service account
#   setup-bq           Create BigQuery dataset and table
#   setup-secrets      Create Secret Manager entries
#   deploy-dashboard   Deploy approval dashboard to Cloud Run
#   deploy-functions   Deploy Cloud Functions
#   deploy-scheduler   Create Cloud Scheduler job (7am AEST daily)
#   deploy-all         Deploy everything
#   test               Run tests
#   lint               Run linting
#   local-dashboard    Run dashboard locally on port 8080
#   local-pipeline     Run scout+editor pipeline locally
#   help               Show this help

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

$PROJECT_ID = "dan-sandpit"
$REGION = "us-central1"
$SA_EMAIL = "content-engine-sa@$PROJECT_ID.iam.gserviceaccount.com"
$DASHBOARD_IMAGE = "gcr.io/$PROJECT_ID/content-engine-dashboard"

function Show-Help {
    Write-Host ""
    Write-Host "AI Content Engine - Available Commands:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  setup              " -NoNewline -ForegroundColor Yellow; Write-Host "Enable GCP APIs and create service account"
    Write-Host "  setup-bq           " -NoNewline -ForegroundColor Yellow; Write-Host "Create BigQuery dataset and table"
    Write-Host "  setup-secrets      " -NoNewline -ForegroundColor Yellow; Write-Host "Create Secret Manager entries"
    Write-Host "  deploy-dashboard   " -NoNewline -ForegroundColor Yellow; Write-Host "Deploy dashboard to Cloud Run"
    Write-Host "  deploy-functions   " -NoNewline -ForegroundColor Yellow; Write-Host "Deploy Cloud Functions"
    Write-Host "  deploy-scheduler   " -NoNewline -ForegroundColor Yellow; Write-Host "Create Cloud Scheduler job"
    Write-Host "  deploy-all         " -NoNewline -ForegroundColor Yellow; Write-Host "Deploy everything"
    Write-Host "  test               " -NoNewline -ForegroundColor Yellow; Write-Host "Run tests"
    Write-Host "  lint               " -NoNewline -ForegroundColor Yellow; Write-Host "Run linting"
    Write-Host "  local-dashboard    " -NoNewline -ForegroundColor Yellow; Write-Host "Run dashboard locally"
    Write-Host "  local-pipeline     " -NoNewline -ForegroundColor Yellow; Write-Host "Run scout+editor pipeline locally"
    Write-Host ""
}

function Invoke-Setup {
    Write-Host "Setting up GCP project..." -ForegroundColor Cyan
    gcloud config set project $PROJECT_ID
    gcloud services enable `
        aiplatform.googleapis.com `
        cloudfunctions.googleapis.com `
        secretmanager.googleapis.com `
        run.googleapis.com `
        cloudscheduler.googleapis.com `
        bigquery.googleapis.com `
        cloudbuild.googleapis.com

    Write-Host "Creating service account..." -ForegroundColor Cyan
    gcloud iam service-accounts create content-engine-sa `
        --display-name="AI Content Engine SA" 2>$null

    $roles = @(
        "roles/aiplatform.user",
        "roles/secretmanager.secretAccessor",
        "roles/bigquery.dataEditor",
        "roles/bigquery.jobUser"
    )
    foreach ($role in $roles) {
        Write-Host "  Granting $role..." -ForegroundColor Gray
        gcloud projects add-iam-policy-binding $PROJECT_ID `
            --member="serviceAccount:$SA_EMAIL" `
            --role=$role --condition=None --quiet 2>$null | Out-Null
    }
    Write-Host "Setup complete." -ForegroundColor Green
}

function Invoke-SetupBQ {
    Write-Host "Creating BigQuery resources..." -ForegroundColor Cyan
    bq mk --dataset --location=US "${PROJECT_ID}:content_engine" 2>$null
    bq mk --table "${PROJECT_ID}:content_engine.post_history" `
        "id:STRING,created_at:TIMESTAMP,scout_output:STRING,editor_output:STRING,status:STRING,linkedin_result:STRING,medium_result:STRING,approved_by:STRING,approved_at:TIMESTAMP" 2>$null
    Write-Host "BigQuery setup complete." -ForegroundColor Green
}

function Invoke-SetupSecrets {
    Write-Host "Creating Secret Manager entries..." -ForegroundColor Cyan
    $secrets = @("linkedin-client-id", "linkedin-client-secret", "linkedin-access-token", "medium-integration-token")
    foreach ($secret in $secrets) {
        gcloud secrets create $secret --replication-policy="automatic" --project=$PROJECT_ID 2>$null
    }
    Write-Host ""
    Write-Host "Secrets created. Add values with:" -ForegroundColor Yellow
    Write-Host '  echo -n "VALUE" | gcloud secrets versions add linkedin-client-id --data-file=-'
    Write-Host '  echo -n "VALUE" | gcloud secrets versions add linkedin-client-secret --data-file=-'
    Write-Host '  echo -n "VALUE" | gcloud secrets versions add medium-integration-token --data-file=-'
}

function Invoke-DeployDashboard {
    Write-Host "Deploying dashboard to Cloud Run..." -ForegroundColor Cyan
    gcloud builds submit --tag $DASHBOARD_IMAGE .
    gcloud run deploy content-engine-dashboard `
        --image $DASHBOARD_IMAGE `
        --platform managed `
        --region $REGION `
        --allow-unauthenticated `
        --set-env-vars="GCP_PROJECT=$PROJECT_ID,GCP_REGION=$REGION"
}

function Invoke-DeployFunctions {
    Write-Host "Deploying Cloud Functions..." -ForegroundColor Cyan

    Write-Host "  Deploying pipeline function..." -ForegroundColor Gray
    gcloud functions deploy content-engine-pipeline `
        --gen2 `
        --runtime python311 `
        --region $REGION `
        --source . `
        --entry-point run_pipeline `
        --trigger-http `
        --memory 512MB `
        --timeout 300s `
        --service-account $SA_EMAIL `
        --set-env-vars="GCP_PROJECT=$PROJECT_ID,GCP_REGION=$REGION"

    Write-Host "  Deploying publish function..." -ForegroundColor Gray
    gcloud functions deploy content-engine-publish `
        --gen2 `
        --runtime python311 `
        --region $REGION `
        --source . `
        --entry-point publish `
        --trigger-http `
        --memory 256MB `
        --timeout 120s `
        --service-account $SA_EMAIL `
        --set-env-vars="GCP_PROJECT=$PROJECT_ID,GCP_REGION=$REGION"
}

function Invoke-DeployScheduler {
    Write-Host "Creating Cloud Scheduler job..." -ForegroundColor Cyan
    $uri = gcloud functions describe content-engine-pipeline --gen2 --region=$REGION --format="value(serviceConfig.uri)"
    gcloud scheduler jobs create http content-engine-daily `
        --schedule="0 7 * * *" `
        --time-zone="Australia/Sydney" `
        --location=$REGION `
        --uri=$uri `
        --http-method=POST `
        --oidc-service-account-email=$SA_EMAIL
}

function Invoke-DeployAll {
    Invoke-DeployDashboard
    Invoke-DeployFunctions
    Invoke-DeployScheduler
    Write-Host "All deployments complete." -ForegroundColor Green
}

function Invoke-Test {
    python -m pytest tests/ -v
}

function Invoke-Lint {
    python -m flake8 agents/ config/ models/ storage/ dashboard/ main.py --max-line-length=120 --exclude=__pycache__
}

function Invoke-LocalDashboard {
    Write-Host "Starting dashboard at http://localhost:8080 ..." -ForegroundColor Cyan
    uvicorn dashboard.app:app --reload --port 8080
}

function Invoke-LocalPipeline {
    Write-Host "Running pipeline locally..." -ForegroundColor Cyan
    python -c @"
from agents.scout import ScoutAgent
from agents.editor import EditorAgent
scout = ScoutAgent()
report = scout.search()
print(f'Scout found {len(report.items)} items')
editor = EditorAgent()
output = editor.write(report)
print('--- LinkedIn ---')
print(output.linkedin_draft.content)
print('--- Medium (first 500 chars) ---')
print(output.medium_draft.content_markdown[:500])
"@
}

# Command dispatcher
switch ($Command) {
    "setup"            { Invoke-Setup }
    "setup-bq"         { Invoke-SetupBQ }
    "setup-secrets"    { Invoke-SetupSecrets }
    "deploy-dashboard" { Invoke-DeployDashboard }
    "deploy-functions" { Invoke-DeployFunctions }
    "deploy-scheduler" { Invoke-DeployScheduler }
    "deploy-all"       { Invoke-DeployAll }
    "test"             { Invoke-Test }
    "lint"             { Invoke-Lint }
    "local-dashboard"  { Invoke-LocalDashboard }
    "local-pipeline"   { Invoke-LocalPipeline }
    "help"             { Show-Help }
    default            { Write-Host "Unknown command: $Command" -ForegroundColor Red; Show-Help }
}
