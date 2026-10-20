# Architecture

A security operator asks the agent to investigate a suspicious login for the synthetic employee Alex Rivera, decide whether the account should be suspended, and request approval before any write.

The running path is local:

1. FastAPI authenticates a bearer token and copies tenant and role from that token. A tenant field on the body is ignored.
2. The LangGraph investigation loads tenant-scoped evidence, asks the model for a structured recommendation, and checks policy in process.
3. A high-risk recommendation pauses in `AWAITING_APPROVAL`. The approval row stores the requester, the exact argument fingerprint, the expiry, and later the approver and the decision.
4. Resume or a decision loads the checkpoint and calls `reauthorize` again. Expiry, rejection, self-approval, and a fingerprint mismatch stop the graph before the tool.
5. After a suspend call, the harness rereads the account. Completion is claimed only when the reread shows `suspended`.

## Modules

| Module | Path | What the demo actually does |
| --- | --- | --- |
| Durable harness | `src/identityguard/harness/` | Plan, tool choice, checkpoint, context compaction, retry, idempotency |
| Identity and policy | `src/identityguard/identity/` | Mock directory, server-side authorization, suspend, provision, verification |
| Approval | approval node and `/v1/approvals/{id}/decision` | Persist and re-check the human decision |
| Evidence and memory | `src/identityguard/storage/` | SQLite for runs. PostgreSQL with forced row-level security when `DATABASE_URL` is set |
| Verified action | `src/identityguard/identity/verification.py` | Independent reread. `UNVERIFIED` does not complete |
| Evaluation | `src/identityguard/evaluations/` | Synthetic cases, replay, model-safety gate |
| Telemetry | `src/identityguard/telemetry/` | In-process traces and Prometheus counters |

## Stores

Pytest and the API use SQLite for workflow rows and a SQLite LangGraph checkpoint. That is enough to kill the process and resume without a second suspend. PostgreSQL with pgvector is the row-level security demonstration. `PostgresStore` sets `identityguard.tenant` and forces policies on identities, evidence, and embeddings. The API process does not move its run store onto PostgreSQL.

The embedding function is a deterministic 8-float hash. It is not a hosted embedding model.

## Models

`MODEL_PROVIDER=mock` is the default. The mock cites only suspicious-login evidence that was retrieved for the subject. Hosted adapters exist for xAI (`XAI_API_KEY`, `https://api.x.ai/v1/chat/completions`, model `grok-4.7`), OpenAI, and Anthropic. They fail closed when the key is missing or the call times out. The Bedrock adapter does not invoke a model. Tests inject a transport and do not open a network connection.

## Workflow adapters

Step Functions, Bedrock AgentCore, the Codex SDK, ClickHouse, and BigQuery are documented slots. They are not called. OPA is not wired. The policy that runs is `identityguard.identity.authorization`.
