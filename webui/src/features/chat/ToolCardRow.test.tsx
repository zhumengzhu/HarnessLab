import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ToolCardRow } from "./ToolCardRow";

describe("ToolCardRow", () => {
  const card = {
    tool: "web_search",
    ok: true,
    output_preview: "result body",
    duration_ms: 120,
  };

  it("renders static compact row when output is empty", () => {
    render(
      <ToolCardRow
        card={{ tool: "grep", ok: true, output_preview: "" }}
        displayMode="compact"
      />
    );
    expect(screen.getByText("grep · ok")).toBeTruthy();
    expect(screen.queryByText("result body")).toBeNull();
  });

  it("keeps compact tool output behind disclosure", () => {
    render(<ToolCardRow card={card} displayMode="compact" />);
    expect(screen.getByText("web_search · ok · 120ms")).toBeTruthy();
    expect(screen.getByText("result body")).toBeTruthy();
  });
});
