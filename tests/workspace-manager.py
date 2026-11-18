#!/usr/bin/env python3
import importlib.util, json, os, subprocess, sys, tempfile
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
    fake.write_text('''#!/usr/bin/env python3\nimport json,sys,uuid\nfrom pathlib import Path\na=sys.argv[1:]\nif a==["harr-capabilities","--json"]:\n print(json.dumps({"schema_version":1,"runtime":"lean-ctx","capabilities":["authority-mode-v1","no-workspace-v1","workspace-sibling-checkouts-v1"]})); sys.exit(0)\nif a[:2]==["workspace-admin","create"]:\n p=Path(a[2]); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps({"id":str(uuid.uuid4()),"revision":1,"primary":str(Path(a[3]).resolve()),"additional":[]})); p.chmod(0o600); sys.exit(0)\nif a[:2]==["workspace-admin","show"]:\n print(Path(a[2]).read_text()); sys.exit(0)\nif a[:2]==["workspace-admin","reconcile"]:\n print(Path(a[2]).read_text()); sys.exit(0)\nsys.exit(2)\n'''); fake.chmod(0o755)
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
                assert exec_mock.call_args.args[2]['LEAN_CTX_STRICT_WORKSPACE_LEGACY_TOOLS'] == '1'
                assert exec_mock.call_args.args[2]['LEAN_CTX_AUTHORITY_MODE'] == 'workspace'
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
    # `auto` never derives authority from the cwd: a Git checkout below the
    # process cwd grants nothing without an explicit root.
    with patch.object(m.Path, 'cwd', return_value=child):
        assert m.mcp_workspace_root() is None
        # `strict` keeps the existing resolver: nearest .git from the cwd.
        with patch.dict(os.environ, {'HARR_WORKSPACE_MODE': 'strict'}):
            assert m.resolve_mcp_authority() == ('workspace', repo.resolve())
    # `none` with any explicit root is a fatal conflict, never a downgrade.
    with patch.dict(os.environ, {'HARR_WORKSPACE_MODE': 'none', 'HARR_WORKSPACE_ROOT': str(repo)}):
        try:
            m.resolve_mcp_authority()
            raise AssertionError('none accepted an explicit root')
        except SystemExit as exc:
            assert 'cannot be combined' in str(exc)
    for bad_mode in ('', 'bogus', 'AUTOPILOT'):
        with patch.dict(os.environ, {'HARR_WORKSPACE_MODE': bad_mode}):
            try:
                m.resolve_mcp_authority()
                raise AssertionError(f'mode {bad_mode!r} was accepted')
            except SystemExit as exc:
                assert 'HARR_WORKSPACE_MODE' in str(exc)
    rootless_cfg = base/'rootless-config'
    with patch.dict(os.environ, {'HARR_WORKSPACE_MODE': 'auto', 'XDG_CONFIG_HOME': str(rootless_cfg)}):
        with patch.object(m.Path, 'cwd', return_value=home):
            assert m.mcp_workspace_root() is None
            with patch.object(m.os, 'execvpe', side_effect=RuntimeError('exec intercepted')) as exec_mock:
                try:
                    m.exec_leanctx(SimpleNamespace(real=str(fake), rest=['mcp']), {'servers': []})
                    raise AssertionError('exec should have been intercepted')
                except RuntimeError as exc:
                    assert str(exc) == 'exec intercepted'
                child_env = exec_mock.call_args.args[2]
                assert child_env['LEAN_CTX_AUTHORITY_MODE'] == 'none'
                assert 'LEAN_CTX_WORKSPACE_FILE' not in child_env
                assert 'LEAN_CTX_STRICT_WORKSPACE' not in child_env
                assert not (rootless_cfg/'harr'/'workspaces').exists()
    # The capability probe runs with launcher-owned authority variables cleared,
    # so a stale parent environment cannot influence runtime admission.
    with patch.dict(os.environ, {'LEAN_CTX_AUTHORITY_MODE': 'none', 'LEAN_CTX_WORKSPACE_FILE': '/stale', 'LEAN_CTX_STRICT_WORKSPACE': '1', 'LEAN_CTX_STRICT_WORKSPACE_LEGACY_TOOLS': '1'}):
        with patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"schema_version":1,"runtime":"lean-ctx","capabilities":["authority-mode-v1","no-workspace-v1","workspace-sibling-checkouts-v1"]}), stderr='')) as run_mock:
            m.verify_leanctx_capabilities(fake)
            probe_env = run_mock.call_args.kwargs['env']
            for key in m.LEANCTX_LAUNCHER_AUTHORITY_VARS:
                assert key not in probe_env, key
    os.environ.pop('LEAN_CTX_AUTHORITY_MODE', None); os.environ.pop('LEAN_CTX_WORKSPACE_FILE', None)
    os.environ.pop('LEAN_CTX_STRICT_WORKSPACE', None); os.environ.pop('LEAN_CTX_STRICT_WORKSPACE_LEGACY_TOOLS', None)
    # Explicit `legacy` is a separate branch: no probe, no store setup, only the
    # new mode variable is removed and the pre-Workspace variables survive.
    legacy_cfg = base/'legacy-config'
    with patch.dict(os.environ, {'HARR_WORKSPACE_MODE': 'legacy', 'HARR_WORKSPACE_ROOT': str(repo), 'LEAN_CTX_WORKSPACE_FILE': str(store), 'XDG_CONFIG_HOME': str(legacy_cfg)}):
        with patch.object(m.subprocess, 'run', side_effect=AssertionError('legacy must not probe or touch a store')):
            with patch.object(m.os, 'execvpe', side_effect=RuntimeError('exec intercepted')) as exec_mock:
                try:
                    m.exec_leanctx(SimpleNamespace(real=str(fake), rest=['mcp']), {'servers': []})
                    raise AssertionError('exec should have been intercepted')
                except RuntimeError as exc:
                    assert str(exc) == 'exec intercepted'
                legacy_env = exec_mock.call_args.args[2]
                assert 'LEAN_CTX_AUTHORITY_MODE' not in legacy_env
                assert legacy_env['LEAN_CTX_WORKSPACE_FILE'] == str(store)
                assert legacy_env['HARR_WORKSPACE_ROOT'] == str(repo)
                assert not (legacy_cfg/'harr'/'workspaces').exists()
    os.environ.pop('LEAN_CTX_WORKSPACE_FILE', None); os.environ.pop('HARR_WORKSPACE_ROOT', None)
    os.environ.pop('HARR_WORKSPACE_MODE', None)
    # Cooperative owner registry mechanics.
    owners_cfg = base/'owners-config'
    with patch.dict(os.environ, {'HARR_CONFIG_DIR': str(owners_cfg)}):
        assert m.owner_record_key('ck-1', 'gen-1') == m.owner_record_key('ck-1', 'gen-1')
        assert m.owner_record_key('ck-1', 'gen-1') != m.owner_record_key('ck-1', 'gen-2')
        assert m.owner_record_key('ck-1', 'gen-1') != m.owner_record_key('ck-2', 'gen-1')
        reg_path, lock_path = m.owner_registry_paths()
        # HARR_CONFIG_DIR overrides the whole harr config dir, so the registry
        # lives directly inside it.
        assert reg_path == owners_cfg/'worktree-owners.json'
        assert lock_path == owners_cfg/'worktree-owners.lock'
        assert m.read_owner_registry() == {'schema_version': 1, 'owners': {}}
        with m.WorktreeOwnerLock():
            registry = m.read_owner_registry()
            registry['owners'][m.owner_record_key('ck-1', 'gen-1')] = {
                'checkout_key': 'ck-1', 'checkout_generation': 'gen-1',
                'owner_id': 'task-a', 'owner_label': 'Task A', 'last_seen_at': '2026-11-17T00:00:00+00:00',
            }
            m.write_owner_registry_atomic(registry)
        assert (reg_path.stat().st_mode & 0o077) == 0
        assert m.read_owner_registry()['owners'][m.owner_record_key('ck-1', 'gen-1')]['owner_id'] == 'task-a'
        (reg_path).write_text('{ not json', encoding='utf-8')
        try:
            m.read_owner_registry()
            raise AssertionError('corrupt registry was treated as empty')
        except SystemExit as exc:
            assert 'corrupt' in str(exc)
        (reg_path).write_text('{"schema_version": 9, "owners": {}}', encoding='utf-8')
        try:
            m.read_owner_registry()
            raise AssertionError('unknown schema was treated as empty')
        except SystemExit as exc:
            assert 'schema' in str(exc)
        reg_path.unlink()
        # Owner command flow against a registered active binding.
        binding_root = str(repo.resolve())
        owner_store = m.workspace_store_path(repo)
        owner_store.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        owner_store.write_text(json.dumps({
            'id': '11111111-1111-4111-8111-111111111111', 'revision': 1,
            'primary': binding_root, 'additional': [],
            'checkout_bindings': {binding_root: {
                'repository_key': 'rk-1', 'checkout_key': 'ck-1',
                'checkout_generation': 'gen-1', 'git_common_dir': str(base/'git'),
                'git_dir': str(base/'git'),
            }},
            'primary_status': {'configured': binding_root, 'active': binding_root, 'state': 'active'},
            'additional_statuses': [],
        }), encoding='utf-8')
        owner_store.chmod(0o600)
        def owner_args(op, root, owner_id=None, owner_label=None, take_over_from=None):
            return SimpleNamespace(real=str(fake), project=str(repo), paths=[op, root],
                                   owner_id=owner_id, owner_label=owner_label, take_over_from=take_over_from)
        import contextlib, io
        def run_owner(*a, **kw):
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                m.workspace_owner_command(owner_args(*a, **kw))
            return json.loads(captured.getvalue())
        assert run_owner('get', binding_root)['owner'] is None
        # get on an unregistered sibling never grants authority.
        try:
            run_owner('get', str(home))
            raise AssertionError('unregistered root was accepted')
        except SystemExit as exc:
            assert 'not exactly registered' in str(exc)
        claimed = run_owner('claim', binding_root, owner_id='task-a', owner_label='Task A')
        assert claimed['status'] == 'claimed' and claimed['owner']['owner_id'] == 'task-a'
        updated = run_owner('claim', binding_root, owner_id='task-a')
        assert updated['status'] == 'reclaimed' and updated['owner']['owner_label'] == 'task-a'
        foreign = run_owner('claim', binding_root, owner_id='task-b')
        assert foreign['status'] == 'confirmation_required' and foreign['owner']['owner_id'] == 'task-a'
        stale = run_owner('claim', binding_root, owner_id='task-b', take_over_from='task-z')
        assert stale['status'] == 'owner_changed' and stale['owner']['owner_id'] == 'task-a'
        assert (reg_path).exists(), 'confirmation flow must not write the registry'
        moved = run_owner('claim', binding_root, owner_id='task-b', take_over_from='task-a')
        assert moved['status'] == 'transferred' and moved['previousOwner']['owner_id'] == 'task-a'
        assert 'task-a' in moved['note']
        wrong_release = run_owner('release', binding_root, owner_id='task-a')
        assert wrong_release['status'] == 'not_owner' and wrong_release['owner']['owner_id'] == 'task-b'
        released = run_owner('release', binding_root, owner_id='task-b')
        assert released['status'] == 'released' and released['owner'] is None
        absent = run_owner('release', binding_root, owner_id='task-b')
        assert absent['status'] == 'absent'
        # Exercise the public CLI parser and its owner-before-store-setup route,
        # not only the helper function used by the command handler.
        cli_env = os.environ.copy()
        cli_env['HARR_CONFIG_DIR'] = str(m.harr_config_dir())
        cli_env['XDG_CONFIG_HOME'] = str(cfg)
        cli_env['HOME'] = str(home)
        cli_base = [sys.executable, str(ROOT/'common/mcp/manager.py'), 'workspace', 'owner']
        cli_options = ['--real', str(fake), '--project', str(repo)]
        def run_owner_cli(operation, root, *options):
            result = subprocess.run(
                [*cli_base, operation, root, *cli_options, *options],
                cwd=ROOT, env=cli_env, capture_output=True, text=True,
            )
            return result
        cli_get = run_owner_cli('get', binding_root)
        assert cli_get.returncode == 0, (cli_get.stdout, cli_get.stderr)
        assert json.loads(cli_get.stdout)['owner'] is None
        cli_claim = run_owner_cli('claim', binding_root, '--owner-id', 'cli-a')
        assert cli_claim.returncode == 0, (cli_claim.stdout, cli_claim.stderr)
        assert json.loads(cli_claim.stdout)['status'] == 'claimed'
        cli_conflict = run_owner_cli('claim', binding_root, '--owner-id', 'cli-b')
        assert cli_conflict.returncode == 0, (cli_conflict.stdout, cli_conflict.stderr)
        assert json.loads(cli_conflict.stdout)['status'] == 'confirmation_required'
        cli_transfer = run_owner_cli(
            'claim', binding_root, '--owner-id', 'cli-b', '--take-over-from', 'cli-a'
        )
        assert cli_transfer.returncode == 0, (cli_transfer.stdout, cli_transfer.stderr)
        transfer_payload = json.loads(cli_transfer.stdout)
        assert transfer_payload['status'] == 'transferred'
        assert transfer_payload['previousOwner']['owner_id'] == 'cli-a'
        cli_release = run_owner_cli('release', binding_root, '--owner-id', 'cli-b')
        assert cli_release.returncode == 0, (cli_release.stdout, cli_release.stderr)
        assert json.loads(cli_release.stdout)['status'] == 'released'
        unregistered_cli = run_owner_cli('get', str(home))
        assert unregistered_cli.returncode != 0
        assert 'not exactly registered' in unregistered_cli.stderr
        assert not m.workspace_store_path(home).exists(), 'owner lookup created a Workspace for an unregistered root'
print('PASS: Harr authority resolver contract, capability probe hygiene, legacy branch and owner registry')
