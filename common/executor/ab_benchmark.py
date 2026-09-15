#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from codex_cli import EXECUTOR_RULES, PROTOCOL, CodexCliAdapter
from service import ExecutorService

DEFAULT_PLANNER_MODEL = "gpt-5.6-sol"
DEFAULT_PLANNER_REASONING = "high"
DEFAULT_EXECUTOR_MODEL = "gpt-5.6-luna"
DEFAULT_EXECUTOR_REASONING = "low"
USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)


class BenchmarkError(RuntimeError):
    pass


@dataclass(frozen=True)
class NativeTurn:
    parent_thread_id: str
    child_thread_id: str
    parent_usage: dict[str, int]
    child_packet: dict[str, Any]
    child_usage: dict[str, int]
    child_model: str | None
    child_reasoning_effort: str | None
    child_rollout: str | None
    stdout_events: tuple[dict[str, Any], ...]
    stderr: str


def _run(argv: list[str], *, cwd: Path | None = None, input_text: str | None = None, env: dict[str, str] | None = None, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        input=input_text,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
    )


def git(root: Path, *args: str, check: bool = True) -> str:
    proc = _run(["git", "-C", str(root), *args], timeout=60)
    if check and proc.returncode != 0:
        raise BenchmarkError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def canonical_git_root(path: Path) -> Path:
    requested = path.expanduser().resolve()
    root = Path(git(requested, "rev-parse", "--show-toplevel")).resolve()
    if root != requested:
        raise BenchmarkError(f"--repo must be the Git worktree root: {root}")
    return root


def usage_zero() -> dict[str, int]:
    return {key: 0 for key in USAGE_FIELDS}


def normalize_usage(value: object) -> dict[str, int]:
    result = usage_zero()
    if not isinstance(value, dict):
        return result
    for key in USAGE_FIELDS:
        try:
            result[key] = int(value.get(key, 0) or 0)
        except (TypeError, ValueError):
            result[key] = 0
    return result


def add_usage(*values: dict[str, int]) -> dict[str, int]:
    return {key: sum(int(value.get(key, 0)) for value in values) for key in USAGE_FIELDS}


def parse_jsonl(text: str) -> tuple[dict[str, Any], ...]:
    items: list[dict[str, Any]] = []
    for raw in text.splitlines():
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            items.append(value)
    return tuple(items)


def parent_usage(events: Iterable[dict[str, Any]]) -> dict[str, int]:
    total = usage_zero()
    for event in events:
        if event.get("type") == "turn.completed":
            total = add_usage(total, normalize_usage(event.get("usage")))
    return total


def thread_id(events: Iterable[dict[str, Any]]) -> str | None:
    for event in events:
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            return str(event["thread_id"])
    return None


def spawned_child_ids(events: Iterable[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for event in events:
        if event.get("type") not in {"item.started", "item.updated", "item.completed"}:
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "collab_tool_call":
            continue
        if str(item.get("tool", "")).lower() != "spawn_agent":
            continue
        receivers = item.get("receiver_thread_ids")
        if isinstance(receivers, list):
            for receiver in receivers:
                if isinstance(receiver, str) and receiver and receiver not in result:
                    result.append(receiver)
    return result


def recursive_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from recursive_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from recursive_strings(child)


def packet_from_rollout_lines(lines: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for line in lines:
        for text in recursive_strings(line):
            stripped = text.strip()
            if not stripped.startswith("{") or PROTOCOL not in stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("protocol") == PROTOCOL:
                candidates.append(value)
    return candidates[-1] if candidates else None


def find_rollout(codex_home: Path, child_thread_id: str, *, wait_seconds: float = 5.0) -> Path | None:
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        candidates: list[Path] = []
        for base_name in ("sessions", "archived_sessions"):
            base = codex_home / base_name
            if not base.exists():
                continue
            candidates.extend(path for path in base.rglob(f"*{child_thread_id}*.jsonl") if path.is_file())
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime_ns)
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.1)


def read_rollout(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def rollout_usage(lines: Iterable[dict[str, Any]]) -> dict[str, int]:
    latest = usage_zero()
    for line in lines:
        if line.get("type") != "event_msg":
            continue
        payload = line.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, dict):
            continue
        total = info.get("total_token_usage")
        if isinstance(total, dict):
            latest = normalize_usage(total)
    return latest


def rollout_model(lines: Iterable[dict[str, Any]]) -> tuple[str | None, str | None]:
    model: str | None = None
    effort: str | None = None
    for line in lines:
        if line.get("type") != "turn_context":
            continue
        payload = line.get("payload")
        if not isinstance(payload, dict):
            continue
        candidate_model = payload.get("model") or payload.get("model_slug")
        candidate_effort = payload.get("reasoning_effort")
        if isinstance(candidate_model, str) and candidate_model:
            model = candidate_model
        if isinstance(candidate_effort, str) and candidate_effort:
            effort = candidate_effort
    return model, effort


def validate_packet(packet: dict[str, Any]) -> None:
    CodexCliAdapter._validate_packet(packet)


def native_initial_prompt(contract: str, executor_model: str, executor_reasoning: str) -> str:
    child_message = f"{EXECUTOR_RULES}\n\n{contract.strip()}\n"
    return f"""You are the Harr A/B benchmark orchestration parent. Do not inspect repository files, edit files, run builds/tests, solve design questions, or implement the task yourself.

Spawn exactly one native Codex child agent with these exact properties:
- task_name: harr_ab_builder
- fork_turns: \"none\"
- model: {executor_model}
- reasoning_effort: {executor_reasoning}
- message: the exact executor message between HARR_CHILD_MESSAGE markers below

Then wait until that child reaches a terminal response. Do not answer a BLOCKED decision. Do not send any follow-up. Do not spawn any other agent. Your own final response must only say HARR_AB_NATIVE_TURN_COMPLETE.

HARR_CHILD_MESSAGE_BEGIN
{child_message}
HARR_CHILD_MESSAGE_END
"""


def native_followup_prompt(resolution: str) -> str:
    return f"""Continue the Harr A/B native-subagent benchmark. Do not inspect/edit/build/test or solve anything yourself. Do not spawn another child.

Send exactly one follow-up task to the existing native child `harr_ab_builder` using the native multi-agent follow-up mechanism. The child must receive only the planner resolution delta between the markers below, with this prefix:

Continue the same Harr execution run. The previous Execution Contract remains authoritative. Apply only this Planner Resolution Delta, continue from the blocked step, and return only the Harr terminal JSON packet.

Wait until the same child reaches a terminal response. Do not make any additional decision. Your own final response must only say HARR_AB_NATIVE_TURN_COMPLETE.

HARR_PLANNER_RESOLUTION_BEGIN
{resolution.strip()}
HARR_PLANNER_RESOLUTION_END
"""


def codex_parent_argv(*, command: str, repo: Path, planner_model: str, planner_reasoning: str, executor_model: str, executor_reasoning: str, parent_session: str | None) -> list[str]:
    argv = [
        command,
        "exec",
        "--json",
        "--model",
        planner_model,
        "--sandbox",
        "workspace-write",
        "--cd",
        str(repo),
        "--config",
        f'model_reasoning_effort="{planner_reasoning}"',
        "--config",
        "agents.enabled=true",
        "--config",
        "features.multi_agent=true",
        "--config",
        "features.multi_agent_v2.enabled=true",
        "--config",
        f'agents.default_subagent_model="{executor_model}"',
        "--config",
        f'agents.default_subagent_reasoning_effort="{executor_reasoning}"',
        "--config",
        "sandbox_workspace_write.network_access=false",
        "--config",
        'web_search="disabled"',
    ]
    if parent_session:
        argv += ["resume", parent_session]
    argv.append("-")
    return argv


def run_native_turn(*, command: str, repo: Path, prompt: str, planner_model: str, planner_reasoning: str, executor_model: str, executor_reasoning: str, parent_session: str | None, expected_child: str | None, codex_home: Path) -> NativeTurn:
    resolved = shutil.which(command)
    if not resolved:
        raise BenchmarkError(f"Codex CLI not found: {command}")
    argv = codex_parent_argv(
        command=resolved,
        repo=repo,
        planner_model=planner_model,
        planner_reasoning=planner_reasoning,
        executor_model=executor_model,
        executor_reasoning=executor_reasoning,
        parent_session=parent_session,
    )
    env = os.environ.copy()
    env["HARR_EXECUTOR_CHILD"] = "1"
    proc = _run(argv, input_text=prompt, env=env)
    events = parse_jsonl(proc.stdout)
    observed_parent = thread_id(events) or parent_session
    if not observed_parent:
        raise BenchmarkError("native benchmark parent emitted no thread.started id")
    if parent_session and observed_parent != parent_session:
        raise BenchmarkError(f"native parent resumed unexpected session: {observed_parent}")
    if proc.returncode != 0:
        raise BenchmarkError(f"native benchmark parent failed ({proc.returncode}): {proc.stderr[-4000:]}")
    spawned = spawned_child_ids(events)
    if expected_child is None:
        if len(spawned) != 1:
            raise BenchmarkError(f"native arm expected exactly one spawned child, observed {spawned}")
        child = spawned[0]
    else:
        if spawned:
            raise BenchmarkError(f"native follow-up spawned a new child instead of reusing {expected_child}: {spawned}")
        child = expected_child

    rollout = find_rollout(codex_home, child)
    if rollout is None:
        raise BenchmarkError(f"native child rollout not found for thread {child} under {codex_home}")
    lines = read_rollout(rollout)
    packet = packet_from_rollout_lines(lines)
    if packet is None:
        raise BenchmarkError(f"native child {child} rollout has no {PROTOCOL} terminal packet")
    validate_packet(packet)
    child_usage = rollout_usage(lines)
    observed_model, observed_effort = rollout_model(lines)
    return NativeTurn(
        parent_thread_id=observed_parent,
        child_thread_id=child,
        parent_usage=parent_usage(events),
        child_packet=packet,
        child_usage=child_usage,
        child_model=observed_model,
        child_reasoning_effort=observed_effort,
        child_rollout=str(rollout),
        stdout_events=events,
        stderr=proc.stderr,
    )


def git_changed_paths(root: Path) -> list[str]:
    raw = _run(["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"]).stdout
    items = raw.split("\0")
    result: list[str] = []
    index = 0
    while index < len(items):
        entry = items[index]
        index += 1
        if not entry or len(entry) < 4:
            continue
        code = entry[:2]
        path = entry[3:].replace("\\", "/")
        result.append(path)
        if ("R" in code or "C" in code) and index < len(items) and items[index]:
            result.append(items[index].replace("\\", "/"))
            index += 1
    return sorted(set(result))


def path_allowed(path: str, patterns: list[str]) -> bool:
    import fnmatch

    for raw in patterns:
        pattern = raw.replace("\\", "/")
        if pattern.endswith("/") and path.startswith(pattern):
            return True
        if any(char in pattern for char in "*?[") and fnmatch.fnmatchcase(path, pattern):
            return True
        if path == pattern:
            return True
    return False


def native_arm(*, repo: Path, contract: str, allowed_paths: list[str], resolutions: list[str], command: str, planner_model: str, planner_reasoning: str, executor_model: str, executor_reasoning: str, codex_home: Path) -> dict[str, Any]:
    started = time.monotonic()
    parent_session: str | None = None
    child_session: str | None = None
    parent_total = usage_zero()
    blocker_turns = 0
    turn_count = 0
    observed_model: str | None = None
    observed_effort: str | None = None
    packet: dict[str, Any] | None = None
    rollout: str | None = None
    for index in range(len(resolutions) + 1):
        prompt = (
            native_initial_prompt(contract, executor_model, executor_reasoning)
            if index == 0
            else native_followup_prompt(resolutions[index - 1])
        )
        turn = run_native_turn(
            command=command,
            repo=repo,
            prompt=prompt,
            planner_model=planner_model,
            planner_reasoning=planner_reasoning,
            executor_model=executor_model,
            executor_reasoning=executor_reasoning,
            parent_session=parent_session,
            expected_child=child_session,
            codex_home=codex_home,
        )
        turn_count += 1
        parent_session = turn.parent_thread_id
        child_session = turn.child_thread_id
        parent_total = add_usage(parent_total, turn.parent_usage)
        packet = turn.child_packet
        rollout = turn.child_rollout
        observed_model = turn.child_model or observed_model
        observed_effort = turn.child_reasoning_effort or observed_effort
        if packet.get("state") != "BLOCKED":
            break
        blocker_turns += 1
        if index >= len(resolutions):
            break

    assert packet is not None and child_session is not None and parent_session is not None
    rollout_path = Path(rollout) if rollout else find_rollout(codex_home, child_session)
    final_child_usage = rollout_usage(read_rollout(rollout_path)) if rollout_path and rollout_path.exists() else usage_zero()
    changed = git_changed_paths(repo)
    out_of_scope = [path for path in changed if not path_allowed(path, allowed_paths)]
    return {
        "state": packet.get("state"),
        "packet": packet,
        "parent_thread_id": parent_session,
        "child_thread_id": child_session,
        "child_rollout": str(rollout_path) if rollout_path else None,
        "child_usage": final_child_usage,
        "orchestrator_usage": parent_total,
        "observed_child_model": observed_model,
        "observed_child_reasoning_effort": observed_effort,
        "turns": turn_count,
        "blocker_turns": blocker_turns,
        "wall_ms": round((time.monotonic() - started) * 1000),
        "changed_paths": changed,
        "out_of_scope": out_of_scope,
    }


def wait_bridge(svc: ExecutorService, snapshot: dict[str, Any]) -> dict[str, Any]:
    current = snapshot
    while current.get("state") == "RUNNING":
        current = svc.wait(
            run_id=str(current["run_id"]),
            after_sequence=int(current["sequence"]),
            timeout_seconds=45,
        )
    return current


def bridge_arm(*, repo: Path, contract: str, allowed_paths: list[str], required_steps: list[str], required_validation: list[str], resolutions: list[str], executor_model: str, executor_reasoning: str, state_root: Path) -> dict[str, Any]:
    started_at = time.monotonic()
    svc = ExecutorService(model=executor_model, reasoning_effort=executor_reasoning, state_root=state_root)
    current = svc.start(
        repo_root=str(repo),
        task_label="ab-benchmark",
        execution_contract=contract,
        allowed_paths=allowed_paths,
        required_steps=required_steps,
        required_validation=required_validation,
    )
    blocker_turns = 0
    resolution_index = 0
    while True:
        current = wait_bridge(svc, current)
        if current.get("state") != "BLOCKED":
            break
        blocker_turns += 1
        if resolution_index >= len(resolutions):
            break
        current = svc.continue_run(
            run_id=str(current["run_id"]),
            expected_sequence=int(current["sequence"]),
            resolution_delta=resolutions[resolution_index],
        )
        resolution_index += 1
    return {
        "state": current.get("state"),
        "packet": {
            "protocol": current.get("protocol"),
            "state": current.get("state"),
            "current_step": current.get("current_step"),
            "completed_steps": current.get("completed_steps"),
            "summary": current.get("summary"),
            "validation": current.get("validation"),
            "blocker": current.get("blocker"),
        },
        "run_id": current.get("run_id"),
        "session_id": _read_run_session_id(state_root, str(current["run_id"])),
        "executor_usage": current.get("usage", {}).get("total", usage_zero()),
        "turns": 1 + resolution_index,
        "blocker_turns": blocker_turns,
        "wall_ms": round((time.monotonic() - started_at) * 1000),
        "changed_paths": current.get("workspace", {}).get("changed_paths", []),
        "out_of_scope": current.get("workspace", {}).get("out_of_scope", []),
        "artifacts": current.get("artifacts", []),
    }


def _read_run_session_id(state_root: Path, run_id: str) -> str | None:
    run_dir = state_root / "runs" / run_id
    for path in sorted(run_dir.glob("events-r*.ndjson"), reverse=True):
        for event in parse_jsonl(path.read_text(encoding="utf-8", errors="replace")):
            if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
                return str(event["thread_id"])
    return None


def comparison(native: dict[str, Any], bridge: dict[str, Any]) -> dict[str, Any]:
    a = normalize_usage(native.get("child_usage"))
    b = normalize_usage(bridge.get("executor_usage"))
    metrics: dict[str, Any] = {}
    for key in USAGE_FIELDS:
        av = a[key]
        bv = b[key]
        metrics[key] = {
            "native": av,
            "bridge": bv,
            "delta_bridge_minus_native": bv - av,
            "bridge_over_native": (round(bv / av, 4) if av else None),
        }
    native_uncached = max(0, a["input_tokens"] - a["cached_input_tokens"])
    bridge_uncached = max(0, b["input_tokens"] - b["cached_input_tokens"])
    metrics["uncached_input_tokens_derived"] = {
        "native": native_uncached,
        "bridge": bridge_uncached,
        "delta_bridge_minus_native": bridge_uncached - native_uncached,
        "bridge_over_native": (round(bridge_uncached / native_uncached, 4) if native_uncached else None),
    }
    return metrics


def render_table(report: dict[str, Any]) -> str:
    native = report["native"]
    bridge = report["bridge"]
    metrics = report["comparison"]
    rows = [
        ("input tokens", metrics["input_tokens"]),
        ("cached input", metrics["cached_input_tokens"]),
        ("uncached input*", metrics["uncached_input_tokens_derived"]),
        ("cache-write input", metrics["cache_write_input_tokens"]),
        ("output tokens", metrics["output_tokens"]),
        ("reasoning output", metrics["reasoning_output_tokens"]),
    ]
    out = [
        "Harr Codex executor A/B",
        f"contract: {report['contract']['bytes']} bytes, sha256={report['contract']['sha256'][:12]}",
        "",
        f"{'metric':<24} {'native Luna':>14} {'bridge Luna':>14} {'B-A':>12}",
        "-" * 68,
    ]
    for label, row in rows:
        out.append(f"{label:<24} {row['native']:>14} {row['bridge']:>14} {row['delta_bridge_minus_native']:>12}")
    out.extend(
        [
            "",
            f"native state: {native.get('state')}  turns={native.get('turns')}  blockers={native.get('blocker_turns')}  wall={native.get('wall_ms')} ms",
            f"bridge state: {bridge.get('state')}  turns={bridge.get('turns')}  blockers={bridge.get('blocker_turns')}  wall={bridge.get('wall_ms')} ms",
            f"native child observed: model={native.get('observed_child_model') or '?'} effort={native.get('observed_child_reasoning_effort') or '?'}",
            f"native parent/orchestrator usage (not included above): {json.dumps(native.get('orchestrator_usage', {}), sort_keys=True)}",
            f"scope violations: native={native.get('out_of_scope', [])} bridge={bridge.get('out_of_scope', [])}",
            "",
            "* uncached input is derived as max(input_tokens - cached_input_tokens, 0).",
            "Token telemetry is not the same thing as ChatGPT/Codex subscription usage units.",
        ]
    )
    return "\n".join(out)


def create_worktree(source: Path, target: Path, head: str) -> None:
    proc = _run(["git", "-C", str(source), "worktree", "add", "--detach", str(target), head], timeout=120)
    if proc.returncode != 0:
        raise BenchmarkError(proc.stderr.strip() or "git worktree add failed")


def remove_worktree(source: Path, target: Path) -> None:
    _run(["git", "-C", str(source), "worktree", "remove", "--force", str(target)], timeout=120)


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B native Codex Luna subagent vs persistent Codex CLI Luna executor")
    parser.add_argument("--repo", type=Path, required=True, help="Git worktree root; benchmark uses detached temporary worktrees from its HEAD")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--allowed-path", action="append", default=[], required=True)
    parser.add_argument("--required-step", action="append", default=[])
    parser.add_argument("--required-validation", action="append", default=[])
    parser.add_argument("--resolution", type=Path, action="append", default=[])
    parser.add_argument("--planner-model", default=DEFAULT_PLANNER_MODEL)
    parser.add_argument("--planner-reasoning", default=DEFAULT_PLANNER_REASONING)
    parser.add_argument("--executor-model", default=DEFAULT_EXECUTOR_MODEL)
    parser.add_argument("--executor-reasoning", default=DEFAULT_EXECUTOR_REASONING)
    parser.add_argument("--codex-command", default="codex")
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--order", choices=("native-first", "bridge-first"), default="native-first")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--keep-worktrees", action="store_true")
    args = parser.parse_args()

    source = canonical_git_root(args.repo)
    contract = args.contract.read_text(encoding="utf-8")
    if not contract.strip():
        raise BenchmarkError("execution contract is empty")
    resolutions = [path.read_text(encoding="utf-8") for path in args.resolution]
    head = git(source, "rev-parse", "HEAD")
    benchmark_id = "ab_" + uuid.uuid4().hex[:12]

    temp = Path(tempfile.mkdtemp(prefix=f"harr-{benchmark_id}-"))
    native_repo = temp / "native"
    bridge_repo = temp / "bridge"
    state_root = temp / "bridge-state"
    create_worktree(source, native_repo, head)
    create_worktree(source, bridge_repo, head)

    def run_native() -> dict[str, Any]:
        return native_arm(
            repo=native_repo,
            contract=contract,
            allowed_paths=args.allowed_path,
            resolutions=resolutions,
            command=args.codex_command,
            planner_model=args.planner_model,
            planner_reasoning=args.planner_reasoning,
            executor_model=args.executor_model,
            executor_reasoning=args.executor_reasoning,
            codex_home=args.codex_home.expanduser().resolve(),
        )

    def run_bridge() -> dict[str, Any]:
        return bridge_arm(
            repo=bridge_repo,
            contract=contract,
            allowed_paths=args.allowed_path,
            required_steps=args.required_step,
            required_validation=args.required_validation,
            resolutions=resolutions,
            executor_model=args.executor_model,
            executor_reasoning=args.executor_reasoning,
            state_root=state_root,
        )

    try:
        if args.order == "native-first":
            native = run_native()
            bridge = run_bridge()
        else:
            bridge = run_bridge()
            native = run_native()
        report = {
            "schema": 1,
            "benchmark_id": benchmark_id,
            "repo": str(source),
            "repo_head": head,
            "contract": {
                "path": str(args.contract.resolve()),
                "bytes": len(contract.encode("utf-8")),
                "chars": len(contract),
                "sha256": hashlib.sha256(contract.encode("utf-8")).hexdigest(),
            },
            "models": {
                "planner": args.planner_model,
                "planner_reasoning": args.planner_reasoning,
                "executor": args.executor_model,
                "executor_reasoning": args.executor_reasoning,
            },
            "order": args.order,
            "native": native,
            "bridge": bridge,
        }
        report["comparison"] = comparison(native, bridge)
        if args.output:
            output = args.output.expanduser().resolve()
        else:
            state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
            output = state_home / "harr" / "executor" / "benchmarks" / f"{benchmark_id}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(render_table(report))
        print(f"\nreport: {output}")
        if args.keep_worktrees:
            print(f"native worktree: {native_repo}")
            print(f"bridge worktree: {bridge_repo}")
        return 0
    finally:
        if not args.keep_worktrees:
            if native_repo.exists():
                remove_worktree(source, native_repo)
            if bridge_repo.exists():
                remove_worktree(source, bridge_repo)
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BenchmarkError, OSError, subprocess.SubprocessError) as exc:
        print(f"A/B benchmark failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
