# Verification boundaries

Implemented checks: strict configuration validation, immutable images/commit SHAs, output collision protection, no shell execution, explicit mutation gate, kube-context/AKS endpoint match, command failure handling, generated RBAC/workload structure, and mode-specific application/pipeline behavior. Python unit tests mock commands and remote APIs. CI tests the sample container under non-root, read-only, dropped-capability constraints.

The vendored Argo namespace installer/CRDs are official v3.5.6 sources with checksums. Harness entity YAML is generated from documented entity types and must be imported/validated in the customer's account. YAML parsing and unit tests are not equivalent to Harness server validation.

No customer Azure subscription, AKS deployment, Harness account, connector, delegate token or API key was available during development. No paid infrastructure was provisioned, production traffic changed or live deployment claimed. GitHub CI outcomes are separate from local checks and must be checked on the repository Actions page.

Live acceptance: `doctor` passes; bootstrap succeeds; engine reports ready/Connected; private repository/registry access works; engine-specific status succeeds; two sample Pods become Ready; port-forward HTTP check passes; deliberate invalid-image deployment fails; recovery to the known-good commit succeeds; runtime identities cannot mutate an unrelated namespace or read Secrets. Run these only on an authorized staging target. Record results and outstanding controls before promotion.

## Development results

Pinned PyYAML 6.0.3 installation succeeded. Argo: 9 applicable unit tests passed (2 Harness-only checks skipped). Harness: all 11 unit tests passed. The identical sample Docker image built and returned HTTP 200 as UID 10001 with read-only filesystem, dropped capabilities, bounded CPU/memory and no-new-privileges. Kubeconform 0.8.0 validated all 64 Kubernetes objects across both generated platform/application bundles and the vendored namespace installer against Kubernetes 1.35.0: zero invalid, errors or skipped. Harness entity YAML is excluded from Kubernetes schema validation because it is Harness configuration. All six GitHub workflow YAML files parse.

A disposable kind Kubernetes 1.37 cluster failed during local control-plane initialization, before applying any project manifests. This is not a passing in-cluster installation test. Live AKS/Harness checks remain unverified until customer setup. Remote GitHub CI passed after publication (see below).

## Publication verification

Published at https://github.com/THEJANAIDU/aks-harness-pilot. The initial source commit passed all four GitHub CI jobs: Python 3.10, 3.12 and 3.13 unit tests/compilation plus the restricted Docker sample-runtime check. [Verified CI run](https://github.com/THEJANAIDU/aks-harness-pilot/actions/runs/40828082549). A fresh public clone matched all 16 tracked source files byte-for-byte and passed its unit suite. Generated Application/AppProject manifests also passed the pinned Argo CD CRD schemas. A local kind 1.35 retry was stopped during image download; it is not counted as successful cluster verification.
