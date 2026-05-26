import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../../lib/api-client";
import type { ComposerCommandItem, ComposerCommandsResponse } from "../../lib/schemas";

export type SlashMenuItem = ComposerCommandItem & { group: "command" | "skill" };

function flattenCommands(data: ComposerCommandsResponse | undefined): SlashMenuItem[] {
  if (!data) return [];
  return [
    ...data.commands.map((item) => ({ ...item, group: "command" as const })),
    ...data.skills.map((item) => ({ ...item, group: "skill" as const })),
  ];
}

/** True while the user is typing a single-token slash command (`/foo`). */
export function isSlashPaletteOpen(composer: string): boolean {
  return /^\/[^\s]*$/.test(composer);
}

export function useComposerSlashMenu(composer: string) {
  const { data } = useQuery({
    queryKey: ["composer-commands"],
    queryFn: () => apiGet<ComposerCommandsResponse>("/api/composer/commands"),
    staleTime: 60_000,
  });
  const [activeIndex, setActiveIndex] = useState(0);

  const allItems = useMemo(() => flattenCommands(data), [data]);
  const open = isSlashPaletteOpen(composer);
  const query = open ? composer.slice(1).toLowerCase() : "";

  const items = useMemo(() => {
    if (!open) return [];
    const filtered = allItems.filter((item) => {
      const name = item.name.toLowerCase();
      const usage = item.usage.toLowerCase();
      return name.startsWith(query) || usage.startsWith(`/${query}`);
    });
    return filtered.slice(0, 12);
  }, [allItems, open, query]);

  const safeIndex = items.length === 0 ? 0 : Math.min(activeIndex, items.length - 1);

  function moveSelection(delta: number) {
    if (items.length === 0) return;
    setActiveIndex((idx) => {
      const next = idx + delta;
      if (next < 0) return items.length - 1;
      if (next >= items.length) return 0;
      return next;
    });
  }

  function resetSelection() {
    setActiveIndex(0);
  }

  return {
    open: open && items.length > 0,
    items,
    activeIndex: safeIndex,
    moveSelection,
    resetSelection,
    pickItem: (item: SlashMenuItem) => item.insert,
  };
}
