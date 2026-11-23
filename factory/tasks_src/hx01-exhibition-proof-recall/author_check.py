"""Cheap author-only fixture scoring through the production evaluate function."""
import importlib.util
import json
from pathlib import Path
import sys

SOURCE = Path(__file__).parent
ROOT = SOURCE.parents[1]
sys.path.insert(0, str(ROOT / 'verifier_kit'))
import cuaverify_additive as kit
sys.modules['cuaverify'] = kit
spec = importlib.util.spec_from_file_location('hx01_verifier', SOURCE / 'tests/verifier.py')
verifier = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = verifier
spec.loader.exec_module(verifier)

class Grader:
    def __init__(self): self.items=[]
    def add(self, check, weight, passed, detail): self.items.append(dict(id=check,weight=weight,score=float(passed)))

build=Path(sys.argv[1]); reports={}
for fixture in sorted((build/'variants').iterdir()):
    kit.VAR_DIR=fixture
    verifier.VAR_DIR=fixture
    verifier.OUTPUT_DIR=fixture/'output'
    verifier.INPUT_DIR=build/'input'
    grader=Grader();verifier.evaluate(grader)
    score=sum(x['weight']*x['score'] for x in grader.items)/sum(x['weight'] for x in grader.items)
    reports[fixture.name]=dict(reward=score,checks=grader.items)
    print(f'{fixture.name}: {score:.2f}')
Path(sys.argv[2]).write_text(json.dumps(reports,indent=2)+'\n')
