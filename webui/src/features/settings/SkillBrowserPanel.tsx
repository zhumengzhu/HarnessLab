import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../lib/api-client";
import type { SkillPreviewResponse, SkillRecord, SkillsResponse } from "../../lib/schemas";

export function SkillBrowserPanel() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [installPath, setInstallPath] = useState("");
  const [installScope, setInstallScope] = useState<"workspace" | "user">("workspace");
  const [previewId, setPreviewId] = useState<string | null>(null);
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

  const previewQuery = useQuery({
    queryKey: ["skill-preview", previewId],
    enabled: previewId !== null,
    queryFn: () => {
      const [kind, id] = previewId!.split(":", 2);
      const param =
        kind === "catalog"
          ? `catalog_id=${encodeURIComponent(id)}`
          : `name=${encodeURIComponent(id)}`;
      return apiGet<SkillPreviewResponse>(`/api/skills/preview?${param}`);
    },
  });

  const rows = useMemo(() => skillsQuery.data?.skills ?? [], [skillsQuery.data?.skills]);

  async function installFromPath() {
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

  async function installFromCatalog(skill: SkillRecord) {
    if (!skill.catalog_id) {
      return;
    }
    setStatus(null);
    setError(null);
    try {
      const result = await apiPost<{ ok: boolean; path: string; scope: string }>(
        "/api/skills/install",
        { catalog_id: skill.catalog_id, scope: installScope }
      );
      setStatus(`Installed ${skill.name} to ${result.path} (${result.scope})`);
      await queryClient.invalidateQueries({ queryKey: ["skills"] });
      await queryClient.invalidateQueries({ queryKey: ["composer-commands"] });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function openPreview(skill: SkillRecord) {
    if (skill.scope === "catalog" && skill.catalog_id) {
      setPreviewId(`catalog:${skill.catalog_id}`);
      return;
    }
    setPreviewId(`name:${skill.name}`);
  }

  return (
    <section className="panel skills-panel">
      <div className="panel-title-row">
        <div>
          <h2>Skills</h2>
          <p className="settings-subtitle">
            浏览已安装与 catalog 技能；可从 bundled catalog 一键安装，或显式提供本地{" "}
            <code>.md</code> 路径。
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
        <select
          value={installScope}
          onChange={(e) => setInstallScope(e.target.value as "workspace" | "user")}
          aria-label="Install scope"
        >
          <option value="workspace">Install to workspace</option>
          <option value="user">Install to user</option>
        </select>
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
            <div className="skills-item-actions">
              <button type="button" onClick={() => openPreview(skill)}>
                Preview
              </button>
              {skill.scope === "catalog" && skill.catalog_id ? (
                <button type="button" onClick={() => void installFromCatalog(skill)}>
                  Install
                </button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>

      {previewId ? (
        <details className="settings-section" open>
          <summary>Markdown preview</summary>
          {previewQuery.isLoading ? <p>Loading preview…</p> : null}
          {previewQuery.error ? (
            <p className="error-text">{(previewQuery.error as Error).message}</p>
          ) : null}
          {previewQuery.data ? (
            <pre className="skills-preview">{previewQuery.data.markdown}</pre>
          ) : null}
        </details>
      ) : null}

      <details className="settings-section">
        <summary>Install skill (local file)</summary>
        <div className="skills-install">
          <input
            type="text"
            placeholder="/path/to/skill.md"
            value={installPath}
            onChange={(e) => setInstallPath(e.target.value)}
          />
          <button type="button" onClick={() => void installFromPath()} disabled={!installPath.trim()}>
            Install
          </button>
        </div>
        {status ? <p className="skills-status">{status}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
      </details>
    </section>
  );
}
