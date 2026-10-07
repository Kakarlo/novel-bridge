// Storage provider — the single swap point for the local-first migration.
//
// Every component/hook reads user-owned data through `getStorage()`, never the `api` client
// directly. The backend (ApiStorageService) stays the default; the browser store
// (IndexedDbStorage) is opt-in behind a flag so step 2 can be verified for parity before it
// becomes the default (design-local-first-storage.md, step 2).
//
// Flag: localStorage `nb:storage` = "idb" selects the browser store, anything else (default)
// selects the API-backed store. Read once at startup — flip it, then reload.

import { ApiStorageService } from "./api-storage";
import { IndexedDbStorage } from "./idb-storage";
import type { StorageService } from "./types";

export type StorageBackend = "api" | "idb";
const BACKEND_KEY = "nb:storage";

// Build-time default, baked into the bundle at `vite build`. The HOSTED build sets
// `VITE_STORAGE_BACKEND=idb` so the browser store is the default and NO server DB is created
// from normal use. Self-host / local-dev builds leave it unset (or "api") to use the backend
// SQLite store. The localStorage flag below is a per-browser DEV override, never the hosted
// default — so a visitor can't accidentally fall back to the shared server DB.
const BUILD_DEFAULT: StorageBackend = import.meta.env.VITE_STORAGE_BACKEND === "idb" ? "idb" : "api";

export function getStorageBackend(): StorageBackend {
  try {
    const override = localStorage.getItem(BACKEND_KEY);
    if (override === "idb" || override === "api") return override;
  } catch {
    /* ignore unavailable storage */
  }
  return BUILD_DEFAULT;
}

/** Switch the active backend and reload so the new store takes over cleanly. */
export function setStorageBackend(backend: StorageBackend): void {
  try {
    localStorage.setItem(BACKEND_KEY, backend);
  } catch {
    /* best-effort */
  }
}

let instance: StorageService | null = null;

/** The active StorageService singleton. */
export function getStorage(): StorageService {
  if (!instance) {
    instance = getStorageBackend() === "idb" ? new IndexedDbStorage() : new ApiStorageService();
  }
  return instance;
}

export type { ExportBundle, StorageService } from "./types";
