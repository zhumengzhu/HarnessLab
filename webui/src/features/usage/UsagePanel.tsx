import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "../../lib/api-client";
import type { UsageDailyBucket, UsageResponse } from "../../lib/schemas";
import { useI18n } from "../../lib/i18n";
import { IconRefresh } from "../shell/icons";
import {
  activeUsageDimensions,
  dailyBarValue,
  formatCompactNumber,
  formatCost,
  formatShortDate,
  maxDailyBarValue,
  typeShare,
  type UsageDimensionKey,
} from "./usageUtils";

type UsageRange = "today" | "7d" | "30d" | "all";
type ChartView = "total" | "byType";

function dimensionLabel(key: UsageDimensionKey, t: (key: string) => string): string {
  const labels: Record<UsageDimensionKey, string> = {
    cache_read: t("usage.dimCacheRead"),
    cache_write: t("usage.dimCacheWrite"),
    cache_write_5m: t("usage.dimCacheWrite5m"),
    cache_write_1h: t("usage.dimCacheWrite1h"),
    reasoning: t("usage.dimReasoning"),
  };
  return labels[key];
}

function UsageDailyChart({
  daily,
  metric,
  chartView,
  emptyLabel,
  displayCurrency,
  currencySymbol,
}: {
  daily: UsageDailyBucket[];
  metric: "tokens" | "cost";
  chartView: ChartView;
  emptyLabel: string;
  displayCurrency?: string;
  currencySymbol?: string;
}) {
  const max = maxDailyBarValue(daily, metric, chartView);

  if (daily.length === 0) {
    return <p className="usage-status-line">{emptyLabel}</p>;
  }

  return (
    <div className="usage-daily-chart" aria-hidden={false}>
      {daily.map((day) => {
        const totalValue = dailyBarValue(day, metric, chartView);
        const heightPct = Math.max(4, (totalValue / max) * 100);
        const inputFrac =
          day.input_tokens + day.output_tokens > 0
            ? day.input_tokens / (day.input_tokens + day.output_tokens)
            : 1;
        const inputHeight = chartView === "byType" ? heightPct * inputFrac : heightPct;
        const outputHeight = chartView === "byType" ? heightPct - inputHeight : 0;

        return (
          <div key={day.date} className="usage-daily-col">
            <div className="usage-daily-bar-wrap">
              {chartView === "byType" ? (
                <>
                  {outputHeight > 0 ? (
                    <div
                      className="usage-daily-seg usage-daily-seg-out"
                      style={{ height: `${outputHeight}%` }}
                    />
                  ) : null}
                  <div
                    className="usage-daily-seg usage-daily-seg-in"
                    style={{ height: `${inputHeight}%` }}
                  />
                </>
              ) : (
                <div className="usage-daily-seg usage-daily-seg-total" style={{ height: `${heightPct}%` }} />
              )}
            </div>
            <span className="usage-daily-date">{formatShortDate(day.date)}</span>
            <span className="usage-daily-value">
              {metric === "cost"
                ? formatCost(
                    day.cost_usd,
                    day.cost_display,
                    currencySymbol,
                    displayCurrency
                  )
                : formatCompactNumber(day.total_tokens)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function UsagePanel() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [range, setRange] = useState<UsageRange>("all");
  const [metric, setMetric] = useState<"tokens" | "cost">("tokens");
  const [chartView, setChartView] = useState<ChartView>("byType");

  const usageQuery = useQuery({
    queryKey: ["usage", range],
    queryFn: () => apiGet<UsageResponse>(`/api/usage?range=${range}`),
  });

  const usage = usageQuery.data;
  const totals = usage?.totals;
  const daily = usage?.daily ?? [];
  const byModel = usage?.by_model ?? [];
  const sessions = usage?.sessions ?? [];

  const inputShare = useMemo(
    () => (totals ? typeShare(totals, "input_tokens") : 0),
    [totals]
  );
  const outputShare = useMemo(
    () => (totals ? typeShare(totals, "output_tokens") : 0),
    [totals]
  );
  const billingDimensions = useMemo(
    () => activeUsageDimensions(totals?.dimensions),
    [totals]
  );
  const formatUsageCost = (costUsd: number, costDisplay?: number | null) =>
    formatCost(costUsd, costDisplay, usage?.currency_symbol, usage?.display_currency);

  const rangeTabs: { id: UsageRange; label: string }[] = [
    { id: "today", label: t("usage.rangeToday") },
    { id: "7d", label: t("usage.range7d") },
    { id: "30d", label: t("usage.range30d") },
    { id: "all", label: t("usage.rangeAll") },
  ];

  return (
    <section className="usage-page">
      <header className="usage-page-hero">
        <h1 className="usage-page-hero-title">{t("usage.pageTitle")}</h1>
        <p className="usage-page-hero-sub">{t("usage.pageSubtitle")}</p>
      </header>

      <div className="usage-card">
        <div className="usage-card-head">
          <div>
            <h2 className="usage-card-title">{t("usage.cardTitle")}</h2>
            <p className="usage-card-sub">{t("usage.cardSubtitle")}</p>
          </div>
          {totals ? (
            <div className="usage-head-stats">
              <span>{formatCompactNumber(totals.total_tokens)} Token</span>
              <span>
                ↑{formatCompactNumber(totals.input_tokens)} ↓{formatCompactNumber(totals.output_tokens)}
              </span>
              <span>{formatUsageCost(totals.cost_usd, totals.cost_display)} {t("usage.cost")}</span>
            </div>
          ) : null}
        </div>

        <div className="usage-toolbar">
          <div className="usage-range-tabs" role="tablist" aria-label={t("usage.rangeTabs")}>
            {rangeTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={range === tab.id}
                className={`usage-range-tab${range === tab.id ? " usage-range-tab-active" : ""}`}
                onClick={() => setRange(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="usage-metric-toggle" role="group" aria-label={t("usage.metricToggle")}>
            <button
              type="button"
              className={`usage-metric-btn${metric === "tokens" ? " usage-metric-btn-active" : ""}`}
              onClick={() => setMetric("tokens")}
            >
              Token
            </button>
            <button
              type="button"
              className={`usage-metric-btn${metric === "cost" ? " usage-metric-btn-active" : ""}`}
              onClick={() => setMetric("cost")}
            >
              {t("usage.cost")}
            </button>
          </div>

          <button
            type="button"
            className="usage-refresh-btn"
            disabled={usageQuery.isFetching}
            onClick={() => void queryClient.invalidateQueries({ queryKey: ["usage"] })}
          >
            <IconRefresh size={14} />
            {usageQuery.isFetching ? t("usage.refreshing") : t("usage.refresh")}
          </button>
        </div>

        {usageQuery.error ? (
          <p className="error-text">
            {t("usage.loadFailed", { error: (usageQuery.error as Error).message })}
          </p>
        ) : null}

        {usage?.source === "sessions" ? (
          <div className="usage-notice" role="status">
            {t("usage.sourceSessionsHint")}
          </div>
        ) : null}

        {totals ? (
          <div className="usage-overview-grid">
            <div className="usage-stat-card">
              <span className="usage-stat-label">{t("usage.statInput")}</span>
              <strong className="usage-stat-value">{formatCompactNumber(totals.input_tokens)}</strong>
            </div>
            <div className="usage-stat-card">
              <span className="usage-stat-label">{t("usage.statOutput")}</span>
              <strong className="usage-stat-value">{formatCompactNumber(totals.output_tokens)}</strong>
            </div>
            <div className="usage-stat-card">
              <span className="usage-stat-label">{t("usage.statTokens")}</span>
              <strong className="usage-stat-value">{formatCompactNumber(totals.total_tokens)}</strong>
            </div>
            <div className="usage-stat-card">
              <span className="usage-stat-label">{t("usage.statCost")}</span>
              <strong className="usage-stat-value">
                {formatUsageCost(totals.cost_usd, totals.cost_display)}
              </strong>
            </div>
          </div>
        ) : null}

        <div className="usage-chart-section">
          <div className="usage-section-head">
            <h3>{t("usage.dailyChartTitle")}</h3>
            <div className="usage-chart-view-toggle" role="group" aria-label={t("usage.chartView")}>
              <button
                type="button"
                className={`usage-chart-view-btn${chartView === "total" ? " active" : ""}`}
                onClick={() => setChartView("total")}
              >
                {t("usage.chartTotal")}
              </button>
              <button
                type="button"
                className={`usage-chart-view-btn${chartView === "byType" ? " active" : ""}`}
                onClick={() => setChartView("byType")}
              >
                {t("usage.chartByType")}
              </button>
            </div>
          </div>

          {usageQuery.isLoading ? (
            <p className="usage-status-line">{t("usage.loading")}</p>
          ) : (
            <UsageDailyChart
              daily={daily}
              metric={metric}
              chartView={chartView}
              emptyLabel={t("usage.noDailyData")}
              displayCurrency={usage?.display_currency}
              currencySymbol={usage?.currency_symbol}
            />
          )}

          {totals && totals.input_tokens + totals.output_tokens > 0 ? (
            <div className="usage-type-breakdown">
              <div className="usage-section-head">
                <h3>{t("usage.typeBreakdownTitle")}</h3>
                <span className="usage-filter-count">
                  {t("usage.typeTotal", { value: formatCompactNumber(totals.total_tokens) })}
                </span>
              </div>
              <div className="usage-type-bar" aria-hidden>
                <span
                  className="usage-type-seg usage-type-seg-in"
                  style={{ width: `${inputShare * 100}%` }}
                />
                <span
                  className="usage-type-seg usage-type-seg-out"
                  style={{ width: `${outputShare * 100}%` }}
                />
              </div>
              <ul className="usage-type-legend">
                <li>
                  <span className="usage-type-dot usage-type-dot-in" />
                  {t("usage.tokenInput")} {formatCompactNumber(totals.input_tokens)}
                </li>
                <li>
                  <span className="usage-type-dot usage-type-dot-out" />
                  {t("usage.tokenOutput")} {formatCompactNumber(totals.output_tokens)}
                </li>
              </ul>
            </div>
          ) : null}

          {billingDimensions.length > 0 ? (
            <div className="usage-dimension-breakdown">
              <div className="usage-section-head">
                <h3>{t("usage.dimensionBreakdownTitle")}</h3>
              </div>
              <ul className="usage-type-legend">
                {billingDimensions.map(({ key, value }) => (
                  <li key={key}>
                    <span className={`usage-type-dot usage-type-dot-${key.replace(/_/g, "-")}`} />
                    {dimensionLabel(key, t)} {formatCompactNumber(value)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        <div className="usage-section-head">
          <h3>{t("usage.modelTableTitle")}</h3>
          <span className="usage-filter-count">{t("usage.shownCount", { count: byModel.length })}</span>
        </div>

        {byModel.length === 0 ? (
          <p className="usage-status-line">{t("usage.noModelData")}</p>
        ) : (
          <div className="usage-table-wrap">
            <table className="usage-table">
              <thead>
                <tr>
                  <th>{t("usage.colModel")}</th>
                  <th>{t("usage.colInput")}</th>
                  <th>{t("usage.colOutput")}</th>
                  <th>{t("usage.colTokens")}</th>
                  <th>{t("usage.colCost")}</th>
                  <th>{t("usage.colLlm")}</th>
                </tr>
              </thead>
              <tbody>
                {byModel.map((row) => (
                  <tr key={row.model}>
                    <td className="usage-table-model">{row.model}</td>
                    <td>{formatCompactNumber(row.input_tokens)}</td>
                    <td>{formatCompactNumber(row.output_tokens)}</td>
                    <td>{formatCompactNumber(row.total_tokens)}</td>
                    <td>{formatUsageCost(row.cost_usd, row.cost_display)}</td>
                    <td>{row.llm_calls}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="usage-section-head usage-section-head-spaced">
          <h3>{t("usage.sessionTableTitle")}</h3>
          <span className="usage-filter-count">{t("usage.shownCount", { count: sessions.length })}</span>
        </div>

        {usageQuery.isLoading ? (
          <p className="usage-status-line">{t("usage.loading")}</p>
        ) : sessions.length === 0 ? (
          <p className="usage-status-line">{t("usage.empty")}</p>
        ) : (
          <div className="usage-table-wrap">
            <table className="usage-table">
              <thead>
                <tr>
                  <th>{t("usage.colSession")}</th>
                  <th>{t("usage.colInput")}</th>
                  <th>{t("usage.colOutput")}</th>
                  <th>{t("usage.colTokens")}</th>
                  <th>{t("usage.colCost")}</th>
                  <th>{t("usage.colLlm")}</th>
                  <th>{t("usage.colTools")}</th>
                  <th>{t("usage.colStatus")}</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((row) => (
                  <tr key={row.session_id}>
                    <td className="usage-table-session" title={row.session_id}>
                      {row.title}
                    </td>
                    <td>{formatCompactNumber(row.input_tokens)}</td>
                    <td>{formatCompactNumber(row.output_tokens)}</td>
                    <td>{formatCompactNumber(row.total_tokens)}</td>
                    <td>{formatUsageCost(row.cost_usd, row.cost_display)}</td>
                    <td>{row.llm_calls}</td>
                    <td>{row.tool_calls}</td>
                    <td>
                      <span className={`usage-budget-pill usage-budget-pill-${row.budget_status}`}>
                        {row.budget_status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
