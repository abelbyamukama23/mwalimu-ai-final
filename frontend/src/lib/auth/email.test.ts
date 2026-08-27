import { describe, expect, it } from "vitest";
import { isValidEmail, normalizeEmail } from "@/lib/auth/email";

describe("isValidEmail", () => {
  it("accepts a well-formed address", () => {
    expect(isValidEmail("user@example.com")).toBe(true);
  });

  it("accepts an address with surrounding whitespace", () => {
    expect(isValidEmail("  user@example.com  ")).toBe(true);
  });

  it("normalizes before validating (case-insensitive domain ok)", () => {
    expect(isValidEmail("User@Example.COM")).toBe(true);
  });

  it("rejects missing @", () => {
    expect(isValidEmail("userexample.com")).toBe(false);
  });

  it("rejects empty and bare input", () => {
    expect(isValidEmail("")).toBe(false);
    expect(isValidEmail("   ")).toBe(false);
  });

  it("rejects a missing domain", () => {
    expect(isValidEmail("user@")).toBe(false);
  });
});

describe("normalizeEmail", () => {
  it("trims and lowercases", () => {
    expect(normalizeEmail("  User@Example.COM  ")).toBe("user@example.com");
  });

  it("returns empty for whitespace-only", () => {
    expect(normalizeEmail("   ")).toBe("");
  });
});
