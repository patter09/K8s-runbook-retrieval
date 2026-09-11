# Runbook: AKS Pod in CrashLoopBackOff

## Symptom
A pod repeatedly restarts and shows status `CrashLoopBackOff` in `kubectl get pods`.

## First checks
1. Describe the pod to see recent events and the last termination reason:
   `kubectl describe pod <pod-name> -n <namespace>`
2. Check the last container logs (the current attempt may not have logged
   anything useful yet):
   `kubectl logs <pod-name> -n <namespace> --previous`
3. Check whether the container is being OOMKilled — look for
   `Reason: OOMKilled` in the describe output. This usually means the
   resource `limits.memory` is set too low for the workload.
4. Check the readiness/liveness probe configuration. An aggressive
   `initialDelaySeconds` or `timeoutSeconds` on the liveness probe can kill a
   healthy but slow-starting container before it finishes booting.

## Common root causes
- Missing or invalid environment variables / secrets (check `envFrom` and
  `secretKeyRef` references resolve correctly).
- Application crashing on startup due to a bad config map update.
- Image pull succeeded but the entrypoint command is wrong (check for
  `CrashLoopBackOff` immediately after a new image tag was rolled out).
- Insufficient memory limits causing OOMKill under load.

## Resolution
- If OOMKilled: increase `resources.limits.memory` and
  `resources.requests.memory`, then roll the deployment.
- If probe misconfiguration: increase `initialDelaySeconds` on the liveness
  probe to allow for slow startup, and prefer a startup probe for slow-boot
  applications.
- If bad config: roll back to the previous ConfigMap/Secret revision and
  redeploy.
- Always verify the fix with `kubectl rollout status deployment/<name>` before
  closing the incident.
