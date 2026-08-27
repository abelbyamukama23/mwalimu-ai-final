/**
 * TypeScript domain definitions for Mwalimu Settings & User Preferences.
 */

export type ThemeMode = "light" | "dark" | "system";
export type DisplayDensity = "comfortable" | "compact";
export type UiLanguage = "en" | "sw" | "fr";

export type DevicePreferences = {
  theme: ThemeMode;
  density: DisplayDensity;
  uiLanguage: UiLanguage;
  audioInputDeviceId: string;
  autoPlayAudio: boolean;
  speechRate: number; // 0.75 to 1.5
};

export type UserProfile = {
  id: string;
  display_name: string;
  avatar_url: string;
  phone_number: string;
  bio: string;
  created_at: string;
  updated_at: string;
};

export type PedagogicalStyle = "intuitive" | "formal" | "socratic";
export type ExplanationDepth = "concise" | "standard" | "in_depth";

export type UserPreferences = {
  id: string;
  pedagogical_style: PedagogicalStyle;
  explanation_depth: ExplanationDepth;
  response_language: string;
  cross_session_memory: boolean;
  created_at: string;
  updated_at: string;
};

export type GeographicUnit = {
  id: string;
  name: string;
  unit_type: string;
  country_code: string;
  slug?: string;
  parent?: {
    id: string;
    name: string;
    unit_type: string;
  } | null;
};

export type UserFamiliarRegion = {
  id: string;
  geographic_unit: GeographicUnit;
  priority: number;
  created_at: string;
  updated_at: string;
};
