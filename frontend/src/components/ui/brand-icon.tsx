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
  GoogleDriveIcon,
  HardDriveIcon,
  MicrosoftIcon,
  SlackIcon,
} from "hugeicons-react";
import { cn } from "@/lib/utils";

type BrandIconType =
  | "google_drive"
  | "google_drive_simple"
  | "google_drive_huge"
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

  // Google Drive
  if (normalized === "google_drive_simple") {
    return <SiGoogledrive size={size} className={cn("text-[#4285F4] shrink-0", className)} />;
  }

  if (normalized === "google_drive_huge") {
    return <GoogleDriveIcon size={size} className={cn("text-ink shrink-0", className)} />;
  }

  if (normalized === "google_drive" || normalized === "googledrive") {
    if (colored) {
      // Crisp official Google Drive 3-color isometric triangle
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 512 443"
          fill="none"
          className={cn("shrink-0", className)}
          aria-hidden="true"
        >
          <path
            d="M170.667 0H341.333L512 296.296H341.333L170.667 0Z"
            fill="#FFBA00"
          />
          <path
            d="M0 296.296L85.3333 444.444H426.667L512 296.296H0Z"
            fill="#2684FC"
          />
          <path
            d="M0 296.296L170.667 0L256 148.148L85.3333 444.444L0 296.296Z"
            fill="#00AC47"
          />
        </svg>
      );
    }
    return <SiGoogledrive size={size} className={cn("text-[#4285F4] shrink-0", className)} />;
  }

  // Notion
  if (normalized === "notion") {
    return <SiNotion size={size} className={cn("text-ink shrink-0", className)} />;
  }

  // Google SSO / Ecosystem (Official standard 4-color Google G logo)
  if (normalized === "google" || normalized === "google_account" || normalized === "google_sso") {
    if (colored) {
      return (
        <svg
          width={size}
          height={size}
          viewBox="0 0 24 24"
          className={cn("shrink-0", className)}
          aria-hidden="true"
        >
          <path
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            fill="#4285F4"
          />
          <path
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            fill="#34A853"
          />
          <path
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
            fill="#FBBC05"
          />
          <path
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
            fill="#EA4335"
          />
        </svg>
      );
    }
    return <SiGoogle size={size} className={cn("text-ink shrink-0", className)} />;
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
