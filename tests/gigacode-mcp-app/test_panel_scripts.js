#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

async function runPanel(file, mode) {
  const html = fs.readFileSync(file, "utf8");
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script, `${file}: script block missing`);
  const listeners = new Map();
  const timers = new Set();
  let pagehidden = false;
  let callsAfterPagehide = 0;
  let nextTimer = 0;
  const setTimer = (callback, delay) => {
    const id = ++nextTimer;
    timers.add(id);
    const native = setTimeout(() => {
      timers.delete(id);
      callback();
    }, delay);
    idToNative.set(id, native);
    return id;
  };
  const idToNative = new Map();
  const clearTimer = (id) => {
    timers.delete(id);
    clearTimeout(idToNative.get(id));
  };
  const elements = new Map();
  const element = () => ({
    append() {},
    scrollHeight: 0,
    scrollTop: 0,
    textContent: "",
    innerHTML: "",
    className: "",
  });
  const document = {
    hidden: false,
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    createElement: element,
    addEventListener() {},
  };
  const window = { addEventListener: (name, callback) => listeners.set(name, callback) };
  const addWindowListener = window.addEventListener;
  window.addEventListener = (name, callback) => addWindowListener(name, (event) => {
    if (name === "pagehide") pagehidden = true;
    callback(event);
  });
  let claims = 0;
  let releases = 0;
  let messages = 0;
  const owners = [];
  const parent = {
    postMessage(message) {
      if (message.id === undefined) return;
      if (message.method === "ui/initialize") {
        queueMicrotask(() => listeners.get("message")({ data: { id: message.id, result: {} } }));
        return;
      }
      if (message.method !== "tools/call" && message.method !== "ui/message") return;
      if (pagehidden) callsAfterPagehide++;
      if (message.method === "ui/message") messages++;
      const tool = message.params?.name;
      if (tool === "claim_done_notification_ui") {
        claims++;
        owners.push(message.params.arguments.owner_token);
      } else if (tool === "release_done_notification_ui") releases++;
      if (mode === "teardown" && tool === "claim_done_notification_ui") return;
      const fail = tool === "claim_done_notification_ui" && (mode === "exhaust" || claims < 3);
      let result;
      if (tool === "claim_done_notification_ui") {
        result = { structuredContent: { claimed: true, status: "DONE", handoff: { status: "DONE", summary: "finished" } } };
      } else if (tool === "panel_event_ui") {
        result = { structuredContent: { ok: true } };
      } else {
        result = {};
      }
      queueMicrotask(() => listeners.get("message")({ data: fail
        ? { id: message.id, error: { code: -32000, message: "temporary failure" } }
        : { id: message.id, result } }));
    },
  };
  const context = vm.createContext({
    document, window, parent, setTimeout: setTimer, clearTimeout: clearTimer,
    console, Math, Date, String, Error, Promise, Map, JSON,
  });
  vm.runInContext(script + "\nwindow.__announce=()=>{sid='sid';scopeId='scope';if(typeof instance!=='undefined')instance='named';initialized=true;notifyEligible=true;return announceDone()};", context, { filename: file });
  await new Promise((resolve) => setImmediate(resolve));
  const announcement = context.window.__announce();
  if (mode === "teardown") {
    await new Promise((resolve) => setImmediate(resolve));
    listeners.get("pagehide")();
  }
  await announcement;
  assert.equal(claims, mode === "teardown" ? 1 : 3);
  assert.ok(owners.every((owner) => owner && owner === owners[0]), "retries must reuse one panel owner token");
  assert.equal(messages, mode === "success" ? 1 : 0);
  assert.equal(releases, mode === "exhaust" ? 1 : 0);
  assert.equal(timers.size, 0, "completed retries must leave no request or retry timers");
  assert.equal(callsAfterPagehide, 0, "pagehide must not create new app requests after teardown");
}

(async () => {
  for (const file of ["common/mcp/ein_app/panel.html"]) {
    const html = fs.readFileSync(file, "utf8");
    const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
    assert.ok(script, `${file}: script block missing`);
    new vm.Script(script, { filename: file });
    await runPanel(file, "success");
    await runPanel(file, "exhaust");
    await runPanel(file, "teardown");
  }
  console.log("MCP App panel retry/teardown contract: PASS");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
