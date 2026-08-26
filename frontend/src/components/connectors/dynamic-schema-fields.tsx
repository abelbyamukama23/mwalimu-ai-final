"use client";

import { Input } from "@/components/ui/input";
import type { JSONSchema, JSONSchemaProperty } from "@/lib/api/connectors";

type DynamicSchemaFieldsProps = {
  schema: JSONSchema | undefined;
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  isCredentialSection?: boolean;
};

export function DynamicSchemaFields({
  schema,
  values,
  onChange,
  isCredentialSection = false,
}: DynamicSchemaFieldsProps) {
  if (!schema || !schema.properties || Object.keys(schema.properties).length === 0) {
    return (
      <p className="text-12 text-ink-tertiary italic">
        {isCredentialSection
          ? "No authentication credentials required."
          : "No additional configuration required."}
      </p>
    );
  }

  const properties = schema.properties as Record<string, JSONSchemaProperty>;
  const requiredFields = new Set(schema.required ?? []);

  return (
    <div className="space-y-3.5">
      {Object.entries(properties).map(([key, prop]) => {
        const isRequired = requiredFields.has(key);
        const title = prop.title || formatPropertyTitle(key);
        const isSecret =
          isCredentialSection ||
          prop.writeOnly === true ||
          prop.format === "password" ||
          /key|secret|token|password/i.test(key);

        const currentValue = values[key] ?? prop.default ?? "";

        return (
          <div key={key} className="space-y-1.5">
            <label className="flex items-center justify-between text-12 font-medium text-ink">
              <span>
                {title}
                {isRequired && <span className="ml-1 text-danger">*</span>}
              </span>
              {prop.type && (
                <span className="text-10 text-ink-tertiary uppercase">
                  {prop.type}
                </span>
              )}
            </label>
            {prop.description && (
              <p className="text-11 text-ink-tertiary">{prop.description}</p>
            )}
            <Input
              type={
                isSecret
                  ? "password"
                  : prop.type === "integer" || prop.type === "number"
                    ? "number"
                    : "text"
              }
              value={String(currentValue)}
              onChange={(e) => {
                const val = e.target.value;
                if (prop.type === "integer") {
                  onChange(key, val === "" ? undefined : parseInt(val, 10));
                } else if (prop.type === "number") {
                  onChange(key, val === "" ? undefined : parseFloat(val));
                } else {
                  onChange(key, val);
                }
              }}
              placeholder={prop.description ? `e.g. ${title}` : undefined}
              min={prop.minimum}
              max={prop.maximum}
              minLength={prop.minLength}
              maxLength={prop.maxLength}
              autoComplete={isSecret ? "new-password" : "off"}
            />
          </div>
        );
      })}
    </div>
  );
}

function formatPropertyTitle(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
