# IdentityGuard AI — Secure Enterprise Agent Harness & Evaluation Platform

An open-source, production-oriented reference implementation for reliable, identity-aware digital workers.

Python/FastAPI agent harness with LangGraph, durable execution, tenant-isolated memory, policy-gated identity operations, human approvals, verified tool outcomes, and replayable LLM security evaluations.

A security operator asks the agent to investigate the suspicious login for synthetic employee Alex Rivera, decide whether the account should be suspended, and request approval before taking action. The agent retrieves fixture evidence, proposes a suspend, and stops in `AWAITING_APPROVAL`. A rejected approval, an expired approval, a failed policy check, or a reread that does not show `suspended` ends the workflow. Those endings do not claim completion.

Accounts are fixtures. Identifiers look like `SYN-USER-ALEX`. The seed file declares `real_accounts: 0`. This package is not an identity provider.

**Deployment decision: NO-GO.** Step Functions has not been executed, the dev tokens have not been replaced, and no hosted model has been called. The model-safety gate is separate: the mock baseline is `ALLOW`, and a candidate that misses more risks is `BLOCK`. Neither result authorizes a cloud deployment. See [docs/production-readiness.md](docs/production-readiness.md) and [benchmarks/benchmark_report.md](benchmarks/benchmark_report.md).

| | |
| --- | --- |
| Package | `identityguard` 0.2.0 |
| API | FastAPI, tenant taken from the bearer token |
| Graph | LangGraph 1.2.16, SQLite checkpoint |
| Directory | Mock provider, two synthetic tenants |
| Approval | Different approver, persisted arguments, expiry, reauthorize on resume |
| Verification | Reread after the tool. `UNVERIFIED` does not complete |
| Evaluation | Golden cases, injection cases, replay, release gate |
| PostgreSQL | Row-level security demonstration when `DATABASE_URL` is set |
| Decision | NO-GO until measured external evidence exists |

## How this sits with the other references

| | [H100 GPU factory](https://github.com/JatinF/h100-ai-factory-reference-architecture) | [Healthcare AI factory](https://github.com/JatinF/healthcare-ai-factory-platform) | This repository |
| --- | --- | --- | --- |
| Focus | GPU infrastructure acceptance | Imaging and private clinical inference | Identity-aware agent control |
| Outcome | Design and gates for the cluster | Synthetic imaging service path | Synthetic investigation with a durable pause |

Each repository stands on its own evidence. A green replay here does not measure a GPU and does not clear the healthcare acceptance report.

## Evidence

| Tag | Meaning in this repo |
| --- | --- |
| `EXAMPLE` | Synthetic directory, golden cases, and local-replay latency |
| `ASSUMPTION` | 0.002 USD per 1,000 tokens, dated 2026-10-19, not an invoice |
| `DERIVED` | A cost computed from fixture token counts and that assumption |
| `GATE` | Model-safety `ALLOW` or `BLOCK`, and the external gates that are `not-run` |
| `MEASURED` | A row in `benchmarks/aws-evidence.json`. That file is absent |

## Run the demo

Python 3.12 or newer.

```bash
python -m pip install -e ".[dev]"
python -m pytest
uvicorn identityguard.api.main:app
```

Pytest uses the mock model and SQLite. It does not call AWS and it does not call a model API. The workflow in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs that suite on Ubuntu 24.04 with Python 3.12, then runs the row-level security test against `pgvector/pgvector:pg16`.

Docker Compose starts the API and a local Postgres. The API run store stays on SQLite under `IG_STATE_DIR`. Postgres is there for the row-level security demonstration. This repository's tests were not executed through Compose.

```bash
docker compose up --build
```

Copy [.env.example](.env.example) only if you want local overrides. Leave hosted API keys unset.

## API

Dev tokens are fixtures. A deployment replaces the map.

| Token | Tenant | Role |
| --- | --- | --- |
| `dev-reader-a` | `tenant-a` | reader |
| `dev-operator-a` | `tenant-a` | operator |
| `dev-approver-a` | `tenant-a` | approver |
| `dev-operator-b` | `tenant-b` | operator |
| `dev-approver-b` | `tenant-b` | approver |

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/healthz` | Process up, `real_accounts` 0 |
| GET | `/metrics` | In-process Prometheus counters |
| POST | `/v1/agents/runs` | Start an investigation. Send `Idempotency-Key` |
| GET | `/v1/agents/runs/{id}` | Owning tenant only. Another tenant receives 404 |
| POST | `/v1/agents/runs/{id}/resume` | Continue a checkpoint. Pending approvals stay pending |
| POST | `/v1/approvals/{id}/decision` | `approved` or `rejected` by a different approver |
| GET | `/v1/identities/{id}` | Read one identity in the caller's tenant |
| GET | `/v1/evaluations/report` | Deterministic metrics, model comparison, and the NO-GO decision |

A missing token returns 401. A body field named `password`, `secret`, `api_key`, `ssn`, or `private_key` returns 400 and the value is not written to the audit log. Policy denials return 200 with `status: DENIED` and leave the account unchanged.

Alex's investigation, from tenant A:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/agents/runs \
  -H "Authorization: Bearer dev-operator-a" \
  -H "Idempotency-Key: alex-1" \
  -H "Content-Type: application/json" \
  -d "{\"subject_id\":\"SYN-USER-ALEX\",\"goal\":\"Investigate the suspicious login for employee Alex Rivera, determine whether the account should be suspended, and request approval before taking action.\"}"
```

## Layout

The harness, identity tools, model adapters, evaluation runner, stores, and telemetry live under `src/identityguard/`. Step Functions is an unexecuted skeleton in `integrations/aws-step-functions/`. Bedrock AgentCore and the Codex SDK are marked unwired. Terraform and Kubernetes manifests are unapplied.

The path and the controls are written out in [docs/architecture.md](docs/architecture.md), [docs/threat-model.md](docs/threat-model.md), [docs/evaluation-methodology.md](docs/evaluation-methodology.md), and [docs/failure-recovery.md](docs/failure-recovery.md).

## Model slot

xAI is the preferred hosted provider when a deployment chooses one: `XAI_API_KEY`, `https://api.x.ai/v1/chat/completions`, model `grok-4.7`. OpenAI and Anthropic adapters implement the same `analyze` contract for a comparison run. Bedrock invoke stays disabled. The default remains the mock, so identity attributes are not sent off the machine. The `hosted-model-run` gate stays `not-run`.

## License

MIT. Copyright 2026 Jatinder Singh.
