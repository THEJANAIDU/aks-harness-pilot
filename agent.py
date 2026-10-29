"""Reviewed, explicit AKS deployment automation. No shell execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import yaml

MODE = "harness"
class AgentError(Exception): pass

def run(args, data=None):
    try:
        result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=600, env={**os.environ,"GIT_TERMINAL_PROMPT":"0"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AgentError("Command unavailable or timed out: " + args[0]) from exc
    if result.returncode:
        # Tool stderr may contain credentials; never echo it into CI logs.
        raise AgentError("Command failed: " + args[0] + "; inspect locally with your operator credentials")
    return result.stdout

def load(path):
    c = json.loads(Path(path).read_text())
    required = {"subscription", "resource_group", "cluster", "context", "namespace", "application", "image", "repo_url", "revision"}
    required |= {"account", "org", "project", "pipeline", "input_sets", "delegate_image"} if MODE == "harness" else set()
    if set(c) != required: raise AgentError("Config fields must be exactly: " + ", ".join(sorted(required)))
    for k,v in c.items():
        if k == "input_sets":
            if not isinstance(v,list) or not v or any(not isinstance(x,str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",x) for x in v): raise AgentError("input_sets must contain identifiers")
        elif not isinstance(v,str) or not v or any(x in v.lower() for x in ("replace_me", "your_", "<", ">")):
            raise AgentError("Supply a real value for " + k)
    for k in ("namespace","application"):
        if len(c[k])>63 or not re.fullmatch(r"[a-z][a-z0-9-]*[a-z0-9]|[a-z]",c[k]): raise AgentError("Invalid DNS label: " + k)
    if c["namespace"] in ("default","kube-system","argocd","harness-delegate"): raise AgentError("Use a dedicated application namespace")
    try: uuid.UUID(c["subscription"])
    except ValueError: raise AgentError("subscription must be a UUID")
    if c["image"].endswith("0"*64) or not re.fullmatch(r"[A-Za-z0-9._:/-]+@sha256:[a-f0-9]{64}", c["image"]): raise AgentError("image must use an immutable sha256 digest")
    u=urllib.parse.urlparse(c["repo_url"])
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment: raise AgentError("Use a credential-free HTTPS repo_url")
    if c["revision"] == "0"*40 or not re.fullmatch(r"[a-f0-9]{40}",c["revision"]): raise AgentError("revision must be a full Git commit SHA")
    if MODE == "harness":
        for k in ("org","project","pipeline"):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", c[k]): raise AgentError("Invalid Harness identifier: " + k)
        if not re.fullmatch(r"[A-Za-z0-9_-]+",c["account"]): raise AgentError("Invalid account identifier")
        if not re.fullmatch(r"harness/delegate:[A-Za-z0-9._-]+@sha256:[a-f0-9]{64}",c["delegate_image"]): raise AgentError("Pin official harness/delegate tag and digest")
    return c

def kubectl(c,*args,data=None):
    return run(["kubectl","--context",c["context"],*args], data)

def doctor(c):
    for tool in ("az","kubectl","kubelogin"):
        if not shutil.which(tool): raise AgentError("Install prerequisite: " + tool)
    cluster=json.loads(run(["az","aks","show","--subscription",c["subscription"],"-g",c["resource_group"],"-n",c["cluster"],"-o","json"]))
    kc=json.loads(kubectl(c,"config","view","--minify","-o","json"))
    cluster_config=kc["clusters"][0]["cluster"]
    if cluster_config.get("insecure-skip-tls-verify"): raise AgentError("Kubeconfig must verify TLS certificates")
    server=urllib.parse.urlparse(cluster_config["server"]).hostname
    if server not in (cluster.get("fqdn"),cluster.get("privateFqdn")): raise AgentError("Kube context does not match the configured AKS cluster")
    kubectl(c,"get","--raw=/readyz")
    return "AKS identity, context and API reachability checked; authorization remains command-specific"

def application(c):
    name=c["application"]
    labels={"app":name}
    container={"name":name,"image":c["image"],"ports":[{"containerPort":8080}],"resources":{"requests":{"cpu":"50m","memory":"32Mi"},"limits":{"cpu":"250m","memory":"128Mi"}},"securityContext":{"allowPrivilegeEscalation":False,"readOnlyRootFilesystem":True,"capabilities":{"drop":["ALL"]}},"readinessProbe":{"httpGet":{"path":"/","port":8080},"initialDelaySeconds":3},"livenessProbe":{"httpGet":{"path":"/","port":8080},"initialDelaySeconds":10}}
    return [{"apiVersion":"apps/v1","kind":"Deployment","metadata":{"name":name,"namespace":c["namespace"]},"spec":{"replicas":2,"revisionHistoryLimit":5,"selector":{"matchLabels":labels},"strategy":{"type":"RollingUpdate","rollingUpdate":{"maxUnavailable":0,"maxSurge":1}},"template":{"metadata":{"labels":labels},"spec":{"automountServiceAccountToken":False,"securityContext":{"runAsNonRoot":True,"runAsUser":10001,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[container]}}}},{"apiVersion":"v1","kind":"Service","metadata":{"name":name,"namespace":c["namespace"]},"spec":{"type":"ClusterIP","selector":labels,"ports":[{"port":80,"targetPort":8080}]}}]

def verify_source(c):
    """Check the actual pinned source before asking a deployment engine to reconcile it."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        run(["git","init","--quiet",tmp])
        run(["git","-C",tmp,"remote","add","origin",c["repo_url"]])
        run(["git","-C",tmp,"fetch","--quiet","--depth=1","origin",c["revision"]])
        actual=run(["git","-C",tmp,"rev-parse","FETCH_HEAD"]).strip()
        if actual != c["revision"]: raise AgentError("Fetched commit does not match requested revision")
        paths=run(["git","-C",tmp,"ls-tree","--name-only","FETCH_HEAD:deploy/app"]).splitlines()
        if paths != ["application.yaml"]: raise AgentError("deploy/app must contain only the generated application.yaml")
        raw=run(["git","-C",tmp,"show","FETCH_HEAD:deploy/app/application.yaml"])
        try: source=list(yaml.safe_load_all(raw))
        except yaml.YAMLError: raise AgentError("Source manifest YAML is invalid") from None
        if source != application(c): raise AgentError("Pinned source differs from the configured release; regenerate and commit deploy/app")

def namespace(c):
    return {"apiVersion":"v1","kind":"Namespace","metadata":{"name":c["namespace"],"labels":{"pod-security.kubernetes.io/enforce":"restricted"}}}

def write_yaml(path,docs):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(yaml.safe_dump_all(docs,sort_keys=False))

def render(c,out):
    out=Path(out)
    if out.exists(): raise AgentError("Output already exists; choose a new directory")
    out.mkdir(parents=True)
    write_yaml(out/"app"/"application.yaml",application(c))
    write_yaml(out/"platform"/"namespace.yaml",[namespace(c)])
    render_mode(c,out)
    return str(out.resolve())

COMMANDS=["validate","render","doctor","bootstrap","execute","status"]
MUTATIONS={"bootstrap","execute"}
def render_mode(c,out):
    ns="harness-delegate"; sa="aks-harness"
    rules=[{"apiGroups":["apps"],"resources":["deployments","replicasets"],"verbs":["get","list","watch","create","update","patch","delete"]},{"apiGroups":[""],"resources":["services","configmaps"],"verbs":["get","list","watch","create","update","patch","delete"]},{"apiGroups":[""],"resources":["pods","events"],"verbs":["get","list","watch"]}]
    write_yaml(out/"platform"/"delegate-rbac.yaml",[{"apiVersion":"v1","kind":"Namespace","metadata":{"name":ns}},{"apiVersion":"v1","kind":"ServiceAccount","metadata":{"name":sa,"namespace":ns}},{"apiVersion":"rbac.authorization.k8s.io/v1","kind":"Role","metadata":{"name":sa,"namespace":c["namespace"]},"rules":rules},{"apiVersion":"rbac.authorization.k8s.io/v1","kind":"RoleBinding","metadata":{"name":sa,"namespace":c["namespace"]},"subjects":[{"kind":"ServiceAccount","name":sa,"namespace":ns}],"roleRef":{"apiGroup":"rbac.authorization.k8s.io","kind":"Role","name":sa}}])
    env=[{"name":"ACCOUNT_ID","value":c["account"]},{"name":"MANAGER_HOST_AND_PORT","value":"https://app.harness.io"},{"name":"DELEGATE_NAME","value":sa},{"name":"DELEGATE_TAGS","value":sa},{"name":"NEXT_GEN","value":"true"},{"name":"DELEGATE_TYPE","value":"KUBERNETES"},{"name":"DEPLOY_MODE","value":"KUBERNETES"},{"name":"DELEGATE_NAMESPACE","valueFrom":{"fieldRef":{"fieldPath":"metadata.namespace"}}},{"name":"DELEGATE_TOKEN","valueFrom":{"secretKeyRef":{"name":"harness-delegate-token","key":"token"}}}]
    write_yaml(out/"delegate.yaml",[{"apiVersion":"apps/v1","kind":"Deployment","metadata":{"name":sa,"namespace":ns},"spec":{"replicas":1,"selector":{"matchLabels":{"app":sa}},"template":{"metadata":{"labels":{"app":sa}},"spec":{"serviceAccountName":sa,"securityContext":{"runAsNonRoot":True,"runAsUser":1001},"containers":[{"name":"delegate","image":c["delegate_image"],"env":env,"ports":[{"containerPort":3460}],"resources":{"requests":{"cpu":"500m","memory":"2Gi"},"limits":{"cpu":"1","memory":"2Gi"}},"readinessProbe":{"httpGet":{"path":"/api/health","port":3460},"initialDelaySeconds":60,"periodSeconds":10},"securityContext":{"allowPrivilegeEscalation":False,"capabilities":{"drop":["ALL"]}}}]}}}}])
    # Harness entities reference a customer-configured Git connector and in-cluster Kubernetes connector.
    stage={"stage":{"name":"Deploy AKS","identifier":"Deploy_AKS","type":"Deployment","spec":{"deploymentType":"Kubernetes","service":{"serviceRef":c["application"].replace("-","_")},"environment":{"environmentRef":"aks_staging","deployToAll":False,"infrastructureDefinitions":[{"identifier":"aks_namespace"}]},"execution":{"steps":[{"step":{"name":"Rolling deploy","identifier":"rolling","type":"K8sRollingDeploy","timeout":"10m","spec":{"skipDryRun":False,"pruningEnabled":False}}}],"rollbackSteps":[{"step":{"name":"Rollback","identifier":"rollback","type":"K8sRollingRollback","timeout":"10m","spec":{}}}]}},"failureStrategies":[{"onFailure":{"errors":["AllErrors"],"action":{"type":"StageRollback"}}}],"delegateSelectors":[sa]}}
    write_yaml(out/"harness"/"pipeline.yaml",[{"pipeline":{"name":"AKS delivery","identifier":c["pipeline"],"orgIdentifier":c["org"],"projectIdentifier":c["project"],"tags":{},"stages":[stage]}}])
    write_yaml(out/"harness"/"service.yaml",[{"service":{"name":c["application"],"identifier":c["application"].replace("-","_"),"orgIdentifier":c["org"],"projectIdentifier":c["project"],"serviceDefinition":{"type":"Kubernetes","spec":{"manifests":[{"manifest":{"identifier":"app","type":"K8sManifest","spec":{"store":{"type":"Github","spec":{"connectorRef":"aks_git","gitFetchType":"Commit","commitId":c["revision"],"repoName":urllib.parse.urlparse(c["repo_url"]).path.strip("/").removesuffix(".git"),"paths":["deploy/app"]}},"skipResourceVersioning":False}}}]}}}}])
    write_yaml(out/"harness"/"environment.yaml",[{"environment":{"name":"AKS staging","identifier":"aks_staging","orgIdentifier":c["org"],"projectIdentifier":c["project"],"type":"PreProduction"}}])
    write_yaml(out/"harness"/"infrastructure.yaml",[{"infrastructureDefinition":{"name":"AKS namespace","identifier":"aks_namespace","orgIdentifier":c["org"],"projectIdentifier":c["project"],"environmentRef":"aks_staging","deploymentType":"Kubernetes","type":"KubernetesDirect","spec":{"connectorRef":"aks_incluster","namespace":c["namespace"],"releaseName":"release-<+INFRA_KEY_SHORT_ID>"},"allowSimultaneousDeployments":False}}])

def api(c,path,body=None):
    token=os.environ.get("HARNESS_API_KEY")
    if not token: raise AgentError("Set HARNESS_API_KEY in your environment")
    query=urllib.parse.urlencode({"accountIdentifier":c["account"],"orgIdentifier":c["org"],"projectIdentifier":c["project"],"moduleType":"CD"})
    request=urllib.request.Request("https://app.harness.io/pipeline/api/"+path+"?"+query,data=None if body is None else json.dumps(body).encode(),headers={"x-api-key":token,"Content-Type":"application/json"},method="GET" if body is None else "POST")
    # Refuse redirects to prevent forwarding API keys to another host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=30) as response: result=json.load(response)
    except (urllib.error.URLError,ValueError): raise AgentError("Harness request failed; check API key, entity identifiers and account permissions") from None
    if result.get("status") not in (None,"SUCCESS"): raise AgentError("Harness rejected request")
    return result

def execute(c,a):
    if a.command=="bootstrap":
        doctor(c)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"rendered"; render(c,out)
            kubectl(c,"apply","-f",str(out/"platform"))
            kubectl(c,"get","secret","harness-delegate-token","-n","harness-delegate","-o","name")
            kubectl(c,"apply","-f",str(out/"delegate.yaml"))
        kubectl(c,"rollout","status","deployment/aks-harness","-n","harness-delegate","--timeout=300s")
        print("Delegate pod ready; verify Connected in Harness and test both connectors")
    elif a.command=="execute":
        verify_source(c)
        result=api(c,"pipeline/execute/"+c["pipeline"]+"/inputSetList",{"inputSetReferences":c["input_sets"],"withMergedPipelineYaml":False})
        execution=result.get("data",{}).get("planExecution",{}).get("uuid") or result.get("data",{}).get("planExecutionId")
        if not execution: raise AgentError("Execution response missing ID; check Harness execution history before retrying")
        print(json.dumps({"execution_id":execution,"message":"Submitted, not verified successful. Run status --execution ID."}))
    else:
        if not a.execution or not re.fullmatch(r"[A-Za-z0-9_-]+",a.execution): raise AgentError("Supply a valid --execution ID")
        result=api(c,"pipelines/execution/summary/"+a.execution)
        summary=result.get("data",{}).get("pipelineExecutionSummary",{})
        print(json.dumps({"status":summary.get("status"),"execution_id":a.execution}))
        if summary.get("status")!="Success": raise AgentError("Execution has not succeeded")


def main(argv=None):
    p=argparse.ArgumentParser(description="AKS " + MODE + " automation agent")
    p.add_argument("command",choices=COMMANDS)
    p.add_argument("--config",required=True)
    p.add_argument("--output",default="generated")
    p.add_argument("--yes",action="store_true",help="Explicitly authorize the selected remote mutation")
    p.add_argument("--execution",help="Harness execution ID")
    a=p.parse_args(argv)
    try:
        c=load(a.config)
        if a.command=="validate": print("Configuration valid; credentials and remote resources not checked")
        elif a.command=="render": print(render(c,a.output))
        elif a.command=="doctor": print(doctor(c))
        else:
            if a.command in MUTATIONS and not a.yes: raise AgentError("Remote mutation requires --yes after reviewing rendered output")
            execute(c,a)
        return 0
    except (AgentError,ValueError,KeyError,OSError) as exc:
        print("ERROR: " + str(exc),file=sys.stderr)
        return 1

if __name__=="__main__": sys.exit(main())
