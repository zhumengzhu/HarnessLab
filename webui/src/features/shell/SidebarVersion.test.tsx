import { cleanup, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { I18nProvider } from "../../lib/i18n";
import { SidebarVersion } from "./SidebarVersion";

afterEach(() => {
  cleanup();
});

function renderVersion(overrides: Partial<ComponentProps<typeof SidebarVersion>> = {}) {
  const props: ComponentProps<typeof SidebarVersion> = {
    version: "0.1.0",
    healthOk: true,
    collapsed: false,
    ...overrides,
  };
  return render(
    <I18nProvider locale="en" onLocaleChange={() => {}}>
      <SidebarVersion {...props} />
    </I18nProvider>
  );
}

describe("SidebarVersion", () => {
  it("shows version label and number when expanded", () => {
    renderVersion();
    expect(screen.getByText("Version")).toBeTruthy();
    expect(screen.getByText("v0.1.0")).toBeTruthy();
  });

  it("shows only status dot when collapsed", () => {
    const { container } = renderVersion({ collapsed: true });
    expect(container.querySelector(".app-sidebar-version-text")).toBeNull();
    expect(container.querySelector(".app-sidebar-version-collapsed")).toBeTruthy();
    expect(screen.getByLabelText("health ok")).toBeTruthy();
  });
});
