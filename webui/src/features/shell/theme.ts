import hljsDarkUrl from "highlight.js/styles/github-dark.min.css?url";
import hljsLightUrl from "highlight.js/styles/github.min.css?url";

export type UiTheme = "dark" | "light";

const HLJS_LINK_ID = "hljs-theme";

const HLJS_BY_THEME: Record<UiTheme, string> = {
  dark: hljsDarkUrl,
  light: hljsLightUrl,
};

/** Apply theme tokens on `<html>` and swap syntax-highlight stylesheet. */
export function applyUiTheme(theme: UiTheme): void {
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-hl-theme", theme);
  }
  swapHljsTheme(theme);
}

function swapHljsTheme(theme: UiTheme): void {
  if (typeof document === "undefined") {
    return;
  }
  const href = HLJS_BY_THEME[theme];
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
