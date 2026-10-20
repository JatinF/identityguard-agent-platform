# External evidence

`aws-evidence.json` is the only file that can move an external gate from `not-run` to `pass`. It is absent in this repository on purpose. The published decision stays **NO-GO** until that file exists for the account under test and every required row is a `MEASURED` pass.

Do not commit a filled copy from a laptop, from the local replay, or from a mocked execution ARN. `tests/test_platform.py` fails if `benchmarks/aws-evidence.json` is present, and it fails if the acceptance report says GO while this file is missing.

## Record shape

```json
{
  "records": [
    {
      "test_id": "stepfunctions-execution",
      "evidence_class": "MEASURED",
      "result": "pass",
      "serials": ["execution ARN"],
      "log": "path or artifact name of the execution log"
    }
  ]
}
```

Required `test_id` values:

| test_id | What a pass means |
| --- | --- |
| `stepfunctions-execution` | The state machine in `deploy/stepfunctions` ran in the account under test and the log shows a denied path closing without Execute |
| `idp-provider-binding` | The dev token map was replaced by the site identity provider and a tenant-bound principal was recorded |
| `hosted-model-run` | A hosted model call, if the site enables one, was traced with identity attributes removed and the policy gate still in front |

Each passing row needs `evidence_class` = `MEASURED`, `result` = `pass`, a non-empty `serials` list, and a `log`. A row that is present and fails any of those checks is a fail. A missing row is `not-run`. Either one keeps the decision at NO-GO.

The local replay in `evals/replay-report.md` is a separate record. It does not fill these rows.
