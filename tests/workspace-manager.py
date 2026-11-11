#!/usr/bin/env python3
import importlib.util, json, os, tempfile
from types import SimpleNamespace
from unittest.mock import patch
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
    gitdir=base/'git-admin'; gitdir.mkdir(); marker=gitdir/'description'; marker.write_text('fixture')
    marker_stat=marker.stat(); marker_ctime_ns=marker_stat.st_ctime_ns
    assert m.git_admin_generation(gitdir) == (
        f"unix:{marker_stat.st_dev}:{marker_stat.st_ino}:"
        f"{marker_ctime_ns // 1_000_000_000}:{marker_ctime_ns % 1_000_000_000}"
    )
    linked_gitdir=base/'linked-git-admin'; linked_gitdir.mkdir(); linked_marker=linked_gitdir/'commondir'; linked_marker.write_text('../..')
    linked_stat=linked_marker.stat(); linked_ctime_ns=linked_stat.st_ctime_ns
    assert m.git_admin_generation(linked_gitdir) == (
        f"unix:{linked_stat.st_dev}:{linked_stat.st_ino}:"
        f"{linked_ctime_ns // 1_000_000_000}:{linked_ctime_ns % 1_000_000_000}"
    )
    assert m.workspace_root(child)==repo.resolve()
    store=m.ensure_workspace_store(fake,repo)
    state=json.loads(store.read_text())
    assert state['primary']==str(repo.resolve()) and state['revision']==1
    assert store.parent==cfg/'harr'/'workspaces'
    assert (store.stat().st_mode & 0o077)==0
    assert m.ensure_workspace_store(fake,repo)==store
    assert m.leanctx_is_mcp([]) and m.leanctx_is_mcp(['mcp']) and not m.leanctx_is_mcp(['config','validate'])
    # A user-scoped MCP host can launch from HOME, not from the open repository.
    with patch.dict(os.environ, {'HARR_WORKSPACE_ROOT': str(repo)}):
        assert m.mcp_workspace_root() == repo.resolve()
        with patch.object(m, 'workspace_root', side_effect=AssertionError('cwd must not be used')):
            with patch.object(m.os, 'execvpe', side_effect=RuntimeError('exec intercepted')) as exec_mock:
                try:
                    m.exec_leanctx(SimpleNamespace(real=str(fake), rest=['mcp']), {'servers': []})
                    raise AssertionError('exec should have been intercepted')
                except RuntimeError as exc:
                    assert str(exc) == 'exec intercepted'
                assert exec_mock.call_args.args[2]['LEAN_CTX_WORKSPACE_FILE'] == str(store)
                assert exec_mock.call_args.args[2]['LEAN_CTX_STRICT_WORKSPACE'] == '1'
    # Invalid explicit roots must fail closed, never silently use host cwd.
    with patch.dict(os.environ, {'HARR_WORKSPACE_ROOT': 'relative/project'}):
        try:
            m.mcp_workspace_root()
            raise AssertionError('relative root was accepted')
        except SystemExit as exc:
            assert 'absolute' in str(exc)
    with patch.dict(os.environ, {'HARR_WORKSPACE_ROOT': str(base/'missing')}):
        try:
            m.mcp_workspace_root()
            raise AssertionError('missing root was accepted')
        except SystemExit as exc:
            assert 'not an existing directory' in str(exc)
    with patch.dict(os.environ, {'HARR_WORKSPACE_ROOT': ''}):
        try:
            m.mcp_workspace_root()
            raise AssertionError('empty root was accepted')
        except SystemExit as exc:
            assert 'non-empty' in str(exc)
    with patch.dict(os.environ, {'HARR_WORKSPACE_ROOT': str(home)}):
        # Rust's workspace-admin validation rejects unsafe broad roots such as HOME.
        assert m.mcp_workspace_root() == home.resolve()
    os.environ.pop('HARR_WORKSPACE_ROOT', None)
    with patch.object(m.Path, 'cwd', return_value=child):
        assert m.mcp_workspace_root() == repo.resolve()
print('PASS: Harr owns deterministic per-project Workspace store and MCP strict-mode selection')
