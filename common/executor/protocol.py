"""Worker contract and handoff validation shared by Einherjar backends.

This protocol is derived from the proven legacy GigaCode bridge. The legacy
`gigacode` MCP stays independent in this compatibility-first PR; Einherjar uses
this module as the backend-neutral contract for all current and future adapters.
"""

from __future__ import annotations

import json

WORKER_CONTRACT = r"""
You are an implementation worker. The caller is a more capable planner and owns
architecture, root-cause decisions, scope changes, and ambiguous design choices.

Your job is to execute an already-decided plan faithfully and cheaply.

Before editing:
1. Read the complete plan.
2. Read only enough repository code to validate the plan's important anchors,
   symbols, call paths, and assumptions.
3. If a material plan assumption does not match the code, STOP BEFORE EDITING
   and return ESCALATE. Do not redesign the solution yourself.

During implementation:
- Stay inside the plan's scope and design.
- Do not perform unrelated cleanup.
- Run the validation requested by the plan.
- Before DONE, perform your own final acceptance pass: map every acceptance
  criterion to a concrete verification result, inspect the final diff/scope for
  unrelated changes, and identify anything still unverified.
- Do not commit, push, or make external writes unless the plan explicitly says so.
- If an unexpected architectural contradiction appears after edits have begun,
  stop making further changes and return ESCALATE. Report every file already changed;
  do not silently revert or broaden the design.
- Ordinary local implementation mistakes that can be fixed without changing the
  plan are yours to fix; do not escalate trivial syntax/test errors.
- Use your normal execution capabilities. The bridge does not prescribe or
  depend on your internal tools, MCP servers, shell implementation, or editor.
- Keep long-running validation bounded. Do not enter sleep/poll loops, launch
  duplicate expensive work merely to wait, or repeatedly probe output just for
  progress. If validation cannot complete in this turn, preserve completed edits
  and return FAILED with the unfinished check and the evidence already gathered.

The final response MUST be exactly one JSON object and no Markdown fences or
surrounding prose. Use this schema:

{
  "status": "DONE" | "ESCALATE" | "FAILED",
  "summary": "short planner-facing summary",
  "changed": [
    {"path": "relative/path", "what": "specific change"}
  ],
  "verified": [
    {
      "criterion": "acceptance criterion id or short statement",
      "check": "command or invariant checked",
      "result": "PASS" | "FAIL",
      "evidence": "compact decisive evidence including exit/result when applicable"
    }
  ],
  "self_review": {
    "criteria_complete": true | false,
    "diff_scope_clean": true | false,
    "unverified": ["criterion or limitation still not proven"]
  },
  "escalation": null | {
    "kind": "plan_code_mismatch" | "ambiguous_design" | "scope_conflict" | "unexpected_architecture" | "validation_contradiction" | "other",
    "expected": "what the plan assumed or required",
    "observed": "what the repository actually contains or does",
    "evidence": [
      {
        "path": "relative/path",
        "symbol": "symbol/function/type or null",
        "lines": "line/range if known, else null",
        "fact": "precise code fact that proves the mismatch",
        "snippet": "minimal decisive code excerpt, preferably <= 8 lines, or null"
      }
    ],
    "impact": "why continuing would require changing the plan or architecture",
    "decision_needed": "one concrete decision/question the planner must resolve",
    "options": [
      {"option": "possible next direction", "consequence": "what choosing it changes"}
    ]
  },
  "blockers": [
    {"kind": "tool|build|test|environment|permission|other", "detail": "specific blocker", "evidence": "relevant compact output"}
  ]
}

Rules for the handoff:
- DONE: escalation must be null; blockers and self_review.unverified must be
  empty; every acceptance criterion must appear in verified with result=PASS;
  self_review.criteria_complete and self_review.diff_scope_clean must both be true.
- ESCALATE: provide enough evidence for the planner to reason without rereading
  the cited source just to understand the mismatch. Prefer exact symbols,
  paths, line ranges, and a tiny decisive snippet. State expected vs observed,
  impact, and the exact decision needed. Do not dump whole files.
- ESCALATE options must be neutral decision branches grounded in observed facts.
  Do NOT invent missing behavior, APIs, algorithms, data, target symbols, or
  implementation details. If a corrected design/target is unknown, say that the
  planner must provide it rather than proposing a plausible substitute.
- FAILED: use for execution/tool/environment failures that do not require an
  architectural decision. Include the failed command/check and compact evidence.
- For verification commands, include the exit/result outcome. Do not make the
  parent rerun a check merely to know whether it passed.
- Keep the whole JSON compact. Evidence should be sufficient, not exhaustive.
- Never claim a check passed unless you actually performed it.
""".strip()


def extract_json_object(output: str) -> dict | None:
    """Extract a JSON object even if the worker wrapped it in prose/fences."""
    stripped = output.strip()
    if not stripped:
        return None

    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    candidates: list[dict] = []
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped, index)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)

    if not candidates:
        return None

    required = {"status", "summary", "changed", "verified", "escalation", "blockers"}
    for candidate in reversed(candidates):
        if required.issubset(candidate):
            return candidate
    return candidates[-1]


def is_worker_handoff_text(text: str) -> bool:
    """Return True if *text* contains a valid worker handoff JSON object."""
    value = extract_json_object(text)
    return isinstance(value, dict) and value.get("status") in {"DONE", "ESCALATE", "FAILED"}


def parse_worker_handoff(
    output: str, exit_code: int, stderr: str
) -> tuple[dict, bool]:
    """Parse a worker handoff JSON object from *output*.

    Returns (parsed_dict, is_error).  The bool is True when the handoff is
    FAILED or the contract was violated.
    """
    if exit_code != 0:
        payload = {
            "status": "FAILED",
            "summary": "Worker process failed before producing a usable handoff.",
            "changed": [],
            "verified": [],
            "escalation": None,
            "blockers": [
                {
                    "kind": "tool",
                    "detail": f"process exited with code {exit_code}",
                    "evidence": (stderr or output)[-4000:],
                }
            ],
        }
        return payload, True

    handoff = extract_json_object(output)
    if handoff is None:
        payload = {
            "status": "FAILED",
            "summary": "Worker violated the handoff protocol.",
            "changed": [],
            "verified": [],
            "escalation": None,
            "blockers": [
                {
                    "kind": "other",
                    "detail": "worker returned no parseable JSON handoff",
                    "evidence": output[-4000:],
                }
            ],
        }
        return payload, True

    required = {"status", "summary", "changed", "verified", "escalation", "blockers"}
    missing = sorted(required - set(handoff))
    if missing or handoff.get("status") not in {"DONE", "ESCALATE", "FAILED"}:
        payload = {
            "status": "FAILED",
            "summary": "Worker returned an invalid handoff object.",
            "changed": [],
            "verified": [],
            "escalation": None,
            "blockers": [
                {
                    "kind": "other",
                    "detail": f"invalid handoff fields; missing={missing}",
                    "evidence": output[-4000:],
                }
            ],
        }
        return payload, True

    if handoff["status"] == "ESCALATE":
        escalation = handoff.get("escalation")
        escalation_required = {
            "kind",
            "expected",
            "observed",
            "evidence",
            "impact",
            "decision_needed",
            "options",
        }
        escalation_missing = (
            sorted(escalation_required - set(escalation))
            if isinstance(escalation, dict)
            else sorted(escalation_required)
        )
        evidence_ok = (
            isinstance(escalation, dict)
            and isinstance(escalation.get("evidence"), list)
            and len(escalation["evidence"]) > 0
        )
        decision_ok = (
            isinstance(escalation, dict)
            and isinstance(escalation.get("decision_needed"), str)
            and bool(escalation["decision_needed"].strip())
        )
        if escalation_missing or not evidence_ok or not decision_ok:
            payload = {
                "status": "FAILED",
                "summary": "Worker escalated without a complete planner-ready handoff.",
                "changed": (
                    handoff.get("changed")
                    if isinstance(handoff.get("changed"), list)
                    else []
                ),
                "verified": (
                    handoff.get("verified")
                    if isinstance(handoff.get("verified"), list)
                    else []
                ),
                "escalation": None,
                "blockers": [
                    {
                        "kind": "other",
                        "detail": (
                            "invalid ESCALATE handoff; "
                            f"missing={escalation_missing}, "
                            f"evidence_present={evidence_ok}, "
                            f"decision_present={decision_ok}"
                        ),
                        "evidence": output[-4000:],
                    }
                ],
            }
            return payload, True

    if handoff["status"] == "DONE":
        done_errors: list[str] = []
        if handoff.get("escalation") is not None:
            done_errors.append("escalation must be null")

        blockers = handoff.get("blockers")
        if blockers != []:
            done_errors.append("blockers must be empty")

        verified = handoff.get("verified")
        if not isinstance(verified, list) or not verified:
            done_errors.append("verified must be a non-empty list")
        else:
            for index, item in enumerate(verified):
                if not isinstance(item, dict):
                    done_errors.append(f"verified[{index}] must be an object")
                    continue
                if not isinstance(item.get("criterion"), str) or not item[
                    "criterion"
                ].strip():
                    done_errors.append(f"verified[{index}].criterion is required")
                if not isinstance(item.get("check"), str) or not item["check"].strip():
                    done_errors.append(f"verified[{index}].check is required")
                if item.get("result") != "PASS":
                    done_errors.append(f"verified[{index}].result must be PASS")
                if not isinstance(item.get("evidence"), str) or not item[
                    "evidence"
                ].strip():
                    done_errors.append(f"verified[{index}].evidence is required")

        self_review = handoff.get("self_review")
        if not isinstance(self_review, dict):
            done_errors.append("self_review is required")
        else:
            if self_review.get("criteria_complete") is not True:
                done_errors.append("self_review.criteria_complete must be true")
            if self_review.get("diff_scope_clean") is not True:
                done_errors.append("self_review.diff_scope_clean must be true")
            if self_review.get("unverified") != []:
                done_errors.append("self_review.unverified must be empty")

        if done_errors:
            payload = {
                "status": "FAILED",
                "summary": "Worker returned DONE without a complete self-verification handoff.",
                "changed": (
                    handoff.get("changed")
                    if isinstance(handoff.get("changed"), list)
                    else []
                ),
                "verified": verified if isinstance(verified, list) else [],
                "escalation": None,
                "blockers": [
                    {
                        "kind": "other",
                        "detail": "; ".join(done_errors),
                        "evidence": "Resume the same session and request the missing acceptance evidence/self-review.",
                    }
                ],
            }
            return payload, True

    return handoff, handoff["status"] == "FAILED"