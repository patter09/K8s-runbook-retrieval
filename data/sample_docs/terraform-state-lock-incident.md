# Runbook: Terraform State Lock Stuck

## Symptom
`terraform plan` or `terraform apply` hangs and eventually fails with an
error similar to:
`Error acquiring the state lock ... Lock Info: ID: <lock-id>`

## First checks
1. Confirm no other pipeline run or engineer is actively applying changes
   against the same workspace right now. Check the CI/CD pipeline history
   (Azure DevOps run list) for any in-progress or recently killed job.
2. Identify the backend holding the lock (Azure Storage blob lease, S3 +
   DynamoDB lock table, etc.) and check the lock metadata for `Who` and
   `Created` timestamp.

## Common root causes
- A previous pipeline run was cancelled or the agent died mid-apply,
  leaving the lock held with no process to release it.
- Two pipelines targeting the same workspace ran concurrently because a
  concurrency limit was not configured on the CI trigger.

## Resolution
1. Verify the process that created the lock is definitely not still running
   (check timestamps — a lock older than the longest expected apply duration
   is safe to investigate for force-unlock).
2. Force-unlock using the lock ID from the error message:
   `terraform force-unlock <lock-id>`
3. Re-run `terraform plan` to confirm state is consistent before applying.
4. Prevention: add a concurrency group / pipeline lock at the CI level so
   only one apply against a given workspace can run at a time.
