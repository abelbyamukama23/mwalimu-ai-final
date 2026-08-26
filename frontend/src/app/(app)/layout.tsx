import { AuthGate } from "@/components/auth/auth-gate";
import { AppShell } from "@/components/layout/app-shell";
import { SettingsModalProvider } from "@/components/settings/settings-modal";

export default function AppGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <SettingsModalProvider>
        <AppShell>{children}</AppShell>
      </SettingsModalProvider>
    </AuthGate>
  );
}
