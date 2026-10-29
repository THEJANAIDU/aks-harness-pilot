# Operator runbook

Before first use: validate the configuration, inspect the generated YAML, verify the immutable Git commit and image contents, obtain platform authorization, check network/DNS/registry connectivity, and choose a staging namespace. Preserve the last known good commit, image digest and configuration outside public Git. Do not deploy the same application namespace with both agents: choose one owner to avoid reconciliation conflicts.

## Rollout

Run the mode-specific commands in README. A submitted application/execution is not proof of rollout. Inspect readiness and events in the configured context, verify the expected image digest, then exercise the HTTP endpoint through a private port-forward. Check application logs privately and remove secrets before sharing diagnostics. For Harness, verify the service revision in the imported pipeline as well as the execution's immutable manifest source.

```sh
kubectl --context CONTEXT -n APP_NAMESPACE rollout status deployment/APP_NAME --timeout=300s
kubectl --context CONTEXT -n APP_NAMESPACE get pods
kubectl --context CONTEXT -n APP_NAMESPACE get events --sort-by=.metadata.creationTimestamp
kubectl --context CONTEXT -n APP_NAMESPACE port-forward svc/APP_NAME 8080:80
# Separate terminal: curl -fsS http://127.0.0.1:8080/
```

## Rollback

Argo CD: restore the last known good full Git SHA in the configuration, render/review it, then run `deploy --yes`. Because source revisions are pinned, a Git revert commit only takes effect after updating the configured SHA. Automated reconciliation can undo an out-of-band `kubectl rollout undo`; use the GitOps source as the authority. Pruning is disabled, so resources removed from Git remain until explicitly reviewed/deleted. No Application deletion finalizer is installed.

Harness: the pipeline uses StageRollback with K8sRollingRollback on deployment errors. A successful first deployment is required for a meaningful prior revision. Verify rollback status and application health; automatic rollback may also fail. For manual recovery, import the service YAML referencing the previous known-good Git commit, verify the pipeline/input set, then execute with `--yes`. Prefer a reviewed previous release over an untracked kubectl change. Avoid concurrent executions and inspect history before retrying a request with an ambiguous network outcome.

Kubernetes rolling rollback does not reverse database/schema migrations, external side effects, Secret changes, or data corruption. Backups and restore tests belong to the application owner.

## Troubleshooting

Context mismatch: correct `context` and user kubeconfig; do not bypass the server check. Authorization errors: ask the platform administrator for the missing scoped capability; do not replace runtime roles with cluster-admin. ImagePullBackOff: verify image digest, architecture, registry visibility and pull credentials. Argo Missing/Unknown: verify CRDs, cluster registration namespaces, controller RoleBinding and Git source credentials. Harness delegate Pending/Disconnected: check available 2Gi memory, image tag/digest, account/token, egress and project placement; readiness does not prove account connectivity. Harness pipeline validation: verify connector identifiers, environment/infrastructure and license features in the account.

## Cleanup

No automatic uninstall command is supplied. Review all application and platform resources before manually removing them in the exact kube context. Do not delete an application namespace until its workloads and data owners approve. Argo Application deletion leaves workloads; remove them only after review. Remove generated RoleBindings and revoke delegate/API/Git tokens when retiring the kit. Never remove shared Argo CRDs while another installation uses them. Stop port-forwards and securely delete temporary kubeconfig/token files.

Production adoption requires HA, SSO, approval policies, environment protection, monitoring/alerts, namespace quotas, network policies, supply-chain scanning/signing, private registry setup, disaster-recovery tests and application-specific capacity/load tests. No production readiness or live customer verification is implied by local tests.
