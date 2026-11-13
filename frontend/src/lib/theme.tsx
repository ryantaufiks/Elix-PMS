"use client";

import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "elix.theme";
const TEXT_KEY = "elix.textSize";

/** Runs before first paint (inlined in <head>) so the page never flashes the wrong theme. */
export const themeBootScript = `try{var t=localStorage.getItem("${KEY}");if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t;if(localStorage.getItem("${TEXT_KEY}")==="large")document.documentElement.dataset.text="large"}catch(e){document.documentElement.dataset.theme="light"}`;

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  }, []);
  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try {
        localStorage.setItem(KEY, next);
      } catch {}
      return next;
    });
  }, []);
  return [theme, toggle];
}

/** "Larger text" (per browser): every size is in rem, so the whole dashboard grows with the root font size. */
export function useLargeText(): [boolean, () => void] {
  const [large, setLarge] = useState(false);
  useEffect(() => {
    setLarge(document.documentElement.dataset.text === "large");
  }, []);
  const toggle = useCallback(() => {
    setLarge((current) => {
      const next = !current;
      if (next) document.documentElement.dataset.text = "large";
      else delete document.documentElement.dataset.text;
      try {
        localStorage.setItem(TEXT_KEY, next ? "large" : "normal");
      } catch {}
      return next;
    });
  }, []);
  return [large, toggle];
}
