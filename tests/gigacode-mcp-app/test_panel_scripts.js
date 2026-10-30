#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

async function runEinMonitorPanel(file) {
  const html = fs.readFileSync(file, "utf8");
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script, `${file}: script block missing`);
  const listeners = new Map();
  const timers = new Set();
  const nativeTimers = new Map();
  const elements = new Map();
  let nextTimer = 0;
  let pollCalls = 0;
  let uiMessages = 0;
  const calls = [];
  const setTimer = (callback, delay) => {
    const id = ++nextTimer;
    timers.add(id);
    nativeTimers.set(id, setTimeout(() => {
      timers.delete(id);
      callback();
    }, delay));
    return id;
  };
  const clearTimer = (id) => {
    timers.delete(id);
    clearTimeout(nativeTimers.get(id));
  };
  const element = () => ({
    children: [],
    append(child) { this.children.push(child); },
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
    addEventListener(name, callback) { listeners.set(`document:${name}`, callback); },
  };
  const window = { addEventListener: (name, callback) => listeners.set(name, callback) };
  const parent = {
    postMessage(message) {
      if (message.method === "ui/notifications/initialized" || message.id === undefined) return;
      if (message.method === "ui/initialize") {
        queueMicrotask(() => listeners.get("message")({ data: { id: message.id, result: {} } }));
        return;
      }
      if (message.method === "ui/message") uiMessages++;
      if (message.method !== "tools/call" && message.method !== "ui/message") return;
      const tool = message.params?.name;
      calls.push(tool);
      if (tool === "poll_ein_ui") pollCalls++;
      const structuredContent = tool === "poll_ein_ui"
        ? { status: "DONE", revision: 1, messages: [{ text: "verified monitor output" }] }
        : { ok: true };
      queueMicrotask(() => listeners.get("message")({
        data: { id: message.id, result: { structuredContent } },
      }));
    },
  };
  const context = vm.createContext({
    document, window, parent, setTimeout: setTimer, clearTimeout: clearTimer,
    console, Math, Date, String, Error, Promise, Map, JSON,
  });
  vm.runInContext(script, context, { filename: file });
  await new Promise((resolve) => setImmediate(resolve));
  listeners.get("message")({ data: {
    method: "ui/notifications/tool-input",
    params: { structuredContent: {
      instance: "review", session_id: "session-1", scope_id: "scope-1", initial_revision: 0,
    } },
  } });
  for (let attempt = 0; attempt < 20 && document.getElementById("status").textContent !== "DONE"; attempt++) {
    await new Promise((resolve) => setImmediate(resolve));
  }
  assert.equal(pollCalls, 1, "monitor panel polls the attached Ein session");
  assert.ok(calls.includes("panel_event_ui"), "monitor panel emits lifecycle diagnostics");
  assert.equal(uiMessages, 0, "monitor panel never sends a completion message");
  assert.ok(!calls.some((name) => String(name).includes("claim_done_notification_ui")), "completion claims belong to the inline marker");
  assert.equal(document.getElementById("status").textContent, "DONE");
  assert.ok(document.getElementById("lines").children.some((line) => line.innerHTML.includes("verified monitor output")));
  listeners.get("pagehide")();
  assert.equal(timers.size, 0, "completed monitor poll leaves no request timers");
}

(async () => {
  const file = "common/mcp/ein_app/panel.html";
  const html = fs.readFileSync(file, "utf8");
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script, `${file}: script block missing`);
  new vm.Script(script, { filename: file });
  await runEinMonitorPanel(file);
  console.log("Ein monitor-only panel lifecycle: PASS");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
