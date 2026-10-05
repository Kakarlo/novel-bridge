import { Cpu } from "lucide-react";

import { useModels } from "@/hooks/use-models";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/**
 * Model picker for the translate toolbar. Provider-aware by design (two-level provider →
 * model) even though only the local Ollama engine exists today — see FRONTEND_TODO #5a — so
 * adding cloud providers later is a data change, not a UI rewrite.
 *
 * READ-ONLY for now: the SSE translate body has no `model` field yet (BACKEND_TODO #2), so a
 * selection couldn't actually switch the model. Rather than offer a control that silently does
 * nothing, the picker is disabled and shows the configured default; it lists the available
 * models (grouped by provider) so the structure is visible and the switch is a one-line flip
 * once the backend body field lands.
 */
export function ModelPicker() {
  const { loading, providers, current } = useModels();

  // One provider today; the first is the local engine.
  const anyModels = providers.some((p) => p.models.length > 0);
  const unavailable = !loading && !anyModels;

  return (
    <div className="flex items-center gap-1.5">
      <Cpu className="size-4 text-muted-foreground" />
      {/* Read-only until the translate body carries a `model` field (BACKEND_TODO #2): the
          whole Select is disabled, so it shows `current` and can't be changed. value = the
          configured default; empty falls through to the placeholder below. */}
      <Select value={current} disabled>
        <SelectTrigger
          size="sm"
          className="w-[11rem]"
          title={
            unavailable
              ? "No models available — the engine is unreachable or not set up."
              : "Model switching per translation is coming soon. This shows the configured default model."
          }
        >
          <SelectValue placeholder={loading ? "Loading models…" : unavailable ? "Engine unavailable" : current} />
        </SelectTrigger>
        <SelectContent>
          {providers.map((p) => (
            <SelectGroup key={p.id}>
              <SelectLabel>{p.label}</SelectLabel>
              {p.models.length > 0 ? (
                p.models.map((m) => (
                  <SelectItem key={`${p.id}:${m}`} value={m}>
                    {m}
                  </SelectItem>
                ))
              ) : (
                <SelectItem value={`${p.id}:__none`} disabled>
                  {p.needs_key ? "Add an API key to use this provider" : "No models available"}
                </SelectItem>
              )}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
