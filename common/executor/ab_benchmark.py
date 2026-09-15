#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from codex_cli import EXECUTOR_RULES, PROTOCOL, TERMINAL_SCHEMA, CodexCliAdapter
from service import ExecutorService

USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")


class BenchmarkError(RuntimeError):
    pass


def run(argv: list[str], *, input_text: str | None = None, env: dict[str, str] | None = None, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, input=input_text, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=timeout)


def git(root: Path, *args: str) -> str:
    proc = run(["git", "-C", str(root), *args], timeout=120)
    if proc.returncode:
        raise BenchmarkError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def usage(value: object = None) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    result: dict[str, int] = {}
    for key in USAGE_FIELDS:
        try:
            result[key] = int(source.get(key, 0) or 0)
        except (TypeError, ValueError):
            result[key] = 0
    return result


def add_usage(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {key: int(a.get(key, 0)) + int(b.get(key, 0)) for key in USAGE_FIELDS}


def jsonl(text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def parent_usage(events: Iterable[dict[str, Any]]) -> dict[str, int]:
    result = usage()
    for event in events:
        if event.get("type") == "turn.completed":
            result = add_usage(result, usage(event.get("usage")))
    return result


def thread_id(events: Iterable[dict[str, Any]]) -> str | None:
    for event in events:
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            return str(event["thread_id"])
    return None


def spawned_child_ids(events: Iterable[dict[str, Any]]) -> list[str]:
    found: list[str] = []
    for event in events:
        item = event.get("item") if event.get("type") in {"item.started", "item.updated", "item.completed"} else None
        if not isinstance(item, dict) or item.get("type") != "collab_tool_call" or str(item.get("tool", "")).lower() != "spawn_agent":
            continue
        for child in item.get("receiver_thread_ids", []):
            if isinstance(child, str) and child and child not in found:
                found.append(child)
    return found


def walk_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_strings(child)


def find_rollout(codex_home: Path, child_id: str, wait_seconds: float = 5.0) -> Path | None:
    deadline = time.monotonic() + wait_seconds
    while True:
        matches: list[Path] = []
        for name in ("sessions", "archived_sessions"):
            base = codex_home / name
            if base.exists():
                matches.extend(path for path in base.rglob(f"*{child_id}*.jsonl") if path.is_file())
        if matches:
            return max(matches, key=lambda path: path.stat().st_mtime_ns)
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.1)


def rollout_lines(path: Path) -> list[dict[str, Any]]:
    return jsonl(path.read_text(encoding="utf-8", errors="replace"))


def packet_from_rollout_lines(lines: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    packets: list[dict[str, Any]] = []
    for line in lines:
        for text in walk_strings(line):
            text = text.strip()
            if not text.startswith("{") or PROTOCOL not in text:
                continue
            try:
                candidate = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and candidate.get("protocol") == PROTOCOL:
                packets.append(candidate)
    return packets[-1] if packets else None


def rollout_usage(lines: Iterable[dict[str, Any]]) -> dict[str, int]:
    result = usage()
    for line in lines:
        payload = line.get("payload") if line.get("type") == "event_msg" else None
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if isinstance(info, dict) and isinstance(info.get("total_token_usage"), dict):
            result = usage(info["total_token_usage"])
    return result


def rollout_model(lines: Iterable[dict[str, Any]]) -> tuple[str | None, str | None]:
    model = effort = None
    for line in lines:
        payload = line.get("payload") if line.get("type") == "turn_context" else None
        if not isinstance(payload, dict):
            continue
        if isinstance(payload.get("model"), str):
            model = str(payload["model"])
        elif isinstance(payload.get("model_slug"), str):
            model = str(payload["model_slug"])
        if isinstance(payload.get("reasoning_effort"), str):
            effort = str(payload["reasoning_effort"])
    return model, effort


def native_initial_prompt(contract: str, model: str, reasoning: str) -> str:
    schema = json.dumps(TERMINAL_SCHEMA, ensure_ascii=False, separators=(",", ":"))
    child = f"{EXECUTOR_RULES}\n\nTerminal response JSON Schema (mandatory):\n{schema}\n\n{contract.strip()}\n"
    return f"""You are only the native-subagent transport for a Harr A/B benchmark. Do not inspect/edit/build/test or solve the implementation yourself.
Spawn exactly one child with task_name=harr_ab_builder, fork_turns=\"none\", model={model}, reasoning_effort={reasoning}. Pass the exact HARR_CHILD_MESSAGE below as its message. Wait for the child to finish once. Do not resolve BLOCKED and do not send a follow-up. Do not spawn any other child. Your final response must only say HARR_AB_NATIVE_TURN_COMPLETE.
HARR_CHILD_MESSAGE_BEGIN
{child}
HARR_CHILD_MESSAGE_END
"""


def native_followup_prompt(delta: str) -> str:
    return f"""Continue only as the native-subagent transport for the Harr A/B benchmark. Do not inspect/edit/build/test, solve the blocker, or spawn another child.
Send exactly one native follow-up task to the existing child harr_ab_builder. The message must say that the previous Execution Contract remains authoritative, apply only the Planner Resolution Delta below, continue from the blocked step, and return only the Harr terminal JSON packet. Wait for that same child to finish once. Your final response must only say HARR_AB_NATIVE_TURN_COMPLETE.
HARR_PLANNER_RESOLUTION_BEGIN
{delta.strip()}
HARR_PLANNER_RESOLUTION_END
"""


def native_argv(command: str, repo: Path, planner_model: str, planner_reasoning: str, executor_model: str, executor_reasoning: str, parent_id: str | None) -> list[str]:
    argv = [
        command, "exec", "--json", "--model", planner_model, "--sandbox", "workspace-write", "--cd", str(repo),
        "--config", f'model_reasoning_effort="{planner_reasoning}"',
        "--config", "agents.enabled=true",
        "--config", "features.multi_agent=true",
        "--config", "features.multi_agent_v2.enabled=true",
        "--config", f'agents.default_subagent_model="{executor_model}"',
        "--config", f'agents.default_subagent_reasoning_effort="{executor_reasoning}"',
        "--config", "sandbox_workspace_write.network_access=false",
        "--config", 'web_search="disabled"',
    ]
    if parent_id:
        argv += ["resume", parent_id]
    return [*argv, "-"]


def native_turn(*, repo: Path, prompt: str, command: str, planner_model: str, planner_reasoning: str, executor_model: str, executor_reasoning: str, codex_home: Path, parent_id: str | None, child_id: str | None) -> tuple[str, str, dict[str, int], dict[str, Any], dict[str, int], str | None, str | None, str]:
    executable = shutil.which(command)
    if not executable:
        raise BenchmarkError(f"Codex CLI not found: {command}")
    env = os.environ.copy()
    env["HARR_EXECUTOR_CHILD"] = "1"
    proc = run(native_argv(executable, repo, planner_model, planner_reasoning, executor_model, executor_reasoning, parent_id), input_text=prompt, env=env)
    events = jsonl(proc.stdout)
    observed_parent = thread_id(events) or parent_id
    if proc.returncode or not observed_parent:
        raise BenchmarkError(f"native parent failed: {proc.stderr[-4000:]}")
    spawned = spawned_child_ids(events)
    if child_id is None:
        if len(spawned) != 1:
            raise BenchmarkError(f"native arm expected one spawned child, observed {spawned}")
        observed_child = spawned[0]
    else:
        if spawned:
            raise BenchmarkError(f"native follow-up spawned replacement child(s): {spawned}")
        observed_child = child_id
    rollout = find_rollout(codex_home, observed_child)
    if rollout is None:
        raise BenchmarkError(f"no native child rollout for {observed_child}")
    lines = rollout_lines(rollout)
    packet = packet_from_rollout_lines(lines)
    if packet is None:
        raise BenchmarkError("native child produced no Harr terminal packet")
    CodexCliAdapter._validate_packet(packet)
    model, effort = rollout_model(lines)
    return observed_parent, observed_child, parent_usage(events), packet, rollout_usage(lines), model, effort, str(rollout)


def changed_paths(root: Path) -> list[str]:
    proc = run(["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"])
    if proc.returncode:
        raise BenchmarkError(proc.stderr.strip() or "git status failed")
    fields = proc.stdout.split("\0")
    result: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if not entry or len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:].replace("\\", "/")
        result.append(path)
        if ("R" in code or "C" in code) and i < len(fields) and fields[i]:
            result.append(fields[i].replace("\\", "/")); i += 1
    return sorted(set(result))


def allowed(path: str, patterns: list[str]) -> bool:
    for raw in patterns:
        pattern = raw.replace("\\", "/")
        if pattern.endswith("/") and path.startswith(pattern):
            return True
        if any(char in pattern for char in "*?[") and fnmatch.fnmatchcase(path, pattern):
            return True
        if path == pattern:
            return True
    return False


def native_arm(args: argparse.Namespace, repo: Path, contract: str, resolutions: list[str], codex_home: Path) -> dict[str, Any]:
    started = time.monotonic()
    parent_id = child_id = None
    parent_total = usage()
    packet: dict[str, Any] | None = None
    child_total = usage()
    observed_model = observed_effort = rollout = None
    blockers = 0
    turns = 0
    for index in range(len(resolutions) + 1):
        prompt = native_initial_prompt(contract, args.executor_model, args.executor_reasoning) if index == 0 else native_followup_prompt(resolutions[index - 1])
        parent_id, child_id, pusage, packet, child_total, model, effort, rollout = native_turn(
            repo=repo, prompt=prompt, command=args.codex_command,
            planner_model=args.planner_model, planner_reasoning=args.planner_reasoning,
            executor_model=args.executor_model, executor_reasoning=args.executor_reasoning,
            codex_home=codex_home, parent_id=parent_id, child_id=child_id,
        )
        parent_total = add_usage(parent_total, pusage); turns += 1
        observed_model = model or observed_model; observed_effort = effort or observed_effort
        if packet.get("state") != "BLOCKED":
            break
        blockers += 1
        if index == len(resolutions):
            break
    assert packet is not None and parent_id and child_id
    paths = changed_paths(repo)
    return {
        "state": packet.get("state"), "packet": packet, "parent_thread_id": parent_id, "child_thread_id": child_id,
        "child_rollout": rollout, "child_usage": child_total, "orchestrator_usage": parent_total,
        "observed_child_model": observed_model, "observed_child_reasoning_effort": observed_effort,
        "turns": turns, "blocker_turns": blockers, "wall_ms": round((time.monotonic() - started) * 1000),
        "changed_paths": paths, "out_of_scope": [path for path in paths if not allowed(path, args.allowed_path)],
    }


def bridge_wait(service: ExecutorService, current: dict[str, Any]) -> dict[str, Any]:
    while current.get("state") == "RUNNING":
        current = service.wait(run_id=str(current["run_id"]), after_sequence=int(current["sequence"]), timeout_seconds=45)
    return current


def bridge_arm(args: argparse.Namespace, repo: Path, contract: str, resolutions: list[str], state_root: Path) -> dict[str, Any]:
    started = time.monotonic()
    service = ExecutorService(model=args.executor_model, reasoning_effort=args.executor_reasoning, state_root=state_root)
    current = service.start(repo_root=str(repo), task_label="ab-benchmark", execution_contract=contract,
                            allowed_paths=args.allowed_path, required_steps=args.required_step,
                            required_validation=args.required_validation)
    used_resolutions = blockers = 0
    while True:
        current = bridge_wait(service, current)
        if current.get("state") != "BLOCKED":
            break
        blockers += 1
        if used_resolutions >= len(resolutions):
            break
        current = service.continue_run(run_id=str(current["run_id"]), expected_sequence=int(current["sequence"]), resolution_delta=resolutions[used_resolutions])
        used_resolutions += 1
    return {
        "state": current.get("state"), "packet": {key: current.get(key) for key in ("protocol", "state", "current_step", "completed_steps", "summary", "validation", "blocker")},
        "run_id": current.get("run_id"), "executor_usage": current.get("usage", {}).get("total", usage()),
        "turns": 1 + used_resolutions, "blocker_turns": blockers, "wall_ms": round((time.monotonic() - started) * 1000),
        "changed_paths": current.get("workspace", {}).get("changed_paths", []), "out_of_scope": current.get("workspace", {}).get("out_of_scope", []),
        "artifacts": current.get("artifacts", []),
    }


def comparison(native: dict[str, Any], bridge: dict[str, Any]) -> dict[str, Any]:
    a, b = usage(native.get("child_usage")), usage(bridge.get("executor_usage"))
    result: dict[str, Any] = {}
    for key in USAGE_FIELDS:
        result[key] = {"native": a[key], "bridge": b[key], "delta_bridge_minus_native": b[key] - a[key], "bridge_over_native": round(b[key] / a[key], 4) if a[key] else None}
    au, bu = max(0, a["input_tokens"] - a["cached_input_tokens"]), max(0, b["input_tokens"] - b["cached_input_tokens"])
    result["uncached_input_tokens_derived"] = {"native": au, "bridge": bu, "delta_bridge_minus_native": bu - au, "bridge_over_native": round(bu / au, 4) if au else None}
    return result


def table(report: dict[str, Any]) -> str:
    metrics = report["comparison"]
    labels = (("input tokens", "input_tokens"), ("cached input", "cached_input_tokens"), ("uncached input*", "uncached_input_tokens_derived"),
              ("cache-write input", "cache_write_input_tokens"), ("output tokens", "output_tokens"), ("reasoning output", "reasoning_output_tokens"))
    lines = ["Harr Codex executor A/B", f"contract: {report['contract']['bytes']} bytes, sha256={report['contract']['sha256'][:12]}", "",
             f"{'metric':<24} {'native Luna':>14} {'bridge Luna':>14} {'B-A':>12}", "-" * 68]
    for label, key in labels:
        row = metrics[key]; lines.append(f"{label:<24} {row['native']:>14} {row['bridge']:>14} {row['delta_bridge_minus_native']:>12}")
    n, b = report["native"], report["bridge"]
    lines += ["", f"native state: {n['state']} turns={n['turns']} blockers={n['blocker_turns']} wall={n['wall_ms']} ms",
              f"bridge state: {b['state']} turns={b['turns']} blockers={b['blocker_turns']} wall={b['wall_ms']} ms",
              f"native child observed: model={n.get('observed_child_model') or '?'} effort={n.get('observed_child_reasoning_effort') or '?'}",
              f"native parent/orchestrator usage (not included above): {json.dumps(n['orchestrator_usage'], sort_keys=True)}",
              f"scope violations: native={n['out_of_scope']} bridge={b['out_of_scope']}", "",
              "* uncached input = max(input_tokens - cached_input_tokens, 0).",
              "Token telemetry is not ChatGPT/Codex subscription usage units."]
    return "\n".join(lines)


def add_worktree(source: Path, target: Path, head: str) -> None:
    proc = run(["git", "-C", str(source), "worktree", "add", "--detach", str(target), head], timeout=120)
    if proc.returncode:
        raise BenchmarkError(proc.stderr.strip() or "git worktree add failed")


def remove_worktree(source: Path, target: Path) -> None:
    run(["git", "-C", str(source), "worktree", "remove", "--force", str(target)], timeout=120)


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B native Luna subagent vs persistent Codex CLI Luna executor")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--allowed-path", action="append", required=True)
    parser.add_argument("--required-step", action="append", default=[])
    parser.add_argument("--required-validation", action="append", default=[])
    parser.add_argument("--resolution", type=Path, action="append", default=[])
    parser.add_argument("--planner-model", default="gpt-5.6-sol")
    parser.add_argument("--planner-reasoning", default="high")
    parser.add_argument("--executor-model", default="gpt-5.6-luna")
    parser.add_argument("--executor-reasoning", default="low")
    parser.add_argument("--codex-command", default="codex")
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--order", choices=("native-first", "bridge-first"), default="native-first")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--keep-worktrees", action="store_true")
    args = parser.parse_args()

    source = args.repo.expanduser().resolve()
    top = Path(git(source, "rev-parse", "--show-toplevel")).resolve()
    if top != source:
        raise BenchmarkError(f"--repo must be Git worktree root: {top}")
    contract = args.contract.read_text(encoding="utf-8")
    if not contract.strip():
        raise BenchmarkError("empty execution contract")
    resolutions = [path.read_text(encoding="utf-8") for path in args.resolution]
    head = git(source, "rev-parse", "HEAD")
    bench_id = "ab_" + uuid.uuid4().hex[:12]
    tmp = Path(tempfile.mkdtemp(prefix=f"harr-{bench_id}-")); native_repo, bridge_repo = tmp / "native", tmp / "bridge"
    add_worktree(source, native_repo, head); add_worktree(source, bridge_repo, head)
    try:
        native_call = lambda: native_arm(args, native_repo, contract, resolutions, args.codex_home.expanduser().resolve())
        bridge_call = lambda: bridge_arm(args, bridge_repo, contract, resolutions, tmp / "bridge-state")
        if args.order == "native-first": native, bridge = native_call(), bridge_call()
        else: bridge, native = bridge_call(), native_call()
        report: dict[str, Any] = {
            "schema": 1, "benchmark_id": bench_id, "repo": str(source), "repo_head": head, "order": args.order,
            "contract": {"path": str(args.contract.resolve()), "bytes": len(contract.encode()), "chars": len(contract), "sha256": hashlib.sha256(contract.encode()).hexdigest()},
            "models": {"planner": args.planner_model, "planner_reasoning": args.planner_reasoning, "executor": args.executor_model, "executor_reasoning": args.executor_reasoning},
            "native": native, "bridge": bridge,
        }
        report["comparison"] = comparison(native, bridge)
        output = args.output.expanduser().resolve() if args.output else Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "harr" / "executor" / "benchmarks" / f"{bench_id}.json"
        output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(table(report)); print(f"\nreport: {output}")
        if args.keep_worktrees: print(f"native worktree: {native_repo}\nbridge worktree: {bridge_repo}")
        return 0
    finally:
        if not args.keep_worktrees:
            if native_repo.exists(): remove_worktree(source, native_repo)
            if bridge_repo.exists(): remove_worktree(source, bridge_repo)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BenchmarkError, OSError, subprocess.SubprocessError) as exc:
        print(f"A/B benchmark failed: {exc}", file=sys.stderr); raise SystemExit(2)
