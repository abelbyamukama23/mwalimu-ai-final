"use client";

import {
  SiCanvas,
  SiDropbox,
  SiGithub,
  SiGoogle,
  SiGoogleclassroom,
  SiGoogledocs,
  SiGoogledrive,
  SiMoodle,
  SiNotion,
  SiZoom,
} from "react-icons/si";
import {
  AmazonIcon,
  Globe02Icon,
  HardDriveIcon,
  MicrosoftIcon,
  SlackIcon,
} from "hugeicons-react";
import type { ComponentType } from "react";
import { cn } from "@/lib/utils";

type BrandIconType =
  | "google_drive"
  | "google"
  | "google_docs"
  | "google_classroom"
  | "notion"
  | "github"
  | "microsoft"
  | "slack"
  | "dropbox"
  | "moodle"
  | "canvas"
  | "zoom"
  | "s3"
  | "amazon"
  | "file_system"
  | "web_crawler"
  | (string & {});

interface BrandIconProps {
  name: BrandIconType;
  size?: number;
  className?: string;
  colored?: boolean;
}

export function BrandIcon({
  name,
  size = 20,
  className,
  colored = true,
}: BrandIconProps) {
  const normalized = name.toLowerCase().replace(/[-_ ]/g, "_");

  // Multi-color SVG for Google Drive if colored is true
  if (normalized === "google_drive" || normalized === "googledrive") {
    if (colored) {
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 87.3 78"
          fill="none"
          className={cn("shrink-0", className)}
          aria-hidden="true"
        >
          <path d="M6.6 66.85l3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8H6.6c-4.4 0-7.3 4.4-4.8 8.2z" fill="#0066DA" />
          <path d="M43.65 25L29.9 1.2c-1.35.8-2.5 1.9-3.3 3.3L1.8 45.7c-2.2 3.8.7 8.6 5.1 8.6h27.5L43.65 25z" fill="#00AC47" />
          <path d="M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.8c2.2-3.8-.7-8.6-5.1-8.6H43.65l13.75 23.8c4.35 0 7.35-4.35 16.15-9.1z" fill="#EA4335" />
          <path d="M43.65 25L57.4 1.2C56.05.4 54.5 0 52.85 0H34.45c-1.65 0-3.2.4-4.55 1.2L43.65 25z" fill="#00832D" />
          <path d="M57.4 1.2L43.65 25l13.75 23.8h27.5c4.4 0 7.3-4.8 5.1-8.6L60.7 4.5c-.8-1.4-1.95-2.5-3.3-3.3z" fill="#FFBA00" />
          <path d="M73.55 76.8H27.5l-13.75-23.8h59.8l13.75 23.8c-.8.8-1.9 1.4-3.1 1.7-.2.2-.4.4-.6.6z" fill="#2684FC" />
        </svg>
      );
    }
    return <SiGoogledrive size={size} className={cn("text-[#4285F4] shrink-0", className)} />;
  }

  // Notion
  if (normalized === "notion") {
    return <SiNotion size={size} className={cn("text-ink shrink-0", className)} />;
  }

  // Google SSO / Ecosystem
  if (normalized === "google" || normalized === "google_account") {
    return <SiGoogle size={size} className={cn(colored ? "text-[#4285F4]" : "", "shrink-0", className)} />;
  }

  // Google Docs
  if (normalized === "google_docs" || normalized === "googledocs") {
    return <SiGoogledocs size={size} className={cn(colored ? "text-[#4285F4]" : "", "shrink-0", className)} />;
  }

  // Google Classroom
  if (normalized === "google_classroom" || normalized === "classroom") {
    return <SiGoogleclassroom size={size} className={cn(colored ? "text-[#0F9D58]" : "", "shrink-0", className)} />;
  }

  // GitHub
  if (normalized === "github") {
    return <SiGithub size={size} className={cn("text-ink shrink-0", className)} />;
  }

  // Microsoft / Office 365
  if (normalized === "microsoft" || normalized === "office" || normalized === "office365") {
    return <MicrosoftIcon size={size} className={cn(colored ? "text-[#00A4EF]" : "", "shrink-0", className)} />;
  }

  // Slack
  if (normalized === "slack") {
    return <SlackIcon size={size} className={cn(colored ? "text-[#4A154B] dark:text-[#E01E5A]" : "", "shrink-0", className)} />;
  }

  // Dropbox
  if (normalized === "dropbox") {
    return <SiDropbox size={size} className={cn(colored ? "text-[#0061FF]" : "", "shrink-0", className)} />;
  }

  // Moodle LMS
  if (normalized === "moodle") {
    return <SiMoodle size={size} className={cn(colored ? "text-[#F98012]" : "", "shrink-0", className)} />;
  }

  // Canvas LMS
  if (normalized === "canvas" || normalized === "canvas_lms") {
    return <SiCanvas size={size} className={cn(colored ? "text-[#E63F25]" : "", "shrink-0", className)} />;
  }

  // Zoom
  if (normalized === "zoom") {
    return <SiZoom size={size} className={cn(colored ? "text-[#0B5CFF]" : "", "shrink-0", className)} />;
  }

  // Amazon S3 / Cloud Object Storage
  if (normalized === "s3" || normalized === "amazon_s3" || normalized === "aws") {
    return <AmazonIcon size={size} className={cn(colored ? "text-[#FF9900]" : "", "shrink-0", className)} />;
  }

  // Local File System
  if (normalized === "file_system" || normalized === "local") {
    return <HardDriveIcon size={size} className={cn("text-accent shrink-0", className)} />;
  }

  // Web Crawler / Links
  if (normalized === "web_crawler" || normalized === "web") {
    return <Globe02Icon size={size} className={cn("text-brand shrink-0", className)} />;
  }

  // Fallback
  return <HardDriveIcon size={size} className={cn("text-ink-secondary shrink-0", className)} />;
}
