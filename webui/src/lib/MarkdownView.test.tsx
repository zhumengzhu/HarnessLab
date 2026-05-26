import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownView } from "./MarkdownView";

describe("MarkdownView", () => {
  it("renders headings and lists", () => {
    render(<MarkdownView markdown={"## Title\n\n- one\n- two"} />);
    expect(screen.getByRole("heading", { level: 2, name: "Title" })).toBeTruthy();
    expect(screen.getByText("one")).toBeTruthy();
    expect(screen.getByText("two")).toBeTruthy();
  });

  it("renders fenced code blocks", () => {
    const { container } = render(<MarkdownView markdown={"```python\nprint('hi')\n```"} />);
    expect(container.querySelector(".md-code-block .hljs")).toBeTruthy();
    expect(container.textContent).toContain("print");
  });

  it("renders inline code", () => {
    render(<MarkdownView markdown={"Use `foo` here."} />);
    expect(screen.getByText("foo")).toBeTruthy();
  });
});
