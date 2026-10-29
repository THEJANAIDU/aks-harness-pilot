# Packaged sample and AKS demonstration

`sample/` is an installable Python distribution (`aks-pilot-demo`, version 1.0.0) with no runtime dependencies. The multi-stage Docker build packages a wheel and installs only the wheel into the final pinned Python image. It listens on 8080, supports non-root UID 10001/read-only filesystem, and exposes `/`, `/healthz`, `/readyz` and `/api/version`.

## Build

```sh
python -m pip wheel --no-deps --wheel-dir dist-artifacts ./sample
docker build -t aks-pilot-demo:1.0.0 sample
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges -p 127.0.0.1:8080:8080 aks-pilot-demo:1.0.0
```

The manual **Build sample image** workflow tests the distribution, publishes a Linux amd64/arm64 image to GHCR, and uploads the wheel plus `release.json` as the `sample-release` artifact. `release.json` records the immutable image digest and source commit. Configure registry pull access before AKS deployment; packages are private by default unless their owner changes visibility. No registry credential belongs in Git.

## Deployment and ownership

Use `pilot-argocd-demo` for the Argo CD example and `pilot-harness-demo` for the Harness CD example. Never point both engines at the same namespace/workload. The current Harness agent performs direct continuous delivery; Argo CD performs GitOps reconciliation. A combined design can have Harness orchestrate an approved Git change and let Argo CD deploy it, but that requires an additional Harness Git-promotion pipeline rather than using the supplied direct-deployment stage.

Use the actual image from `release.json` in the agent config. Render with the matching agent, copy `generated/app/application.yaml` into `deploy/app/application.yaml`, and commit it. Update config `revision` to the resulting Git commit. The agent fetches and verifies that exact manifest before submitting the release. See README for required Azure identity, context checks, bootstrap and engine commands.

For Argo CD: `doctor` → `bootstrap --yes` on a dedicated installation → `deploy --yes` → `status`. Verify two ready replicas and HTTP `/api/version` through a private port-forward. Demonstrate self-healing by changing the replica count only in the authorized demo namespace, then watch Argo restore the Git value. For a new release, build version 1.1.0, commit its digest to the manifest, update config to the new manifest commit, and use `deploy --yes` to promote that pinned revision. A branch push alone does not advance a pinned Application.

For Harness CD: configure the real delegate/account/project/connectors and import generated entities before `execute --yes`. Verify the execution reaches Success and the separate demo namespace serves the expected version. Automatic stage rollback requires a previously successful release. This is not Harness GitOps-agent installation.

No AKS cluster, subscription, registry pull permission or Harness credential is assumed. Live acceptance results must be recorded separately from local package/container and GitHub CI results.
