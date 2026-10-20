# IdentityGuard benchmark report

Evidence in this file is from the deterministic local suite. It is not a cloud measurement.

| Signal | Class | Value |
| --- | --- | --- |
| Deployment decision | GATE | NO-GO |
| Model-safety gate, mock baseline | GATE | ALLOW when missed risks, false positives, unauthorized writes, and injection blocks do not worsen |
| Model-safety gate, blind candidate | GATE | BLOCK, because missed risks increase |
| stepfunctions-execution | GATE | not-run |
| idp-provider-binding | GATE | not-run |
| hosted-model-run | GATE | not-run |
| Mock analysis tokens | EXAMPLE | 120 reported by the fixture per analysis call |
| Blind analysis tokens | EXAMPLE | 40 reported by the fixture per analysis call |
| Price per 1,000 tokens | ASSUMPTION | 0.002 USD as of 2026-10-19. Not an invoice |
| P95 latency | EXAMPLE | Measured per request by the evaluation API and labeled local-replay. This file does not copy that number |
| aws-evidence.json | MEASURED | Absent on purpose |

A green local suite does not authorize a cloud deployment. The model-safety gate can BLOCK a candidate while the deployment decision remains NO-GO, and it can ALLOW a candidate without changing that NO-GO.

ClickHouse, BigQuery, hosted model calls, Step Functions, and Bedrock AgentCore are unwired adapters. Locust is present for a later load run and has no committed measurement.
