import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import agent
import yaml

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.c=json.loads(Path("config.example.json").read_text())
        self.c.update(image="ghcr.io/example/sample@sha256:"+"a"*64,revision="b"*40)
        if agent.MODE=="harness": self.c.update(account="account123",project="demo",delegate_image="harness/delegate:26.10.1@sha256:"+"c"*64)
    def load(self,c):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"config.json"; path.write_text(json.dumps(c)); return agent.load(path)
    def test_valid(self): self.assertEqual(self.load(self.c),self.c)
    def test_invalid_and_secret_configuration(self):
        for field,value in [("namespace","kube-system"),("image","nginx:latest"),("revision","main"),("revision","0"*40),("repo_url","https://token@github.com/a/b"),("subscription","-"*36)]:
            with self.subTest(field=field,value=value):
                c=copy.deepcopy(self.c); c[field]=value
                with self.assertRaises(agent.AgentError): self.load(c)
        c=copy.deepcopy(self.c); c["api_key"]="secret"
        with self.assertRaises(agent.AgentError): self.load(c)
    def test_render_no_network_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d, patch.object(agent,"run",side_effect=AssertionError("network")):
            out=Path(d)/"out"; agent.render(self.c,out)
            dep=list(yaml.safe_load_all((out/"app/application.yaml").read_text()))[0]
            self.assertEqual(dep["spec"]["template"]["spec"]["containers"][0]["image"],self.c["image"])
            self.assertFalse(dep["spec"]["template"]["spec"]["automountServiceAccountToken"])
            for path in out.rglob("*.yaml"):
                self.assertTrue(list(yaml.safe_load_all(path.read_text())))
            with self.assertRaises(agent.AgentError): agent.render(self.c,out)
    def test_mutation_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as d, patch.object(agent,"execute") as execute:
            path=Path(d)/"config.json"; path.write_text(json.dumps(self.c))
            self.assertEqual(agent.main(["bootstrap","--config",str(path)]),1)
            execute.assert_not_called()
    def test_context_mismatch_blocks(self):
        responses=[json.dumps({"fqdn":"real.example"}),json.dumps({"clusters":[{"cluster":{"server":"https://wrong.example"}}]})]
        with patch.object(agent.shutil,"which",return_value="tool"),patch.object(agent,"run",side_effect=responses):
            with self.assertRaises(agent.AgentError): agent.doctor(self.c)
    def test_subprocess_never_uses_shell(self):
        with patch.object(agent.subprocess,"run") as run:
            run.return_value.returncode=0; run.return_value.stdout="ok"
            agent.run(["kubectl","--context","x; echo bad"])
            self.assertNotIn("shell",run.call_args.kwargs)
    def test_mode_specific_contract(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"out"; agent.render(self.c,out)
            if agent.MODE=="argocd":
                objects=list(yaml.safe_load_all((out/"argocd.yaml").read_text()))
                self.assertEqual(objects[0]["stringData"]["namespaces"],self.c["namespace"])
                self.assertEqual(objects[1]["spec"]["clusterResourceWhitelist"],[])
                self.assertFalse(objects[2]["spec"]["syncPolicy"]["automated"]["prune"])
                vendor=Path("vendor/namespace-install.yaml")
                self.assertEqual(hashlib.sha256(vendor.read_bytes()).hexdigest(),vendor.with_suffix(".sha256").read_text().strip())
            else:
                entities=yaml.safe_load((out/"harness/pipeline.yaml").read_text())
                stage=entities["pipeline"]["stages"][0]["stage"]
                self.assertEqual(stage["failureStrategies"][0]["onFailure"]["action"]["type"],"StageRollback")
                self.assertIn("rollbackSteps",stage["spec"]["execution"])
                dep=yaml.safe_load((out/"delegate.yaml").read_text())
                env=dep["spec"]["template"]["spec"]["containers"][0]["env"]
                self.assertIn("valueFrom",next(v for v in env if v["name"]=="DELEGATE_TOKEN"))
    def test_harness_api_failure_does_not_leak_key(self):
        if agent.MODE!="harness": self.skipTest("Harness-specific API contract")
        import urllib.error
        with patch.dict(agent.os.environ,{"HARNESS_API_KEY":"supersecret"}),patch.object(agent.urllib.request,"build_opener") as opener:
            opener.return_value.open.side_effect=urllib.error.URLError("supersecret")
            with self.assertRaises(agent.AgentError) as exc: agent.api(self.c,"test")
            self.assertNotIn("supersecret",str(exc.exception))
    def test_harness_submission_is_not_success(self):
        if agent.MODE!="harness": self.skipTest("Harness-specific API contract")
        import argparse
        with patch.object(agent,"verify_source"), patch.object(agent,"api",return_value={"status":"SUCCESS","data":{}}):
            with self.assertRaises(agent.AgentError): agent.execute(self.c,argparse.Namespace(command="execute"))
        with patch.object(agent,"api",return_value={"data":{"pipelineExecutionSummary":{"status":"Running"}}}):
            with self.assertRaises(agent.AgentError): agent.execute(self.c,argparse.Namespace(command="status",execution="run123"))

    def test_source_digest_gate(self):
        expected=yaml.safe_dump_all(agent.application(self.c))
        responses=["","","",self.c["revision"],"application.yaml",expected]
        with patch.object(agent,"run",side_effect=responses): agent.verify_source(self.c)
        wrong=expected.replace(self.c["image"],"nginx:latest")
        with patch.object(agent,"run",side_effect=["","","",self.c["revision"],"application.yaml",wrong]):
            with self.assertRaises(agent.AgentError): agent.verify_source(self.c)
    def test_insecure_context_blocks(self):
        responses=[json.dumps({"fqdn":"real.example"}),json.dumps({"clusters":[{"cluster":{"server":"https://real.example","insecure-skip-tls-verify":True}}]})]
        with patch.object(agent.shutil,"which",return_value="tool"),patch.object(agent,"run",side_effect=responses):
            with self.assertRaises(agent.AgentError): agent.doctor(self.c)

if __name__=="__main__": unittest.main()
