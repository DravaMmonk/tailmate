import assert from "node:assert/strict";
import test from "node:test";
import { parseSseEvents } from "./sse";

test("parseSseEvents handles CRLF-delimited SSE events across chunk boundaries", () => {
  const events = parseSseEvents([
    'event: query.started\r\ndata: {"event":"query.started","session_id":"session-1"}\r\n\r\n',
    'event: query.delta\r\ndata: {"event":"query.delta","session_id":"session-1","delta":"Hel',
    'lo"}\r\n\r\n',
    'event: query.completed\r\ndata: {"event":"query.completed","output":{"session_id":"session-1","response":"Hello","metadata":{},"error":null}}\r\n\r\n',
  ]);

  assert.deepEqual(events, [
    {
      name: "query.started",
      payload: {
        event: "query.started",
        session_id: "session-1",
      },
    },
    {
      name: "query.delta",
      payload: {
        event: "query.delta",
        session_id: "session-1",
        delta: "Hello",
      },
    },
    {
      name: "query.completed",
      payload: {
        event: "query.completed",
        output: {
          session_id: "session-1",
          response: "Hello",
          metadata: {},
          error: null,
        },
      },
    },
  ]);
});

test("parseSseEvents ignores comment frames and flushes the trailing payload", () => {
  const events = parseSseEvents([
    ": keep-alive\n",
    "event: query.delta\n",
    'data: {"event":"query.delta","delta":"Tail"}',
  ]);

  assert.deepEqual(events, [
    {
      name: "query.delta",
      payload: {
        event: "query.delta",
        delta: "Tail",
      },
    },
  ]);
});

test("parseSseEvents resets the event type after an event-only frame", () => {
  const events = parseSseEvents([
    "event: ping\n\n",
    'data: {"event":"message","delta":"Fresh"}\n\n',
  ]);

  assert.deepEqual(events, [
    {
      name: "message",
      payload: {
        event: "message",
        delta: "Fresh",
      },
    },
  ]);
});

test("parseSseEvents tolerates event frames separated by a single newline", () => {
  const events = parseSseEvents([
    'event: query.started\ndata: {"event":"query.started","session_id":"session-1"}\n',
    'event: query.delta\ndata: {"event":"query.delta","session_id":"session-1","delta":"Hello"}\n',
    'event: query.completed\ndata: {"event":"query.completed","session_id":"session-1","output":{"session_id":"session-1","response":"Hello","metadata":{},"error":null}}\n',
  ]);

  assert.deepEqual(events, [
    {
      name: "query.started",
      payload: {
        event: "query.started",
        session_id: "session-1",
      },
    },
    {
      name: "query.delta",
      payload: {
        event: "query.delta",
        session_id: "session-1",
        delta: "Hello",
      },
    },
    {
      name: "query.completed",
      payload: {
        event: "query.completed",
        session_id: "session-1",
        output: {
          session_id: "session-1",
          response: "Hello",
          metadata: {},
          error: null,
        },
      },
    },
  ]);
});

test("parseSseEvents keeps trailing non-chat events after query completion", () => {
  const events = parseSseEvents([
    'event: query.completed\ndata: {"event":"query.completed","session_id":"session-1","output":{"session_id":"session-1","response":"Hello","metadata":{},"error":null}}\n',
    'event: message\ndata: {"code":498,"message":"Context error","session_id":"session-1"}\n',
  ]);

  assert.deepEqual(events, [
    {
      name: "query.completed",
      payload: {
        event: "query.completed",
        session_id: "session-1",
        output: {
          session_id: "session-1",
          response: "Hello",
          metadata: {},
          error: null,
        },
      },
    },
    {
      name: "message",
      payload: {
        code: 498,
        message: "Context error",
        session_id: "session-1",
      },
    },
  ]);
});

test("parseSseEvents preserves event names when data arrives before event", () => {
  const events = parseSseEvents([
    'data: {"event":"query.delta","session_id":"session-1","delta":"Hello"}\n',
    "event: query.delta\n\n",
  ]);

  assert.deepEqual(events, [
    {
      name: "query.delta",
      payload: {
        event: "query.delta",
        session_id: "session-1",
        delta: "Hello",
      },
    },
  ]);
});
