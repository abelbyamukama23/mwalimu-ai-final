"use client";

import {
  useCallback,
  useEffect,
  useRef,
  type ClipboardEvent,
  type KeyboardEvent,
} from "react";
import { cn } from "@/lib/utils";

interface OtpInputProps {
  value: string;
  onChange: (value: string) => void;
  length?: number;
  disabled?: boolean;
  hasError?: boolean;
  autoFocus?: boolean;
  onComplete?: (code: string) => void;
}

export function OtpInput({
  value,
  onChange,
  length = 6,
  disabled = false,
  hasError = false,
  autoFocus = true,
  onComplete,
}: OtpInputProps) {
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Array of single-character digits from value
  const digits = Array.from({ length }, (_, i) => value[i] || "");

  useEffect(() => {
    if (autoFocus && inputRefs.current[0] && !disabled) {
      inputRefs.current[0].focus();
    }
  }, [autoFocus, disabled]);

  const handleInputChange = (index: number, digit: string) => {
    const cleanDigit = digit.replace(/\D/g, "").slice(-1);
    const newDigits = [...digits];
    newDigits[index] = cleanDigit;
    const nextValue = newDigits.join("");
    onChange(nextValue);

    if (cleanDigit && index < length - 1) {
      inputRefs.current[index + 1]?.focus();
    }

    if (nextValue.length === length && !nextValue.includes("")) {
      onComplete?.(nextValue);
    }
  };

  const handleKeyDown = (index: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace") {
      if (!digits[index] && index > 0) {
        // Current box is empty, jump back and clear previous
        const newDigits = [...digits];
        newDigits[index - 1] = "";
        onChange(newDigits.join(""));
        inputRefs.current[index - 1]?.focus();
      } else {
        const newDigits = [...digits];
        newDigits[index] = "";
        onChange(newDigits.join(""));
      }
    } else if (e.key === "ArrowLeft" && index > 0) {
      e.preventDefault();
      inputRefs.current[index - 1]?.focus();
    } else if (e.key === "ArrowRight" && index < length - 1) {
      e.preventDefault();
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handlePaste = useCallback(
    (e: ClipboardEvent<HTMLInputElement>) => {
      e.preventDefault();
      const pastedData = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, length);
      if (!pastedData) return;

      onChange(pastedData);

      const nextFocusIndex = Math.min(pastedData.length, length - 1);
      inputRefs.current[nextFocusIndex]?.focus();

      if (pastedData.length === length) {
        onComplete?.(pastedData);
      }
    },
    [length, onChange, onComplete],
  );

  return (
    <div className="flex items-center justify-between gap-2 sm:gap-2.5" role="group" aria-label="6-digit verification code">
      {Array.from({ length }).map((_, index) => (
        <input
          key={index}
          ref={(el) => {
            inputRefs.current[index] = el;
          }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          autoComplete={index === 0 ? "one-time-code" : "off"}
          value={digits[index] || ""}
          disabled={disabled}
          aria-label={`Digit ${index + 1} of ${length}`}
          onChange={(e) => handleInputChange(index, e.target.value)}
          onKeyDown={(e) => handleKeyDown(index, e)}
          onPaste={handlePaste}
          className={cn(
            "h-12 w-11 sm:h-13 sm:w-12 rounded-lg border text-center font-mono text-20 font-bold outline-none transition-all duration-150",
            "bg-surface text-ink focus:ring-2 focus:ring-accent/20",
            hasError
              ? "border-danger text-danger focus:border-danger focus:ring-danger/20"
              : "border-border focus:border-accent",
            disabled && "cursor-not-allowed bg-subtle opacity-60",
          )}
        />
      ))}
    </div>
  );
}
