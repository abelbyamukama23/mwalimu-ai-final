"use client";

import Image from "next/image";
import { cn } from "@/lib/utils";

export interface MwalimuLogoProps {
  size?: number;
  className?: string;
  priority?: boolean;
  alt?: string;
}

/**
 * Official Mwalimu brand icon / logo.
 * Renders the circular 4-pillar community / knowledge star mark.
 */
export function MwalimuLogo({
  size = 28,
  className,
  priority = false,
  alt = "Mwalimu",
}: MwalimuLogoProps) {
  return (
    <Image
      src="/logo.png"
      alt={alt}
      width={size}
      height={size}
      priority={priority}
      className={cn("shrink-0 select-none object-contain", className)}
      style={{ width: size, height: size }}
    />
  );
}

export default MwalimuLogo;
