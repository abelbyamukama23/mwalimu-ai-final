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
