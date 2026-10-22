import assert from "node:assert/strict";
import test from "node:test";
import { startSingleFlightPolling } from "../src/singleFlightPolling.ts";

test("slow polls and manual refresh share one request, then back off and clean up", async () => {
  let resolve!: (value: number) => void;
  let calls = 0;
  let time = 0;
  let timer: { callback: () => void; delay: number } | null = null;
  const values: number[] = [];
  const poller = startSingleFlightPolling({
    fetch: () => { calls += 1; return new Promise<number>(r => { resolve = r; }); },
    onValue: value => values.push(value), onError: () => {}, now: () => time,
    schedule: (callback, delay) => { timer = { callback, delay }; return timer; },
    cancel: () => { timer = null; },
  });
  await Promise.resolve();
  const first = poller.refresh();
  assert.equal(poller.refresh(), first);
  assert.equal(calls, 1);
  assert.equal(timer, null);
  time = 10_000;
  resolve(1); await first;
  assert.deepEqual(values, [1]);
  assert.equal((timer as unknown as { delay: number }).delay, 15_000);
  poller.stop(); assert.equal(timer, null);
});

test("failed polls back off, successful retries recover, late unmounted responses are ignored", async () => {
  let reject!: (error: Error) => void;
  let resolve!: (value: number) => void;
  let timer: { callback: () => void; delay: number } | null = null;
  const values: number[] = [];
  const errors: unknown[] = [];
  let fail = true;
  const poller = startSingleFlightPolling({ fetch: () => fail ? new Promise<number>((_, r) => { reject = r; })
    : new Promise<number>(r => { resolve = r; }),
    onValue: value => values.push(value), onError: error => errors.push(error), now: () => 0,
    schedule: (callback, delay) => { timer = { callback, delay }; return timer; }, cancel: () => { timer = null; },
  });
  await Promise.resolve();
  const first = poller.refresh(); reject(new Error("slow source"));
  await assert.rejects(first);
  assert.equal(errors.length, 1);
  assert.equal((timer as unknown as { delay: number }).delay, 5000);
  fail = false;
  const second = poller.refresh(); await Promise.resolve();
  resolve(2); await second;
  assert.deepEqual(values, [2]);
  assert.equal((timer as unknown as { delay: number }).delay, 2500);
  const last = poller.refresh(); await Promise.resolve();
  poller.stop(); resolve(3); await last;
  assert.deepEqual(values, [2]); assert.equal(timer, null);
});

test("idle cadence switches for active work and hidden tabs pause until one visible refresh", async () => {
  let visible = true;
  let changed = () => {};
  let unsubscribed = false;
  let calls = 0;
  let active = false;
  let timer: { callback: () => void; delay: number } | null = null;
  const poller = startSingleFlightPolling({
    fetch: async () => { calls++; return { active }; },
    intervalMs: value => value?.active ? 3000 : 30_000,
    isVisible: () => visible,
    subscribeVisibility: callback => { changed = callback; return () => { unsubscribed = true; }; },
    onValue: () => {}, onError: () => {}, now: () => 0,
    schedule: (callback, delay) => { timer = { callback, delay }; return timer; },
    cancel: () => { timer = null; },
  });
  await poller.refresh();
  assert.equal(calls, 1);
  assert.equal(timer!.delay, 30_000);
  active = true;
  await poller.refresh();
  assert.equal(timer!.delay, 3000);
  visible = false; changed();
  assert.equal(timer, null);
  const callsBefore = calls;
  visible = true; changed();
  await poller.refresh();
  assert.equal(calls, callsBefore + 1);
  assert.equal(timer!.delay, 3000);
  poller.stop();
  changed();
  assert.equal(calls, callsBefore + 1);
  assert.equal(timer, null);
  assert.ok(unsubscribed);
});

test("a request finishing after the tab hides schedules nothing; explicit reload still works", async () => {
  let visible = false;
  let changed = () => {};
  let calls = 0;
  let resolve!: (value: number) => void;
  let timers = 0;
  const poller = startSingleFlightPolling({
    fetch: () => { calls++; return new Promise<number>(r => { resolve = r; }); },
    isVisible: () => visible,
    subscribeVisibility: callback => { changed = callback; return () => {}; },
    onValue: () => {}, onError: () => {},
    schedule: () => { timers++; return timers; }, cancel: () => {},
  });
  await Promise.resolve(); assert.equal(calls, 0);
  visible = true; changed();
  const pending = poller.refresh(); await Promise.resolve();
  visible = false; changed(); resolve(1); await pending;
  assert.equal(timers, 0);
  const explicit = poller.refresh(); await Promise.resolve();
  resolve(2); await explicit;
  assert.equal(calls, 2); assert.equal(timers, 0);
  poller.stop();
});
