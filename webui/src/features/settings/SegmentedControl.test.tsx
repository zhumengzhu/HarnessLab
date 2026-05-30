import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SegmentedControl } from "./SegmentedControl";

describe("SegmentedControl", () => {
  it("calls onChange when option clicked", () => {
    const onChange = vi.fn();
    render(
      <SegmentedControl
        ariaLabel="Theme"
        value="light"
        options={[
          { value: "system", label: "System" },
          { value: "light", label: "Light" },
          { value: "dark", label: "Dark" },
        ]}
        onChange={onChange}
      />
    );

    fireEventClick(screen.getByRole("button", { name: "Dark" }));
    expect(onChange).toHaveBeenCalledWith("dark");
  });

  it("marks active option with aria-pressed", () => {
    render(
      <SegmentedControl
        ariaLabel="Locale"
        value="zh"
        options={[
          { value: "zh", label: "中文" },
          { value: "en", label: "English" },
        ]}
        onChange={() => {}}
      />
    );

    expect(screen.getByRole("button", { name: "中文" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "English" }).getAttribute("aria-pressed")).toBe(
      "false"
    );
  });
});

function fireEventClick(element: HTMLElement) {
  element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}
