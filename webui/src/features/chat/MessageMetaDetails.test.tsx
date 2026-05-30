import { cleanup, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { I18nProvider } from "../../lib/i18n";
import { MessageMetaDetails } from "./MessageMetaDetails";
import type { ContextSnapshot } from "../../lib/schemas";

const snapshot: ContextSnapshot = {
  conversation_tokens: 32000,
  limit_tokens: 1048576,
  usage_ratio: 0.03,
  prompt_tokens_estimate: 776,
  context_breakdown_tokens: {
    conversation: 32000,
  },
};

function renderMeta(props: Partial<ComponentProps<typeof MessageMetaDetails>> = {}) {
  return render(
    <I18nProvider locale="en" onLocaleChange={() => {}}>
      <MessageMetaDetails snapshot={snapshot} modelLabel="deepseek-v4-flash" {...props} />
    </I18nProvider>
  );
}

describe("MessageMetaDetails", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders collapsible context summary without inline percent", () => {
    renderMeta();
    expect(screen.getByText("Context")).toBeTruthy();
    expect(screen.queryByText("3%")).toBeNull();
  });

  it("shows OpenClaw-style compact stats when expanded", () => {
    renderMeta();
    expect(screen.getByText(/↑776/)).toBeTruthy();
    expect(screen.getByText(/R1016\.6K/)).toBeTruthy();
    expect(screen.getByText("3% ctx")).toBeTruthy();
    expect(screen.getByText("deepseek-v4-flash")).toBeTruthy();
    expect(screen.queryByText("Conversation")).toBeNull();
    expect(screen.queryByText("3% Full")).toBeNull();
  });

  it("returns null without snapshot data", () => {
    const { container } = renderMeta({ snapshot: null });
    expect(container.firstChild).toBeNull();
  });
});
