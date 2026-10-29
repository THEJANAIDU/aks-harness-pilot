import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

class SampleTests(unittest.TestCase):
    def test_packaged_endpoints(self):
        # Test the built distribution, including console entry point and package metadata.
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run([sys.executable,"-m","pip","wheel","--no-deps","--wheel-dir",directory,"./sample"],check=True,stdout=subprocess.DEVNULL)
            wheels=list(Path(directory).glob("*.whl"))
            self.assertEqual(len(wheels),1)
            subprocess.run([sys.executable,"-m","pip","install","--no-deps","--target",directory+"/installed",str(wheels[0])],check=True,stdout=subprocess.DEVNULL)
            expected=re.search(r'version = "([^"]+)"',Path("sample/pyproject.toml").read_text()).group(1)
            code="EXPECTED="+repr(expected)+"\n"+"""import json
from aks_pilot_demo.server import response
for path in ('/','/healthz','/readyz','/api/version','/missing'):
    status,kind,body=response(path)
    if path=='/': assert status==200 and EXPECTED.encode() in body
    elif path=='/missing': assert status==404
    else: assert status==200 and json.loads(body)['version']==EXPECTED
"""
            import os
            subprocess.run([sys.executable,"-c",code],check=True,env={**os.environ,"PYTHONPATH":directory+"/installed"})
