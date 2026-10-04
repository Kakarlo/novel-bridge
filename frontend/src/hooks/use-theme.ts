import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "theme";

/** Read the theme the no-FOUC script in index.html already applied to <html>. */
function currentTheme(): Theme {
  if (typeof document === "undefined") return "light";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function hasExplicitChoice(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== null;
  } catch {
    return false;
  }
}

/**
 * Light/dark theme state. The initial value comes from the class the no-FOUC
 * script in index.html set (saved choice, else OS preference), so there's no
 * flash. `toggle()` persists an explicit choice to localStorage. While the user
 * hasn't made an explicit choice, we follow OS changes live.
 */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(currentTheme);

  const apply = useCallback((next: Theme) => {
    document.documentElement.classList.toggle("dark", next === "dark");
    setTheme(next);
  }, []);

  const toggle = useCallback(() => {
    const next: Theme = currentTheme() === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore persistence failures */
    }
    apply(next);
  }, [apply]);

  // Follow the OS preference until the user picks a theme explicitly.
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = (e: MediaQueryListEvent) => {
      if (!hasExplicitChoice()) apply(e.matches ? "dark" : "light");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [apply]);

  return { theme, toggle };
}
