# Identity and least privilege

Use an existing Entra-enabled AKS cluster. Operator identity, in-cluster service accounts, and pod-to-Azure workload identity solve separate problems.

| Actor | Required scope | Purpose |
|---|---|---|
| Reader/operator | Reader on this AKS resource; Azure Kubernetes Service Cluster User Role on this AKS resource | `az aks show` and user kubeconfig retrieval |
| Platform bootstrap administrator | Just-in-time permission to create required namespaces, CRDs (Argo only), namespace Roles/RoleBindings and platform workloads | One-time reviewed installation; ability to bind a Role requires owning its permissions or explicit bind authorization |
| Argo application controller | Generated Role in the application namespace | Deployments/ReplicaSets/Services write, Pods/Events read |
| Harness delegate service account | Generated Role in the application namespace | Deployments/ReplicaSets/Services/ConfigMaps write, Pods/Events read |
| Runtime sample app | No mounted service account token, no Azure identity | Serves HTTP only |

No agent is assigned subscription Contributor, Owner or permanent cluster-admin. Both deployment engines use Kubernetes service accounts and namespace RoleBindings, including on Azure-RBAC-enabled AKS. The human bootstrap identity needs the actual Entra/Azure or Kubernetes RBAC privileges that your cluster's authorization mode requires. A generic AKS RBAC Writer cannot create all platform RBAC/CRDs. Obtain temporary elevated access from the platform team rather than escalating the runtime delegate/controller.

Example resource-scoped Azure assignments, executed by an authorized RBAC administrator, not by this kit:

```sh
AKS_ID=$(az aks show --subscription SUBSCRIPTION_UUID -g AKS_RG -n AKS_NAME --query id -o tsv)
az role assignment create --assignee-object-id OPERATOR_OBJECT_ID --assignee-principal-type User --role Reader --scope "$AKS_ID"
az role assignment create --assignee-object-id OPERATOR_OBJECT_ID --assignee-principal-type User --role 'Azure Kubernetes Service Cluster User Role' --scope "$AKS_ID"
```

Use managed identities or OIDC federation for any later CI-to-Azure integration; do not store client secrets or admin kubeconfig in GitHub. This kit's CI is offline and requests no Azure identity. The in-cluster agents do not require Azure Workload Identity merely to deploy Kubernetes objects. If your application needs Key Vault/Storage, configure a separate least-privilege managed identity with federated subject `system:serviceaccount:NAMESPACE:SERVICEACCOUNT`, audience `api://AzureADTokenExchange`, an annotated service account and workload-identity pod label; scope its Azure role to the specific resource. The sample intentionally has no Azure access.

The manifests do not create Azure infrastructure or paid services. Running controllers/delegates consumes existing AKS capacity and may cause autoscaling costs. Start in a dedicated staging cluster/namespace and review capacity before `--yes`. Private AKS requires private network/DNS connectivity from the operator. Delegate/controller access to Git and image registries must also work from the cluster.

Protect the deployment namespace: ability to create workloads can allow use of service accounts/secrets there even without direct Secret-read permission. Do not colocate sensitive unrelated applications. Argo's AppProject restricts types/repository/destination in addition to Kubernetes RBAC. Restrict access to Argo/Harness configuration, project administrators and the platform namespaces.
