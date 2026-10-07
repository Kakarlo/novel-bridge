import { useEffect } from "react";

/**
 * One shared `beforeunload` guard for the whole app.
 *
 * Several things want to warn before a refresh/close (a live translation stream, a
 * memory-only API key). Rather than each registering its own listener, callers flip a named
 * reason on/off here; a SINGLE listener is installed while any reason is active, so the
 * browser shows exactly one native "Leave site?" prompt. No reasons → no listener, no prompt.
 */

const reasons = new Set<string>();
let installed = false;

function onBeforeUnload(e: BeforeUnloadEvent) {
  e.preventDefault();
  e.returnValue = ""; // triggers the browser's native prompt
}

function sync() {
  const want = reasons.size > 0;
  if (want && !installed) {
    window.addEventListener("beforeunload", onBeforeUnload);
    installed = true;
  } else if (!want && installed) {
    window.removeEventListener("beforeunload", onBeforeUnload);
    installed = false;
  }
}

/** Warn on refresh/close while `active` is true, under a stable `reason` key. */
export function useUnloadWarning(reason: string, active: boolean) {
  useEffect(() => {
    if (!active) return;
    reasons.add(reason);
    sync();
    return () => {
      reasons.delete(reason);
      sync();
    };
  }, [reason, active]);
}
