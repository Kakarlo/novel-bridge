import { useEffect, useState } from "react";
import { Cpu, Eye, EyeOff, KeyRound } from "lucide-react";

import { DEFAULT_PROVIDER_ID, PROVIDERS, providerNeedsKey } from "@/api/providers";
import { useModels } from "@/hooks/use-models";
import { useCredentials, setCredentials, clearApiKey } from "@/hooks/use-credentials";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/**
 * Interactive provider + model + API-key picker for the translate toolbar (BYO-key).
 *
 * The toolbar shows a compact button with the active provider/model; clicking it opens a
 * dialog where the user picks a provider, pastes their API key (for cloud providers), and
 * chooses a model. All of it is backed by the credential store (use-credentials): the key is
 * session-only (never persisted to disk), the provider/model choice is remembered. Translate /
 * health / models all read the same store, so a change here takes effect immediately.
 */
export function ModelPicker() {
  const creds = useCredentials();
  const activeProviderId = creds.provider || DEFAULT_PROVIDER_ID;
  const { loading, providers, current } = useModels();

  const [open, setOpen] = useState(false);

  const activeModels = providers.find((p) => p.id === activeProviderId)?.models ?? [];
  const activeModelLabel = creds.model || current || "default";
  const activeProviderLabel = PROVIDERS.find((p) => p.id === activeProviderId)?.label ?? activeProviderId;

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        data-icon="inline-start"
        className="max-w-[16rem]"
        title="Choose the translation provider, model, and API key"
      >
        <Cpu className="size-4 text-muted-foreground" />
        <span className="truncate">
          {activeProviderLabel}
          <span className="text-muted-foreground"> · {loading ? "…" : activeModelLabel}</span>
        </span>
      </Button>

      <ProviderDialog
        open={open}
        onOpenChange={setOpen}
        activeProviderId={activeProviderId}
        activeModels={activeModels}
        apiKey={creds.apiKey}
        selectedModel={creds.model}
        serverDefaultModel={current}
      />
    </>
  );
}

interface ProviderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activeProviderId: string;
  activeModels: string[];
  apiKey: string;
  selectedModel: string;
  serverDefaultModel: string;
}

function ProviderDialog({
  open,
  onOpenChange,
  activeProviderId,
  activeModels,
  apiKey,
  selectedModel,
  serverDefaultModel,
}: ProviderDialogProps) {
  // Local draft of the key so typing doesn't re-probe on every keystroke; committed on blur /
  // "Use key". The provider/model selects commit immediately (cheap, no network per char).
  const [keyDraft, setKeyDraft] = useState(apiKey);
  const [showKey, setShowKey] = useState(false);

  // Keep the draft in sync if the dialog reopens with a different stored key.
  useEffect(() => {
    if (open) setKeyDraft(apiKey);
  }, [open, apiKey]);

  const needsKey = providerNeedsKey(activeProviderId);
  const hasKey = apiKey.trim().length > 0;

  function chooseProvider(id: string) {
    // Switching provider resets the model to that provider's default (empty = default).
    setCredentials({ provider: id, model: "" });
  }

  function chooseModel(model: string) {
    setCredentials({ model });
  }

  function commitKey() {
    const next = keyDraft.trim();
    if (next !== apiKey) setCredentials({ apiKey: next });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="size-4" />
            Translation model
          </DialogTitle>
          <DialogDescription>
            Choose a provider and model. Cloud providers need your own API key — it is kept only for this browser
            session and sent directly to the backend, never stored on a server.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-1">
          {/* Provider */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="provider-select">Provider</Label>
            <Select value={activeProviderId} onValueChange={chooseProvider}>
              <SelectTrigger id="provider-select" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROVIDERS.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.label}
                    {p.needsKey ? " (API key)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* API key — only for cloud providers */}
          {needsKey && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="api-key-input">API key</Label>
              <div className="flex items-center gap-1.5">
                <div className="relative flex-1">
                  <Input
                    id="api-key-input"
                    type={showKey ? "text" : "password"}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="Paste your API key"
                    value={keyDraft}
                    onChange={(e) => setKeyDraft(e.target.value)}
                    onBlur={commitKey}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitKey();
                    }}
                    className="pr-8"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((v) => !v)}
                    className="absolute inset-y-0 right-2 flex items-center text-muted-foreground hover:text-foreground"
                    aria-label={showKey ? "Hide API key" : "Show API key"}
                    tabIndex={-1}
                  >
                    {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
                <Button type="button" size="sm" variant="secondary" onClick={commitKey}>
                  Use key
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                {hasKey ? (
                  <span className="inline-flex items-center gap-2">
                    A key is set for this session.
                    <button
                      type="button"
                      onClick={() => {
                        clearApiKey();
                        setKeyDraft("");
                      }}
                      className="underline underline-offset-2 hover:text-foreground"
                    >
                      Forget key
                    </button>
                  </span>
                ) : (
                  "No key set — this provider can't translate until you add one."
                )}
              </p>
            </div>
          )}

          {/* Model */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="model-select">Model</Label>
            <Select value={selectedModel || ""} onValueChange={chooseModel} disabled={activeModels.length === 0}>
              <SelectTrigger id="model-select" className="w-full">
                <SelectValue
                  placeholder={
                    needsKey && !hasKey
                      ? "Add an API key to load models"
                      : activeModels.length === 0
                        ? "No models available"
                        : serverDefaultModel
                          ? `Default (${serverDefaultModel})`
                          : "Select a model"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {activeModels.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedModel && (
              <button
                type="button"
                onClick={() => setCredentials({ model: "" })}
                className="self-start text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Use provider default
              </button>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
