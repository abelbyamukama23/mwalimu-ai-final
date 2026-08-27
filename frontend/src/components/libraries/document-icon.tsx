"use client";

import {
  FileCode,
  FileCode2,
  FilePieChart,
  FileSpreadsheet,
  FileText,
  Globe,
  Image as ImageIcon,
  type LucideIcon,
} from "lucide-react";

export type DocumentTypeInfo = {
  label: string;
  ext: string;
  icon: LucideIcon;
  textColor: string;
  bgColor: string;
  borderColor: string;
};

export function getDocumentTypeInfo(filenameOrType: string): DocumentTypeInfo {
  const clean = filenameOrType.toLowerCase().trim();
  const ext = clean.includes(".") ? clean.split(".").pop() || "" : clean;

  switch (ext) {
    case "pdf":
      return {
        label: "PDF",
        ext: "pdf",
        icon: FileText,
        textColor: "text-red-600 dark:text-red-400",
        bgColor: "bg-red-500/10 dark:bg-red-500/15",
        borderColor: "border-red-500/25",
      };
    case "docx":
    case "doc":
      return {
        label: "Word",
        ext: "docx",
        icon: FileText,
        textColor: "text-blue-600 dark:text-blue-400",
        bgColor: "bg-blue-500/10 dark:bg-blue-500/15",
        borderColor: "border-blue-500/25",
      };
    case "xlsx":
    case "xls":
    case "csv":
      return {
        label: "Spreadsheet",
        ext: ext,
        icon: FileSpreadsheet,
        textColor: "text-emerald-600 dark:text-emerald-400",
        bgColor: "bg-emerald-500/10 dark:bg-emerald-500/15",
        borderColor: "border-emerald-500/25",
      };
    case "pptx":
    case "ppt":
      return {
        label: "Presentation",
        ext: ext,
        icon: FilePieChart,
        textColor: "text-amber-600 dark:text-amber-400",
        bgColor: "bg-amber-500/10 dark:bg-amber-500/15",
        borderColor: "border-amber-500/25",
      };
    case "md":
    case "markdown":
      return {
        label: "Markdown",
        ext: "md",
        icon: FileCode2,
        textColor: "text-purple-600 dark:text-purple-400",
        bgColor: "bg-purple-500/10 dark:bg-purple-500/15",
        borderColor: "border-purple-500/25",
      };
    case "png":
    case "jpg":
    case "jpeg":
    case "webp":
    case "svg":
      return {
        label: "Image / OCR",
        ext: ext,
        icon: ImageIcon,
        textColor: "text-rose-600 dark:text-rose-400",
        bgColor: "bg-rose-500/10 dark:bg-rose-500/15",
        borderColor: "border-rose-500/25",
      };
    case "link":
    case "url":
    case "html":
      return {
        label: "Web",
        ext: "link",
        icon: Globe,
        textColor: "text-cyan-600 dark:text-cyan-400",
        bgColor: "bg-cyan-500/10 dark:bg-cyan-500/15",
        borderColor: "border-cyan-500/25",
      };
    case "txt":
    case "text":
    default:
      return {
        label: "Text",
        ext: "txt",
        icon: FileCode,
        textColor: "text-teal-600 dark:text-teal-400",
        bgColor: "bg-teal-500/10 dark:bg-teal-500/15",
        borderColor: "border-teal-500/25",
      };
  }
}

export function DocumentIcon({
  filenameOrType,
  size = "md",
}: {
  filenameOrType: string;
  size?: "sm" | "md" | "lg";
}) {
  const info = getDocumentTypeInfo(filenameOrType);
  const Icon = info.icon;

  const sizeClasses = {
    sm: "h-8 w-8 rounded-md text-13",
    md: "h-10 w-10 rounded-lg text-16",
    lg: "h-12 w-12 rounded-xl text-20",
  };

  const iconSizes = {
    sm: 15,
    md: 20,
    lg: 24,
  };

  return (
    <div
      className={`flex shrink-0 items-center justify-center border font-semibold ${sizeClasses[size]} ${info.bgColor} ${info.borderColor} ${info.textColor}`}
      title={`${info.label} Document (${info.ext.toUpperCase()})`}
    >
      <Icon size={iconSizes[size]} aria-hidden />
    </div>
  );
}
