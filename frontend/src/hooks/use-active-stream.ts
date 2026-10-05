import { useSyncExternalStore } from "react";

/**
 * A tiny app-wide flag for "a translation is currently streaming" (field-fix #1).
 *
 * The translate stream is a live HTTP connection with no server-side resume (see the
 * steering docs). The only in-app navigation that tears it down is switching projects
 * (switching tabs keeps the TranslateTab mounted, so the stream survives). This store lets
 * the TranslateTab publish its streaming state and lets App guard a project switch behind a
 * confirmation — without threading props through the tree.
 *
 * It is intentionally module-level and single-stream: only one translation runs at a time
 * (the backend concurrency cap defaults to 1, and the UI only drives one).
 */

let streaming = false;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

export function setStreaming(value: boolean) {
  if (streaming === value) return;
  streaming = value;
  emit();
}

export function isStreamingNow(): boolean {
  return streaming;
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** React hook: re-renders when the global streaming flag changes. */
export function useIsStreaming(): boolean {
  return useSyncExternalStore(subscribe, isStreamingNow, isStreamingNow);
}
