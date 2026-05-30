import type { SkillRecord } from "../../lib/schemas";

export type SkillScopeFilter = "all" | "installed" | "catalog";

export type SkillGroup = {
  id: string;
  labelKey: "workspace" | "user" | "catalog";
  skills: SkillRecord[];
};

const GROUP_ORDER: SkillGroup["labelKey"][] = ["workspace", "user", "catalog"];

export function filterSkillsByScope(
  skills: SkillRecord[],
  filter: SkillScopeFilter
): SkillRecord[] {
  if (filter === "all") return skills;
  if (filter === "installed") {
    return skills.filter((skill) => skill.scope === "workspace" || skill.scope === "user");
  }
  return skills.filter((skill) => skill.scope === "catalog");
}

export function filterSkillsByQuery(skills: SkillRecord[], query: string): SkillRecord[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return skills;
  return skills.filter((skill) => {
    const haystack = [skill.name, skill.description, skill.scope, ...skill.tags]
      .join(" ")
      .toLowerCase();
    return haystack.includes(needle);
  });
}

export function countSkillsByScope(skills: SkillRecord[]): Record<SkillScopeFilter, number> {
  const installed = skills.filter(
    (skill) => skill.scope === "workspace" || skill.scope === "user"
  ).length;
  return {
    all: skills.length,
    installed,
    catalog: skills.filter((skill) => skill.scope === "catalog").length,
  };
}

export function groupSkills(skills: SkillRecord[]): SkillGroup[] {
  const buckets = new Map<SkillGroup["labelKey"], SkillRecord[]>();
  for (const key of GROUP_ORDER) {
    buckets.set(key, []);
  }
  for (const skill of skills) {
    const key =
      skill.scope === "workspace" || skill.scope === "user" || skill.scope === "catalog"
        ? skill.scope
        : "catalog";
    buckets.get(key)?.push(skill);
  }
  return GROUP_ORDER.map((labelKey) => ({
    id: labelKey,
    labelKey,
    skills: buckets.get(labelKey) ?? [],
  })).filter((group) => group.skills.length > 0);
}
