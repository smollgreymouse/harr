#!/usr/bin/env python3
import importlib.util, json, os, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('harr_manager',ROOT/'common/mcp/manager.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='harr-workspace-manager-') as td:
    base=Path(td); home=base/'home'; cfg=base/'config'; repo=base/'repo'; child=repo/'src';
    for p in (home,cfg,child): p.mkdir(parents=True,exist_ok=True)
    (repo/'.git').mkdir()
    fake=base/'leanctx'
    fake.write_text('''#!/usr/bin/env python3\nimport json,sys,uuid\nfrom pathlib import Path\na=sys.argv[1:]\nif a[:2]==["workspace-admin","create"]:\n p=Path(a[2]); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps({"id":str(uuid.uuid4()),"revision":1,"primary":str(Path(a[3]).resolve()),"additional":[]})); p.chmod(0o600); sys.exit(0)\nif a[:2]==["workspace-admin","show"]:\n print(Path(a[2]).read_text()); sys.exit(0)\nif a[:2]==["workspace-admin","reconcile"]:\n print(Path(a[2]).read_text()); sys.exit(0)\nsys.exit(2)\n'''); fake.chmod(0o755)
    os.environ['HOME']=str(home); os.environ['XDG_CONFIG_HOME']=str(cfg)
    assert m.workspace_root(child)==repo.resolve()
    store=m.ensure_workspace_store(fake,repo)
    state=json.loads(store.read_text())
    assert state['primary']==str(repo.resolve()) and state['revision']==1
    assert store.parent==cfg/'harr'/'workspaces'
    assert (store.stat().st_mode & 0o077)==0
    assert m.ensure_workspace_store(fake,repo)==store
    assert m.leanctx_is_mcp([]) and m.leanctx_is_mcp(['mcp']) and not m.leanctx_is_mcp(['config','validate'])
print('PASS: Harr owns deterministic per-project Workspace store and MCP strict-mode selection')
