"use client";

import { CheckCircle2, Globe } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useCurrentUser } from "@/lib/hooks/use-current-user";

const PROVIDERS = [
  {
    id: "google",
    name: "Google Account",
    description: "Used for Single Sign-On and personal Google Drive document imports.",
  },
  {
    id: "microsoft",
    name: "Microsoft / Office 365",
    description: "Used for OneDrive and school Microsoft 365 integrations.",
  },
  {
    id: "github",
    name: "GitHub",
    description: "Used for developer authentication and code repositories.",
  },
];

export function ConnectedAccountsSection() {
  const { data: user } = useCurrentUser();
  const toast = useToast();

  const handleConnect = (providerName: string) => {
    toast(`Connecting to ${providerName} OAuth flow…`);
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h2 className="text-22 font-semibold text-ink">Connected Accounts</h2>
        <p className="mt-1 text-13 text-ink-secondary">
          Link external identity providers and cloud services to your Mwalimu workspace.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-6 divide-y divide-border-subtle">
        {PROVIDERS.map((prov) => {
          // If email is gmail, represent Google as connected
          const isConnected =
            prov.id === "google" && user?.email?.endsWith("@gmail.com");

          return (
            <div
              key={prov.id}
              className="flex items-center justify-between py-4"
            >
              <div className="max-w-md space-y-1">
                <div className="flex items-center gap-2">
                  <Globe size={16} className="text-ink-tertiary" />
                  <span className="text-14 font-medium text-ink">
                    {prov.name}
                  </span>
                  {isConnected && (
                    <Badge tone="success">
                      <CheckCircle2 size={11} className="mr-1 inline" />
                      Connected
                    </Badge>
                  )}
                </div>
                <p className="text-12 text-ink-secondary leading-relaxed">
                  {prov.description}
                </p>
              </div>

              <div>
                {isConnected ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => toast("Account disconnection requires password setup.")}
                  >
                    Disconnect
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => handleConnect(prov.name)}
                  >
                    Connect
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
