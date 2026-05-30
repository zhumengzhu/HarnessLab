import { describe, expect, it } from "vitest";
import { stepChatTextSize } from "./chatDisplay";

describe("chatDisplay", () => {
  it("steps chat text size within bounds", () => {
    expect(stepChatTextSize("md", -1)).toBe("sm");
    expect(stepChatTextSize("sm", -1)).toBe("sm");
    expect(stepChatTextSize("md", 1)).toBe("lg");
    expect(stepChatTextSize("lg", 1)).toBe("lg");
  });
});
