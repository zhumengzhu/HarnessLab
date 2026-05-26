import { describe, expect, it } from "vitest";
import { isSlashPaletteOpen } from "./useComposerSlashMenu";

describe("isSlashPaletteOpen", () => {
  it("opens for bare slash prefix without spaces", () => {
    expect(isSlashPaletteOpen("/")).toBe(true);
    expect(isSlashPaletteOpen("/rem")).toBe(true);
    expect(isSlashPaletteOpen("/research")).toBe(true);
  });

  it("closes after command token ends", () => {
    expect(isSlashPaletteOpen("/remember note")).toBe(false);
  });
});
