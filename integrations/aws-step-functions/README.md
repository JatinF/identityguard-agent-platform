# AWS Step Functions

`definition.asl.json` is an unexecuted skeleton for account `000000000000`.

`WaitForApproval` uses a task token. Its timeout and its catch go to `Close`. `Authorize` and `Reauthorize` default to `Close`. `Execute` is reached only from an `ALLOW` choice. `check.py` enforces that shape and the IAM document. Nothing in this directory has been deployed, and there is no execution id.
