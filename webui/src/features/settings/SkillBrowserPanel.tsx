import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../lib/api-client";
import type { SkillPreviewResponse, SkillRecord, SkillsResponse } from "../../lib/schemas";
import { MarkdownView } from "../../lib/MarkdownView";
import { useI18n } from "../../lib/i18n";
import { IconRefresh, IconSparkles } from "../shell/icons";
import {
  countSkillsByScope,
  filterSkillsByQuery,
  filterSkillsByScope,
  groupSkills,
  type SkillGroup,
  type SkillScopeFilter,
} from "./skillBrowserUtils";

const GROUP_LABEL_KEYS: Record<SkillGroup["labelKey"], "groupWorkspace" | "groupUser" | "groupCatalog"> = {
  workspace: "groupWorkspace",
  user: "groupUser",
  catalog: "groupCatalog",
};

export function SkillBrowserPanel() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");
  const [scopeFilter, setScopeFilter] = useState<SkillScopeFilter>("all");
  const [installPath, setInstallPath] = useState("");
  const [installScope, setInstallScope] = useState<"workspace" | "user">("workspace");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const skillsQuery = useQuery({
    queryKey: ["skills"],
    queryFn: () => apiGet<SkillsResponse>("/api/skills"),
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

  const allRows = useMemo(() => skillsQuery.data?.skills ?? [], [skillsQuery.data?.skills]);
  const scopeCounts = useMemo(() => countSkillsByScope(allRows), [allRows]);
  const filteredRows = useMemo(() => {
    const scoped = filterSkillsByScope(allRows, scopeFilter);
    return filterSkillsByQuery(scoped, filter);
  }, [allRows, filter, scopeFilter]);
  const groups = useMemo(() => groupSkills(filteredRows), [filteredRows]);

  const scopeTabs: { id: SkillScopeFilter; label: string }[] = [
    { id: "all", label: t("skills.tabAll") },
    { id: "installed", label: t("skills.tabInstalled") },
    { id: "catalog", label: t("skills.tabCatalog") },
  ];

  async function refreshSkills() {
    await queryClient.invalidateQueries({ queryKey: ["skills"] });
    await queryClient.invalidateQueries({ queryKey: ["composer-commands"] });
  }

  async function installFromPath() {
    setStatus(null);
    setError(null);
    try {
      const result = await apiPost<{ ok: boolean; path: string; scope: string }>(
        "/api/skills/install",
        { source: installPath.trim(), scope: installScope }
      );
      setStatus(t("skills.installedTo", { path: result.path, scope: result.scope }));
      setInstallPath("");
      await refreshSkills();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function installFromCatalog(skill: SkillRecord) {
    if (!skill.catalog_id) return;
    setStatus(null);
    setError(null);
    try {
      const result = await apiPost<{ ok: boolean; path: string; scope: string }>(
        "/api/skills/install",
        { catalog_id: skill.catalog_id, scope: installScope }
      );
      setStatus(t("skills.installedNamed", { name: skill.name, path: result.path }));
      await refreshSkills();
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

  function closePreview() {
    setPreviewId(null);
  }

  return (
    <section className="skills-page">
      <header className="skills-page-hero">
        <h1 className="skills-page-hero-title">{t("skills.pageTitle")}</h1>
        <p className="skills-page-hero-sub">{t("skills.pageSubtitle")}</p>
      </header>

      <div className="skills-card">
        <div className="skills-card-head">
          <div>
            <h2 className="skills-card-title">{t("skills.cardTitle")}</h2>
            <p className="skills-card-sub">{t("skills.cardSubtitle")}</p>
          </div>
          <button
            type="button"
            className="skills-refresh-btn"
            disabled={skillsQuery.isFetching}
            onClick={() => void refreshSkills()}
          >
            <IconRefresh size={14} />
            {skillsQuery.isFetching ? t("skills.refreshing") : t("skills.refresh")}
          </button>
        </div>

        <div className="skills-tabs" role="tablist" aria-label={t("skills.scopeTabs")}>
          {scopeTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={scopeFilter === tab.id}
              className={`skills-tab${scopeFilter === tab.id ? " skills-tab-active" : ""}`}
              onClick={() => setScopeFilter(tab.id)}
            >
              {tab.label}
              <span className="skills-tab-count">{scopeCounts[tab.id]}</span>
            </button>
          ))}
        </div>

        <div className="skills-filter-row">
          <input
            type="search"
            className="skills-filter-input"
            placeholder={t("skills.filterPlaceholder")}
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            autoComplete="off"
          />
          <span className="skills-filter-count">
            {t("skills.shownCount", { count: filteredRows.length })}
          </span>
        </div>

        {skillsQuery.isLoading ? <p className="skills-status-line">{t("skills.loading")}</p> : null}
        {skillsQuery.error ? (
          <p className="error-text">{t("skills.loadFailed", { error: (skillsQuery.error as Error).message })}</p>
        ) : null}

        {filteredRows.length === 0 && !skillsQuery.isLoading ? (
          <p className="skills-empty">{t("skills.empty")}</p>
        ) : (
          <div className="skills-groups">
            {groups.map((group) => (
              <details key={group.id} className="skills-group" open>
                <summary className="skills-group-header">
                  <span>{t(`skills.${GROUP_LABEL_KEYS[group.labelKey]}`)}</span>
                  <span className="skills-group-count">{group.skills.length}</span>
                </summary>
                <ul className="skills-grid">
                  {group.skills.map((skill) => (
                    <li key={`${skill.scope}:${skill.name}`} className="skills-row">
                      <div className="skills-row-icon" aria-hidden>
                        <IconSparkles size={16} />
                      </div>
                      <div className="skills-row-main">
                        <div className="skills-row-title">{skill.name}</div>
                        <div className="skills-row-desc">{skill.description}</div>
                        {skill.tags.length ? (
                          <div className="skills-row-tags">
                            {skill.tags.map((tag) => (
                              <span key={tag} className="skills-tag">
                                #{tag}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        <div className="skills-row-usage">
                          {t("skills.composerUsage", { name: skill.name })}
                        </div>
                      </div>
                      <div className="skills-row-actions">
                        <span className={`skills-scope-pill skills-scope-pill-${skill.scope}`}>
                          {skill.scope}
                        </span>
                        <button type="button" className="skills-action-btn" onClick={() => openPreview(skill)}>
                          {t("skills.preview")}
                        </button>
                        {skill.scope === "catalog" && skill.catalog_id ? (
                          <button
                            type="button"
                            className="skills-action-btn skills-action-btn-primary"
                            onClick={() => void installFromCatalog(skill)}
                          >
                            {t("skills.install")}
                          </button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
        )}

        <div className="skills-section-divider" />

        <div className="skills-install-section">
          <div className="skills-install-head">
            <h3 className="skills-install-title">{t("skills.installLocalTitle")}</h3>
            <p className="skills-install-sub">{t("skills.installLocalSub")}</p>
          </div>
          <div className="skills-install-row">
            <input
              type="text"
              className="skills-filter-input"
              placeholder={t("skills.installPathPlaceholder")}
              value={installPath}
              onChange={(event) => setInstallPath(event.target.value)}
            />
            <select
              className="skills-scope-select"
              value={installScope}
              onChange={(event) => setInstallScope(event.target.value as "workspace" | "user")}
              aria-label={t("skills.installScope")}
            >
              <option value="workspace">{t("skills.installScopeWorkspace")}</option>
              <option value="user">{t("skills.installScopeUser")}</option>
            </select>
            <button
              type="button"
              className="skills-action-btn skills-action-btn-primary"
              disabled={!installPath.trim()}
              onClick={() => void installFromPath()}
            >
              {t("skills.install")}
            </button>
          </div>
          {status ? <p className="skills-status-line skills-status-ok">{status}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </div>

      {previewId ? (
        <div className="skills-preview-dialog" role="dialog" aria-modal="true">
          <div className="skills-preview-panel">
            <div className="skills-preview-head">
              <h3>{t("skills.previewTitle")}</h3>
              <button type="button" className="skills-action-btn" onClick={closePreview}>
                {t("skills.close")}
              </button>
            </div>
            {previewQuery.isLoading ? <p className="skills-status-line">{t("skills.previewLoading")}</p> : null}
            {previewQuery.error ? (
              <p className="error-text">{(previewQuery.error as Error).message}</p>
            ) : null}
            {previewQuery.data ? (
              <MarkdownView markdown={previewQuery.data.markdown} className="skills-preview-body" />
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
