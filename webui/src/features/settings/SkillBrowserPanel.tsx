import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../lib/api-client";
import type { SkillRecord, SkillsResponse } from "../../lib/schemas";

export function SkillBrowserPanel() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [installPath, setInstallPath] = useState("");
  const [installScope, setInstallScope] = useState<"workspace" | "user">("workspace");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const skillsQuery = useQuery({
    queryKey: ["skills", query],
    queryFn: () =>
      apiGet<SkillsResponse>(
        query.trim()
          ? `/api/skills?q=${encodeURIComponent(query.trim())}`
          : "/api/skills"
      ),
  });

  const rows = useMemo(() => skillsQuery.data?.skills ?? [], [skillsQuery.data?.skills]);

  async function installSkill() {
    setStatus(null);
    setError(null);
    try {
      const result = await apiPost<{ ok: boolean; path: string; scope: string }>(
        "/api/skills/install",
        { source: installPath.trim(), scope: installScope }
      );
      setStatus(`Installed to ${result.path} (${result.scope})`);
      setInstallPath("");
      await queryClient.invalidateQueries({ queryKey: ["skills"] });
      await queryClient.invalidateQueries({ queryKey: ["composer-commands"] });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="panel skills-panel">
      <div className="panel-title-row">
        <div>
          <h2>Skills</h2>
          <p className="settings-subtitle">
            浏览 workspace / user 技能；安装需显式提供本地 <code>.md</code> 路径（无自动远程安装）。
          </p>
        </div>
      </div>

      <div className="skills-toolbar">
        <input
          type="search"
          placeholder="Search skills…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {skillsQuery.isLoading ? <p>Loading…</p> : null}
      {skillsQuery.error ? (
        <p className="error-text">Failed: {(skillsQuery.error as Error).message}</p>
      ) : null}

      <ul className="skills-list">
        {rows.map((skill: SkillRecord) => (
          <li key={`${skill.scope}:${skill.name}`} className="skills-item">
            <div className="skills-item-head">
              <strong>{skill.name}</strong>
              <span className="composer-slash-tag">{skill.scope}</span>
            </div>
            <p>{skill.description}</p>
            {skill.tags.length ? (
              <p className="skills-tags">{skill.tags.map((t) => `#${t}`).join(" ")}</p>
            ) : null}
            <p className="skills-usage">
              Composer: <code>/{skill.name} &lt;task&gt;</code>
            </p>
          </li>
        ))}
      </ul>

      <details className="settings-section">
        <summary>Install skill (local file)</summary>
        <div className="skills-install">
          <input
            type="text"
            placeholder="/path/to/skill.md"
            value={installPath}
            onChange={(e) => setInstallPath(e.target.value)}
          />
          <select
            value={installScope}
            onChange={(e) => setInstallScope(e.target.value as "workspace" | "user")}
          >
            <option value="workspace">workspace</option>
            <option value="user">user (~/.config/harnesslab/skills)</option>
          </select>
          <button type="button" onClick={() => void installSkill()} disabled={!installPath.trim()}>
            Install
          </button>
        </div>
        {status ? <p className="skills-status">{status}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
      </details>
    </section>
  );
}
