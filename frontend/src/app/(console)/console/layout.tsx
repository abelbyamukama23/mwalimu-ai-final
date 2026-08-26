import type { Metadata } from "next";
import { InstitutionShell } from "@/components/console/institution-shell";

export const metadata: Metadata = { title: "Institution Console" };

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return <InstitutionShell>{children}</InstitutionShell>;
}
