# Production readiness

**Deployment decision: NO-GO.**

| Gate | State | Why |
| --- | --- | --- |
| stepfunctions-execution | not-run | The ASL file has not been started in AWS |
| idp-provider-binding | not-run | Tokens are the dev fixture map |
| hosted-model-run | not-run | The default provider is the mock. Adapters are not called by the tests |
| Measured cloud evidence | absent | `benchmarks/aws-evidence.json` is not in the tree |

A local pytest pass, including the PostgreSQL row-level security test in CI, is not a measured cloud run. The model-safety gate can `ALLOW` the mock baseline or `BLOCK` a weaker candidate without moving this decision off NO-GO.

## What would have to be true later

A GO record would name an execution id, the identity provider that replaced the fixture map, and a hosted-model trace that shows the policy gate still ran on the server. That record would live in `benchmarks/aws-evidence.json` and would be tagged `MEASURED`. This repository does not contain one.

Local PostgreSQL in Docker Compose and the mock directory are enough to run the demo. RDS, Step Functions, AgentCore, ClickHouse, BigQuery, Grafana production series, and a load-test result are adapters or sketches. Locust has no committed numbers. Terraform and the Kubernetes manifest are unapplied.

## SLO language

Do not read the local-replay P95 as a service objective. Do not read the 0.002 USD token assumption as a bill. Completion rate in the evaluation report is the deterministic suite, not production traffic.
