"use client";

import { useEffect, useState, useTransition } from "react";
import type { DevicePreferences, DisplayDensity, ThemeMode, UiLanguage } from "./types";

const LOCAL_STORAGE_KEY = "mwalimu.device_preferences";
const PREFS_CHANGE_EVENT = "mwalimu:device_preferences_change";

const DEFAULT_PREFERENCES: DevicePreferences = {
  theme: "system",
  density: "comfortable",
  uiLanguage: "en",
  audioInputDeviceId: "default",
  autoPlayAudio: false,
  speechRate: 1.0,
};

function getStoredPreferences(): DevicePreferences {
  if (typeof window === "undefined") {
    return DEFAULT_PREFERENCES;
  }
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
    if (!raw) return DEFAULT_PREFERENCES;
    return { ...DEFAULT_PREFERENCES, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function applyTheme(theme: ThemeMode) {
  if (typeof window === "undefined") return;
  const root = document.documentElement;
  const isDark =
    theme === "dark" ||
    (theme === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);

  if (isDark) {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

export function useDevicePreferences() {
  const [prefs, setPrefs] = useState<DevicePreferences>(getStoredPreferences);
  const [, startTransition] = useTransition();

  useEffect(() => {
    // Sync theme on mount
    applyTheme(prefs.theme);

    const handleStorage = (e: StorageEvent) => {
      if (e.key === LOCAL_STORAGE_KEY && e.newValue) {
        try {
          const parsed = JSON.parse(e.newValue) as DevicePreferences;
          setPrefs(parsed);
          applyTheme(parsed.theme);
        } catch {
          // ignore parsing error
        }
      }
    };

    const handleCustomEvent = (e: Event) => {
      const customEvent = e as CustomEvent<DevicePreferences>;
      if (customEvent.detail) {
        setPrefs(customEvent.detail);
        applyTheme(customEvent.detail.theme);
      }
    };

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleMediaChange = () => {
      const currentPrefs = getStoredPreferences();
      if (currentPrefs.theme === "system") {
        applyTheme("system");
      }
    };

    window.addEventListener("storage", handleStorage);
    window.addEventListener(PREFS_CHANGE_EVENT, handleCustomEvent);
    mediaQuery.addEventListener("change", handleMediaChange);

    return () => {
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener(PREFS_CHANGE_EVENT, handleCustomEvent);
      mediaQuery.removeEventListener("change", handleMediaChange);
    };
  }, [prefs.theme]);

  const updatePreferences = (updates: Partial<DevicePreferences>) => {
    startTransition(() => {
      const next = { ...prefs, ...updates };
      setPrefs(next);
      applyTheme(next.theme);
      try {
        localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(next));
        window.dispatchEvent(
          new CustomEvent(PREFS_CHANGE_EVENT, { detail: next }),
        );
      } catch {
        // ignore localStorage quota errors
      }
    });
  };

  const setTheme = (theme: ThemeMode) => updatePreferences({ theme });
  const setDensity = (density: DisplayDensity) => updatePreferences({ density });
  const setUiLanguage = (uiLanguage: UiLanguage) => updatePreferences({ uiLanguage });

  return {
    preferences: prefs,
    updatePreferences,
    setTheme,
    setDensity,
    setUiLanguage,
  };
}
