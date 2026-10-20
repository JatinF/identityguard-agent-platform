# IdentityGuard AI — Secure Enterprise Agent Harness & Evaluation Platform

An open-source reference implementation of long-running, identity-aware AI agents that execute enterprise workflows safely, recover from interruptions, and verify outcomes.

Production-oriented Python agent harness with LangGraph, AWS Step Functions, policy-gated tool execution, tenant-isolated memory, human approvals, replayable evaluations, and verified enterprise identity operations.

The executable slice is:

synthetic identity request → policy gate → approval interrupt → tool → postcondition check → tenant memory and audit.

Accounts are fixtures. Identifiers look like `SYN-USER-014` and `SYN-REQ-100`. The seed file declares `real_accounts: 0`. The harness is not an identity provider.

**Deployment decision: NO-GO.** Step Functions has not been executed, the dev tokens have not been replaced by a site identity provider, and no hosted model has been called. The report is [`acceptance/deployment-acceptance.md`](acceptance/deployment-acceptance.md).

| | |
| --- | --- |
| Package | `identityguard` |
| Graph | LangGraph 1.2.16, SQLite checkpoint |
| Tools | lookup, disable, grant-role, export-audit |
| Approval | A different approver in the same tenant, interrupt and resume |
| Evaluation | 10 golden cases, replayed from [`evals/cases.json`](evals/cases.json) |
| AWS | State machine and IAM documents for account `000000000000` |
| Decision | NO-GO until measured external evidence exists |

## How this sits with the other references

| | [H100 GPU factory](https://github.com/JatinF/h100-ai-factory-reference-architecture) | [Healthcare AI factory](https://github.com/JatinF/healthcare-ai-factory-platform) | This repository |
| --- | --- | --- | --- |
| Focus | GPU infrastructure acceptance | Imaging and private clinical inference | Identity-aware agent control |
| Outcome | Design and gates for the cluster | Synthetic imaging service path | Synthetic identity workflow with a durable pause |

Each repository stands on its own evidence. A green replay here does not measure a GPU and does not clear the healthcare acceptance report.

## Evidence

| Tag | Meaning in this repo |
| --- | --- |
| `EXAMPLE` | Synthetic directory and the golden cases |
| `GATE` | Step Functions execution, identity-provider binding, hosted-model trace |
| `MEASURED` | A row in `benchmarks/aws-evidence.json` with an execution identifier and a log |

The local replay is not a `MEASURED` row. Schema: [`benchmarks/README.md`](benchmarks/README.md).

## Run the software slice

Python 3.11 or newer.

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Pytest runs the policy gate, the LangGraph pause and resume, a reopened SQLite checkpoint, tenant isolation, the API, the state-machine checker, and a comparison of the committed reports with the generators. The job in [`.github/workflows/check.yml`](.github/workflows/check.yml) does the same on Ubuntu 24.04 with Python 3.12. That job does not call AWS and does not call a model API.

Regenerate the two committed views after a generator change, then re-run pytest:

```bash
python -c "from pathlib import Path; from identityguard.evals import render_eval, run_suite; from identityguard.acceptance_report import build_report, render_markdown; Path('acceptance').mkdir(exist_ok=True); Path('evals/replay-report.md').write_text(render_eval(run_suite()), encoding='utf-8'); Path('acceptance/deployment-acceptance.md').write_text(render_markdown(build_report(True)), encoding='utf-8')"
```

## API

The default token map is a fixture. A deployment replaces it with the site identity provider.

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
| GET | `/metrics` | Local process counters |
| POST | `/v1/runs` | Start a run. Tenant and role come from the token |
| POST | `/v1/runs/{request_id}/resume` | Approver submits an `APR-` id. The body cannot name the approver |
| GET | `/v1/runs/{request_id}` | Owning tenant only. Another tenant receives 404 |

A missing token returns 401. A body field named `password`, `secret`, `api_key`, `ssn`, or `private_key` returns 422 and the value is not written to the audit log. Policy denials return 200 with `status: denied` and leave the directory unchanged.

## What each control is

| Capability | Where it lives |
| --- | --- |
| Policy-gated tools | [`src/identityguard/policy.py`](src/identityguard/policy.py) |
| Durable pause and resume | LangGraph interrupt plus SQLite, covered by `recovery_check` |
| Tenant-isolated memory | [`src/identityguard/memory.py`](src/identityguard/memory.py) |
| Human approval | Resume route and the self-approval deny |
| Replayable evaluation | [`evals/replay-report.md`](evals/replay-report.md) |
| Verified outcome | Postcondition check after the tool, containment check on deny |
| Step Functions shape | [`deploy/stepfunctions/identity-workflow.asl.json`](deploy/stepfunctions/identity-workflow.asl.json) |
| Least-privilege IAM document | [`deploy/iam/tool-role.json`](deploy/iam/tool-role.json) |
| Threat model, SLOs, runbooks | [`docs`](docs) |

The path is drawn in [`docs/architecture.md`](docs/architecture.md).

## Model slot

The tool name comes from the operation field. A sentence in `justification` cannot select a different tool. This reference does not send identity attributes to a hosted model. If a site later adds one, the supported provider slot is xAI: environment variable `XAI_API_KEY`, base URL `https://api.x.ai/v1`, called only from the server side, and only after the same policy gate. That call is not implemented. The `hosted-model-run` gate stays `not-run`.

## License

MIT. Copyright 2026 Jatinder Singh.
