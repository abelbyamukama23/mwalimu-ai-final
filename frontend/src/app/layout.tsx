import type { Metadata } from "next";
import { AuthModalProvider } from "@/components/auth/auth-modal";
import { AuthProvider } from "@/components/auth/auth-provider";
import { AppProviders } from "@/components/providers/app-providers";
import { ThemeController } from "@/components/theme/theme-controller";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Mwalimu", template: "%s · Mwalimu" },
  description:
    "Mwalimu — an AI learning workspace grounded in your libraries and local context.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full">
        <AppProviders>
          <AuthProvider>
            <AuthModalProvider>{children}</AuthModalProvider>
            <ThemeController />
          </AuthProvider>
        </AppProviders>
      </body>
    </html>
  );
}
