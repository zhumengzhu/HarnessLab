import { createContext, createElement, useContext, useMemo, type ReactNode } from "react";
import { en, type Messages } from "./locales/en";
import { zh } from "./locales/zh";

export type Locale = "zh" | "en";

const LOCALES: Record<Locale, Messages> = { en, zh };

export type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  messages: Messages;
};

const I18nContext = createContext<I18nContextValue | null>(null);

function lookup(messages: Messages, key: string): string | undefined {
  const parts = key.split(".");
  let node: unknown = messages;
  for (const part of parts) {
    if (node == null || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`));
}

export function I18nProvider({
  locale,
  onLocaleChange,
  children,
}: {
  locale: Locale;
  onLocaleChange: (locale: Locale) => void;
  children: ReactNode;
}) {
  const value = useMemo((): I18nContextValue => {
    const messages = LOCALES[locale] ?? en;
    return {
      locale,
      setLocale: onLocaleChange,
      messages,
      t(key, vars) {
        const raw = lookup(messages, key) ?? lookup(en, key) ?? key;
        return interpolate(raw, vars);
      },
    };
  }, [locale, onLocaleChange]);

  return createElement(I18nContext.Provider, { value }, children);
}

export function translate(
  locale: Locale,
  key: string,
  vars?: Record<string, string | number>
): string {
  const messages = LOCALES[locale] ?? en;
  const raw = lookup(messages, key) ?? lookup(en, key) ?? key;
  return interpolate(raw, vars);
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return ctx;
}

export function formatMessageTime(iso: string, locale: Locale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}
