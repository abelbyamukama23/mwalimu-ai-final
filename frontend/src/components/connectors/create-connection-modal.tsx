"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import {
  useConnectors,
  useCreateLibraryConnection,
} from "@/lib/hooks/use-connectors";
import type { Connector, SyncFrequency } from "@/lib/api/connectors";
import { DynamicSchemaFields } from "./dynamic-schema-fields";

type CreateConnectionModalProps = {
  libraryId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function CreateConnectionModal({
  libraryId,
  open,
  onOpenChange,
}: CreateConnectionModalProps) {
  const { data: connectors, isLoading: loadingConnectors } = useConnectors();
  const createMutation = useCreateLibraryConnection(libraryId);
  const toast = useToast();

  const [selectedConnectorId, setSelectedConnectorId] = useState<string>("");
  const [name, setName] = useState("");
  const [syncFrequency, setSyncFrequency] = useState<SyncFrequency>("manual");
  const [configValues, setConfigValues] = useState<Record<string, unknown>>({});
  const [credentialValues, setCredentialValues] = useState<
    Record<string, unknown>
  >({});
  const [formError, setFormError] = useState<string | null>(null);

  const activeConnectors = useMemo(() => {
    return (connectors ?? []).filter((c) => c.is_active);
  }, [connectors]);

  // Set default connector once loaded
  const selectedConnector: Connector | undefined = useMemo(() => {
    if (selectedConnectorId) {
      return activeConnectors.find((c) => c.id === selectedConnectorId);
    }
    return activeConnectors[0];
  }, [activeConnectors, selectedConnectorId]);

  const handleConfigChange = (key: string, value: unknown) => {
    setConfigValues((prev) => {
      const next = { ...prev };
      if (value === undefined || value === "") {
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
  };

  const handleCredentialChange = (key: string, value: unknown) => {
    setCredentialValues((prev) => {
      const next = { ...prev };
      if (value === undefined || value === "") {
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
  };

  const resetForm = () => {
    setName("");
    setConfigValues({});
    setCredentialValues({});
    setFormError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedConnector) {
      setFormError("Please select a connector.");
      return;
    }
    if (!name.trim()) {
      setFormError("Connection name is required.");
      return;
    }

    setFormError(null);

    try {
      await createMutation.mutateAsync({
        connector_id: selectedConnector.id,
        name: name.trim(),
        configuration:
          Object.keys(configValues).length > 0 ? configValues : undefined,
        credentials:
          Object.keys(credentialValues).length > 0
            ? credentialValues
            : undefined,
        sync_frequency: syncFrequency,
        status: "active",
      });

      toast("Connection created successfully");
      resetForm();
      onOpenChange(false);
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to create connection. Check configuration.";
      setFormError(message);
    } finally {
      // Clear sensitive memory immediately
      setCredentialValues({});
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) resetForm();
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader
          title="Add knowledge connection"
          description="Connect external data sources directly to this library."
        />

        {loadingConnectors ? (
          <div className="py-8 text-center text-13 text-ink-tertiary">
            Loading platform connectors…
          </div>
        ) : activeConnectors.length === 0 ? (
          <div className="py-6 text-center text-13 text-ink-secondary">
            No active platform connectors available.
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 pt-2">
            {formError && (
              <div className="rounded-md border border-danger/30 bg-danger-surface p-3 text-12 text-danger">
                {formError}
              </div>
            )}

            {/* Connector Selection */}
            <div className="space-y-1.5">
              <label className="text-12 font-medium text-ink">
                Connector Type
              </label>
              <select
                value={selectedConnector?.id ?? ""}
                onChange={(e) => {
                  setSelectedConnectorId(e.target.value);
                  setConfigValues({});
                  setCredentialValues({});
                }}
                className="focus-ring h-10 w-full rounded-md border border-border bg-surface px-3 text-13 text-ink"
              >
                {activeConnectors.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.connector_type})
                  </option>
                ))}
              </select>
              {selectedConnector?.description && (
                <p className="text-11 text-ink-tertiary">
                  {selectedConnector.description}
                </p>
              )}
            </div>

            {/* Connection Name */}
            <div className="space-y-1.5">
              <label className="text-12 font-medium text-ink">
                Connection Name <span className="text-danger">*</span>
              </label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Documentation Crawler"
                required
              />
            </div>

            {/* Sync Frequency */}
            <div className="space-y-1.5">
              <label className="text-12 font-medium text-ink">
                Sync Frequency
              </label>
              <select
                value={syncFrequency}
                onChange={(e) =>
                  setSyncFrequency(e.target.value as SyncFrequency)
                }
                className="focus-ring h-10 w-full rounded-md border border-border bg-surface px-3 text-13 text-ink"
              >
                <option value="manual">Manual</option>
                <option value="hourly">Hourly</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
            </div>

            {/* Configuration Schema */}
            <div className="border-t border-border pt-3">
              <h4 className="mb-2 text-13 font-semibold text-ink">
                Configuration
              </h4>
              <DynamicSchemaFields
                schema={selectedConnector?.config_schema}
                values={configValues}
                onChange={handleConfigChange}
              />
            </div>

            {/* Credentials Schema */}
            <div className="border-t border-border pt-3">
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-13 font-semibold text-ink">
                  Authentication & Credentials
                </h4>
                <span className="text-11 text-ink-tertiary">Write-only</span>
              </div>
              <p className="mb-3 text-11 text-ink-tertiary">
                Credentials are encrypted at rest on the platform API and never
                exposed after submission.
              </p>
              <DynamicSchemaFields
                schema={selectedConnector?.auth_schema}
                values={credentialValues}
                onChange={handleCredentialChange}
                isCredentialSection
              />
            </div>

            <div className="mt-6 flex justify-end gap-2.5 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  resetForm();
                  onOpenChange(false);
                }}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating…" : "Create Connection"}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
