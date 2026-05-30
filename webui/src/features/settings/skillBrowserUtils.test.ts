import { describe, expect, it } from "vitest";
import type { SkillRecord } from "../../lib/schemas";
import {
  countSkillsByScope,
  filterSkillsByQuery,
  filterSkillsByScope,
  groupSkills,
} from "./skillBrowserUtils";

const rows: SkillRecord[] = [
  {
    name: "grep-helper",
    description: "Search workspace",
    tags: ["dev"],
    scope: "workspace",
    path: "/tmp/grep-helper.md",
  },
  {
    name: "notes",
    description: "User notes",
    tags: [],
    scope: "user",
    path: "/tmp/notes.md",
  },
  {
    name: "1password",
    description: "Catalog skill",
    tags: ["security"],
    scope: "catalog",
    path: null,
    catalog_id: "cat-1",
  },
];

describe("skillBrowserUtils", () => {
  it("filters by scope tab", () => {
    expect(filterSkillsByScope(rows, "installed")).toHaveLength(2);
    expect(filterSkillsByScope(rows, "catalog")).toHaveLength(1);
  });

  it("filters by query", () => {
    expect(filterSkillsByQuery(rows, "notes")).toHaveLength(1);
    expect(filterSkillsByQuery(rows, "security")).toHaveLength(1);
  });

  it("counts scopes for tabs", () => {
    expect(countSkillsByScope(rows)).toEqual({ all: 3, installed: 2, catalog: 1 });
  });

  it("groups skills by scope", () => {
    expect(groupSkills(rows).map((group) => group.id)).toEqual(["workspace", "user", "catalog"]);
  });
});
