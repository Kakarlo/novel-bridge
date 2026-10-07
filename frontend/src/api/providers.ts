// Known LLM providers the picker can offer (bring-your-own-key).
//
// The backend's GET /api/models returns models for ONE provider at a time (the one named in
// the ?provider= query, or the server default). So the frontend keeps a small static catalog
// of selectable providers here; useModels fills in the live model list for the currently
// selected provider and leaves the others as known-but-unlisted entries. Adding a provider is
// a one-line change here plus the matching backend engine.

export interface ProviderInfo {
  id: string;
  label: string;
  /** A cloud provider that requires the user's API key before it can list/translate. */
  needsKey: boolean;
}

export const PROVIDERS: ProviderInfo[] = [
  { id: "ollama", label: "Local (Ollama)", needsKey: false },
  { id: "openrouter", label: "OpenRouter", needsKey: true },
  { id: "gemini", label: "Google Gemini", needsKey: true },
];

/** Default provider used when the user hasn't chosen one (matches the common server config). */
export const DEFAULT_PROVIDER_ID = "ollama";

export function getProvider(id: string): ProviderInfo | undefined {
  return PROVIDERS.find((p) => p.id === id);
}

export function providerNeedsKey(id: string): boolean {
  return getProvider(id)?.needsKey ?? false;
}
