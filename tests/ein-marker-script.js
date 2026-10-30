#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("common/mcp/ein_marker.html", "utf8");
const script = source.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script, "marker script block missing");
new vm.Script(script, { filename: "common/mcp/ein_marker.html" });

async function createHarness({ messageFailures = 0, waitSnapshot, waitPending = false } = {}) {
  const listeners = new Map();
  const pendingTimers = new Map();
  const calls = [];
  const messages = [];
  let timerId = 0;
  const elements = new Map();
  const makeElement = () => ({
    style: {}, className: "", textContent: "",
    getBoundingClientRect: () => ({ height: 36 }),
  });
  const document = {
    hidden: false,
    body: { style: {} },
    getElementById(id) { if (!elements.has(id)) elements.set(id, makeElement()); return elements.get(id); },
    addEventListener() {},
  };
  const window = { addEventListener: (name, callback) => listeners.set(name, callback) };
  const answer = (message, result, error) => queueMicrotask(() => listeners.get("message")({
    data: error ? { id: message.id, error: { message: error } } : { id: message.id, result },
  }));
  const parent = {
    postMessage(message) {
      if (message.id === undefined) { messages.push(message); return; }
      if (message.method === undefined) { messages.push(message); return; }
      if (message.method === "ui/initialize") { answer(message, {}); return; }
      if (message.method === "ui/message") {
        messages.push(message);
        if (messageFailures > 0) { messageFailures--; answer(message, null, "simulated delivery failure"); }
        else answer(message, {});
        return;
      }
      assert.equal(message.method, "tools/call", message.method);
      const tool = message.params.name;
      const args = message.params.arguments;
      calls.push({ tool, args });
      if (tool === "ein_marker_wait_ui" && waitPending) return;
      if (tool === "ein_marker_wait_ui") { answer(message, { structuredContent: waitSnapshot(args) }); return; }
      if (tool === "ein_marker_claim_ui") {
        answer(message, { structuredContent: { claimed: true, status: "DONE", handoff: { status: "DONE", summary: "fixture" } } });
        return;
      }
      answer(message, { structuredContent: { ok: true } });
    },
  };
  const context = vm.createContext({
    document, window, parent, console, Math, Date, String, Error, Promise, Map, JSON,
    ResizeObserver: class { observe() {} },
    requestAnimationFrame: (callback) => queueMicrotask(callback),
    getComputedStyle: () => ({ paddingTop: "0", paddingBottom: "0" }),
    setTimeout: (callback, delay) => { const id = ++timerId; pendingTimers.set(id, { callback, delay }); return id; },
    clearTimeout: (id) => pendingTimers.delete(id),
  });
  vm.runInContext(
    `${script}\nwindow.__testDeliver=(snapshot)=>deliver(snapshot);`,
    context,
    { filename: "common/mcp/ein_marker.html" },
  );
  await flush();
  const dispatch = (data) => listeners.get("message")({ data });
  return { calls, messages, listeners, pendingTimers, document, window, dispatch };
}

async function flush() {
  for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
}

function toolStart(harness, action = "start", sessionId = "session-1", jobId = "job-00000001") {
  harness.dispatch({ method: "ui/notifications/tool-input", params: { arguments: { action } } });
  harness.dispatch({ method: "ui/notifications/tool-result", params: { result: { structuredContent: {
    session_id: sessionId, job_id: jobId, status: "RUNNING", summary: "running",
  } } } });
}

(async () => {
  let phase = "success scenario";
  const hardTimeout = setTimeout(() => {
    console.error(`Ein marker script timed out during ${phase}`);
    process.exit(1);
  }, 10000);
  const success = await createHarness({
    waitSnapshot: (args) => ({ session_id: args.session_id, job_id: args.job_id, terminal: true, status: "DONE", handoff: { status: "DONE", summary: "fixture" } }),
  });
  toolStart(success);
  await flush();
  assert.equal(success.calls.filter((call) => call.tool === "ein_marker_claim_ui").length, 1);
  assert.equal(success.messages.filter((message) => message.method === "ui/message").length, 1);
  const wait = success.calls.find((call) => call.tool === "ein_marker_wait_ui");
  assert.equal(wait.args.job_id, "job-00000001", "marker wait is bound to the exact launching job");
  const envelope = JSON.parse(success.messages.find((message) => message.method === "ui/message").params.content[0].text.split("\n").slice(1).join("\n"));
  assert.deepEqual(Object.keys(envelope).sort(), ["event", "handoff", "instance", "job_id", "session_id", "status"].sort());
  assert.equal(success.messages.find((message) => message.method === "ui/message").params.role, "user");
  assert.equal(envelope.event, "harr.ein.completed");
  assert.equal(envelope.job_id, "job-00000001");
  assert.equal(envelope.status, "DONE");
  assert.equal(envelope.handoff.summary, "fixture");
  await success.window.__testDeliver({ terminal: true, status: "DONE" });
  assert.equal(success.messages.filter((message) => message.method === "ui/message").length, 1, "one active marker emits at most one completion");

  phase = "failed delivery retry scenario";
  const retry = await createHarness({
    messageFailures: 1,
    waitSnapshot: (args) => ({ session_id: args.session_id, job_id: args.job_id, terminal: true, status: "DONE", handoff: { status: "DONE" } }),
  });
  toolStart(retry);
  await flush();
  assert.equal(retry.calls.filter((call) => call.tool === "ein_marker_release_ui").length, 1, "failed ui/message releases its claim");
  await retry.window.__testDeliver({ terminal: true, status: "DONE" });
  assert.equal(retry.calls.filter((call) => call.tool === "ein_marker_claim_ui").length, 2, "released completion can be claimed again");
  assert.equal(retry.calls.filter((call) => call.tool === "ein_marker_release_ui").length, 1);
  assert.equal(retry.messages.filter((message) => message.method === "ui/message").length, 2);

  phase = "stale job scenario";
  const stale = await createHarness({
    waitSnapshot: (args) => ({ session_id: args.session_id, job_id: "job-00000002", current_job_id: "job-00000002", terminal: false, replaced: true, status: "RUNNING" }),
  });
  toolStart(stale, "resume", "session-1", "job-00000001");
  await flush();
  assert.equal(stale.calls[0].args.job_id, "job-00000001");
  assert.equal(stale.calls.filter((call) => call.tool === "ein_marker_claim_ui").length, 0, "stale marker cannot claim newer job completion");
  assert.equal(stale.messages.filter((message) => message.method === "ui/message").length, 0);

  phase = "non-start action scenario";
  const nonAction = await createHarness({
    waitSnapshot: () => { throw new Error("non-start/resume action must not poll"); },
  });
  toolStart(nonAction, "status");
  await flush();
  assert.equal(nonAction.calls.length, 0);
  assert.equal(nonAction.messages.some((message) => message.method === "ui/notifications/request-teardown"), true);
  assert.equal(nonAction.document.body.style.display, "none");

  phase = "unmount scenario";
  const unmount = await createHarness({ waitPending: true });
  toolStart(unmount, "start");
  await flush();
  assert.equal(unmount.calls.some((call) => call.tool === "ein_marker_wait_ui"), true);
  unmount.dispatch({ id: 900, method: "ui/resource-teardown" });
  await flush();
  assert.equal(unmount.messages.some((message) => message.id === 900 && message.result), true, "resource teardown is acknowledged");
  assert.equal(unmount.messages.filter((message) => message.method === "ui/message").length, 0);

  clearTimeout(hardTimeout);
  console.log("Ein async marker JavaScript lifecycle: PASS");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
