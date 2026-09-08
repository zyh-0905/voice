# VoiceLens API

FastAPI service for the VoiceLens data-governance MVP. The interactive contract is available at `/docs`; the machine-readable OpenAPI document is `/openapi.json`.

## Running

```bash
PYTHONPATH=services/api uvicorn app.main:app --reload --port 8000
```

By default the demo uses an in-memory repository. Set `USE_DATABASE=true` and
`DATABASE_URL` to use SQLAlchemy (run migrations before production use). Set
`RUN_WORKER_INLINE=true` only for local demos; production deployments should
dispatch analysis jobs to the worker queue.

## Authentication and tenancy

The MVP does not validate tokens yet. Integrations should send `Authorization:
Bearer <token>` and bind every request to the authenticated project. The review
confirmation endpoint also accepts `X-Role`; `VIEWER` receives `403`, while
analyst/admin roles may confirm. Treat this header as a demo shim, not a
production authorization mechanism.

## Endpoints

All paths are rooted at `/api/v1` and project resources are tenant-scoped.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET | `/health` | Service health | 200 |
| GET | `/projects` | List projects | 200 |
| GET | `/projects/{project_id}` | Project details | 200 |
| POST | `/projects/{project_id}/datasets` | Multipart upload (`file`, `consent=true`; optional `name`, `source_namespace`, `source_kind`) | 201 |
| GET | `/projects/{project_id}/datasets` | List datasets | 200 |
| POST | `/projects/{project_id}/datasets/{dataset_id}/validate` | Validate and increment dataset version | 202 |
| POST | `/projects/{project_id}/analyses` | Create analysis (`dataset_ids`, optional `config`) | 202 |
| GET | `/projects/{project_id}/analyses` | List analysis runs | 200 |
| GET | `/projects/{project_id}/analyses/{analysis_id}` | Analysis status/results | 200 |
| POST | `/projects/{project_id}/analyses/{analysis_id}/retry` | Retry failed/cancelled run | 200 |
| POST | `/projects/{project_id}/analyses/{analysis_id}/cancel` | Cancel queued/running run | 200 |
| GET | `/projects/{project_id}/risks` | List risk findings | 200 |
| GET | `/projects/{project_id}/tasks` | List follow-up tasks | 200 |
| GET | `/projects/{project_id}/reviews` | List review items | 200 |
| POST | `/projects/{project_id}/reviews/{review_id}/confirm` | Confirm a finding | 200 |
| GET | `/projects/{project_id}/exports/redacted.csv` | Download redacted CSV | 200 (`text/csv`) |

Upload accepts `txt`, `csv`, `xls`, and `xlsx` extensions, with a 50 MiB limit.
CSV/TXT ingestion is deterministic and masks email, phone, and order-number
patterns. XLS/XLSX validation currently returns `unsupported_file_type`.

## Error codes

Errors are JSON `{"detail":{"code":"..."}}`; clients should branch on the
stable `code`, not localized messages.

`consent_required` (422), `unsupported_file_type` (422), `file_too_large` (413),
`dataset_not_found` (404), `dataset_not_ready` (422), `version_conflict` (409),
`analysis_not_found` (404), `analysis_not_retryable` (409),
`review_not_found` (404), and `forbidden` (403) are currently emitted.

Demo responses may contain synthetic projects, risks, tasks, and reviews. They
must not be presented as production evidence; production mode must replace the
repository and worker configuration and enforce real authentication.
