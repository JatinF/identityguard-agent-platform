# Failure and recovery

## Process exit during approval

`POST /v1/agents/runs` writes the run row, then the graph pauses inside the approval node after the approval row is stored. The SQLite checkpoint is on disk. Closing both database connections and opening them again is the crash the resume test uses. The approver's decision runs `reauthorize` before `suspend-account`. The effect row is keyed by the run id, so a second resume does not suspend the account again.

## Repeated events

The same idempotency key and tenant return the original run. A second `approved` decision sees a row that is no longer `pending` and does not invoke the tool again.

## Expired or rejected approval

Expiry is checked before the stored decision. An approver who accepts after `expires_at` still gets `EXPIRED` and no write. A rejection gets `REJECTED` and no write. A resume while the decision is pending and unexpired returns the waiting view and does not execute.

## Model failure

The analyze node retries a timeout or an unavailable model up to three times. If every attempt fails, the run is `FAILED` and the account is unchanged. A model that recovers inside the budget continues into the normal approval pause.

## Unverified write

If the tool reports success and the reread still shows `active`, the run is `UNVERIFIED`. `completion_claimed` stays false. The fixed status text does not describe that outcome as success.

## Evidence that is not on file

A recommendation that cites an evidence id outside the retrieved set is `EVIDENCE_REJECTED` before authorization. No approval row is required and no write occurs.
