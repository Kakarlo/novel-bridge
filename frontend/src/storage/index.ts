// Storage provider — the single swap point for the local-first migration.
//
// Every component/hook reads user-owned data through `getStorage()`, never the `api` client
// directly. Today it returns the REST-backed ApiStorageService (no behavior change); switching
// to IndexedDbStorage later is a one-line change here, with the UI untouched
// (design-local-first-storage.md, step 1 → 2).

import { ApiStorageService } from "./api-storage";
import type { StorageService } from "./types";

let instance: StorageService | null = null;

/** The active StorageService singleton. */
export function getStorage(): StorageService {
  if (!instance) {
    instance = new ApiStorageService();
  }
  return instance;
}

export type { ExportBundle, StorageService } from "./types";
