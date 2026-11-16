"""Structural delivery checks. These do not execute PostgreSQL or a web service."""
from pathlib import Path
import ast,csv,json,re
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
def main():
    checks=[]
    for p in ROOT.rglob('*.json'):json.loads(p.read_text())
    checks.append('All JSON artifacts parse')
    for p in ROOT.rglob('*.py'):ast.parse(p.read_text())
    checks.append('All supplied Python scripts parse')
    api=json.loads((ROOT/'specs/openapi.json').read_text())
    def visit(x):
        if isinstance(x,dict):
            if '$ref' in x:
                assert x['$ref'].startswith('#/'),x['$ref']
                target=api
                for key in x['$ref'][2:].split('/'):target=target[key]
            if x.get('type')=='object' and 'required' in x:
                assert set(x['required'])<=set(x.get('properties',{}))
            for v in x.values():visit(v)
        elif isinstance(x,list):
            for v in x:visit(v)
    visit(api)
    ids=[]
    for path,operations in api['paths'].items():
        for method,operation in operations.items():
            ids.append(operation['operationId'])
            assert operation['security']
            params=operation.get('parameters',[])
            for name in re.findall(r'\{(.*?)\}',path):
                assert any(p['name']==name and p['in']=='path' and p['required'] for p in params)
            if method in ('post','delete'):
                assert any(p['name']=='Idempotency-Key' and p['required'] for p in params)
    assert len(ids)==len(set(ids))
    checks.append('OpenAPI local references, operation IDs, required fields, auth and idempotency structure consistent')
    a=json.loads((ROOT/'data_audit/audit.json').read_text()); manifest=json.loads((ROOT/'specs/ingestion_manifest.json').read_text())
    assert a['source_sha256']==manifest['source_archives']
    assert len(a['files'])==len(manifest['files'])==12
    assert len(manifest['text_files'])==85
    for x in manifest['files']:
        actual=next(y for y in a['files'] if y['archive']==x['archive'] and y['file']==x['file'])
        assert (x['expected_rows'],x['expected_columns'],x['exact_unique_rows'])==(actual['rows'],actual['columns'],actual['exact_unique_rows'])
    checks.append('Source manifest agrees with audited CSV counts and includes 85 text entries')
    for filename,expected in [('disease_candidate_catalog.csv',960),('feature_candidate_catalog.csv',958)]:
        with (ROOT/'data_audit'/filename).open() as f:rows=list(csv.DictReader(f))
        assert len(rows)==expected and len({r['candidate_id'] for r in rows})==expected
    checks.append('Candidate catalogs have 960 unique disease IDs and 958 unique feature IDs')
    m=json.loads((ROOT/'experiments/results/metrics.json').read_text())
    cm=np.load(ROOT/'experiments/results/confusion_matrix.npy')
    assert cm.shape==(46,46) and cm.sum()==m['splits']['test']['n']
    assert np.isclose(np.trace(cm)/cm.sum(),m['splits']['test']['top1_accuracy'])
    assert np.count_nonzero(cm.sum(1))==m['splits']['test']['classes_present']==39
    assert sum(v['n'] for v in m['splits'].values())==m['unique_labeled_rows']
    for v in m['splits'].values():assert sum(b['n'] for b in v['calibration_bins'])==v['n']
    checks.append('Confusion matrix, split totals, class support and calibration counts match reported metrics')
    for p in ROOT.rglob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            if '://' in target or target.startswith('#'):continue
            assert (p.parent/target.split('#')[0]).exists(),(str(p),target)
    checks.append('Relative Markdown links and image targets exist')
    report={'checks_passed':checks,'limits':['Not a full OpenAPI standards-validator run','SQL migration not executed against PostgreSQL','No application, browser, API, MCP or clinical validation performed','Baseline metrics unit tests are a separate command'],'environment':{'python':'3.12.14','numpy':'2.3.5','Pillow':'13.0.0'}}
    (ROOT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
