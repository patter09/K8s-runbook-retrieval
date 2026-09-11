# Runbook: ArgoCD Application Stuck in "OutOfSync" or Failing to Sync

## Symptom
An ArgoCD Application shows `OutOfSync` and does not reconcile automatically,
or a manual sync fails with an error in the ArgoCD UI/CLI.

## First checks
1. Check the application's sync status and error detail:
   `argocd app get <app-name>`
2. Look at the diff between the live and desired state:
   `argocd app diff <app-name>`
3. Check whether a resource hook (PreSync/PostSync job) is failing — this is
   a common cause of syncs appearing "stuck":
   `kubectl get jobs -n <namespace>`

## Common root causes
- A manual `kubectl edit` change was made directly against the cluster,
  causing configuration drift from the Git source of truth.
- A Helm chart values change introduced a schema the cluster's admission
  controller (e.g. Kyverno policy) rejects, so the apply silently fails
  validation.
- A PreSync hook (e.g. a DB migration job) failed and is blocking the rest
  of the sync from proceeding.
- Image tag in the manifest does not exist in the registry yet (pipeline
  ordering issue — manifest updated before image push completed).

## Resolution
- If drift: sync with `--prune` to bring the cluster back in line with Git,
  after confirming the manual change wasn't an intentional emergency fix
  (if it was, commit the equivalent change to Git first).
- If policy rejection: check `kubectl describe` on the failed resource for
  the admission controller's rejection reason and fix the manifest to
  comply, rather than disabling the policy.
- If a hook job failed: inspect the job's logs, fix the underlying issue,
  delete the failed job, and retry the sync.
- Always confirm the pipeline order guarantees the image is pushed before
  the manifest referencing it is applied, to prevent recurrence.
