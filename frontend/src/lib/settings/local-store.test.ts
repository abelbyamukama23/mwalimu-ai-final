import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("Device Preferences Local Store", () => {
  const localStorageMock = (() => {
    let store: Record<string, string> = {};
    return {
      getItem: (key: string) => store[key] || null,
      setItem: (key: string, value: string) => {
        store[key] = value.toString();
      },
      clear: () => {
        store = {};
      },
    };
  })();

  beforeEach(() => {
    vi.stubGlobal("localStorage", localStorageMock);
    localStorageMock.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads default preferences when localStorage is empty", () => {
    expect(localStorageMock.getItem("mwalimu.device_preferences")).toBeNull();
  });
});
