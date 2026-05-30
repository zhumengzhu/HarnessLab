import hljsDarkUrl from "highlight.js/styles/github-dark.min.css?url";
import hljsLightUrl from "highlight.js/styles/github.min.css?url";

export type ThemeFamily = "claw" | "classic";
export type ColorScheme = "light" | "dark";
export type ThemePreference = "system" | ColorScheme;
export type ResolvedUiTheme = `${ThemeFamily}-${ColorScheme}`;

/** @deprecated Legacy single-token themes; mapped to Claw on apply. */
export type LegacyUiTheme = "dark" | "light";

export type UiTheme = ResolvedUiTheme | LegacyUiTheme;

export const THEME_FAMILIES: ReadonlyArray<{
  id: ThemeFamily;
  labelKey: "settings.themeClaw" | "settings.themeClassic";
  hintKey: "settings.themeClawHint" | "settings.themeClassicHint";
  icon: string;
}> = [
  {
    id: "claw",
    labelKey: "settings.themeClaw",
    hintKey: "settings.themeClawHint",
    icon: "⚡",
  },
  {
    id: "classic",
    labelKey: "settings.themeClassic",
    hintKey: "settings.themeClassicHint",
    icon: "◆",
  },
];

export function resolveColorScheme(preference: ThemePreference): ColorScheme {
  if (preference !== "system") {
    return preference;
  }
  if (typeof window === "undefined" || !window.matchMedia) {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** @deprecated Use resolveUiTheme(family, preference) instead. */
export function resolveThemePreference(preference: ThemePreference): ColorScheme {
  return resolveColorScheme(preference);
}

export function resolveUiTheme(
  family: ThemeFamily,
  preference: ThemePreference
): ResolvedUiTheme {
  return `${family}-${resolveColorScheme(preference)}`;
}

const HLJS_LINK_ID = "hljs-theme";

const HLJS_BY_SCHEME: Record<ColorScheme, string> = {
  dark: hljsDarkUrl,
  light: hljsLightUrl,
};

function normalizeThemeId(theme: UiTheme): ResolvedUiTheme {
  if (theme === "dark") return "claw-dark";
  if (theme === "light") return "claw-light";
  return theme;
}

/** Apply theme tokens on `<html>` and swap syntax-highlight stylesheet. */
export function applyUiTheme(theme: UiTheme): void {
  const resolved = normalizeThemeId(theme);
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-hl-theme", resolved);
  }
  swapHljsTheme(resolved.endsWith("-light") ? "light" : "dark");
}

function swapHljsTheme(scheme: ColorScheme): void {
  if (typeof document === "undefined") {
    return;
  }
  const href = HLJS_BY_SCHEME[scheme];
  const existing = document.getElementById(HLJS_LINK_ID) as HTMLLinkElement | null;
  if (existing?.href.endsWith(href)) {
    return;
  }
  existing?.remove();

  const link = document.createElement("link");
  link.id = HLJS_LINK_ID;
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}
