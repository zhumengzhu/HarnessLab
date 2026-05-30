import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "../../lib/api-client";
import { MarkdownView } from "../../lib/MarkdownView";
import { useI18n } from "../../lib/i18n";
import type {
  ProposalDetailResponse,
  ProposalGateRunResult,
  ProposalsResponse,
} from "../../lib/schemas";
import { summarizeGateOutput } from "./gate-utils";
import { useProposalGateState } from "./useProposalGateState";

export function ProposalPanel() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [proposalFilter, setProposalFilter] = useState<"open" | "all">("open");

  const proposals = useQuery({
    queryKey: ["proposals", proposalFilter],
    queryFn: () => apiGet<ProposalsResponse>(`/api/proposals?status=${proposalFilter}`),
  });

  const proposalDetail = useQuery({
    queryKey: ["proposal", selectedProposalId],
    queryFn: () =>
      apiGet<ProposalDetailResponse>(
        `/api/proposals/${encodeURIComponent(selectedProposalId || "")}`
      ),
    enabled: Boolean(selectedProposalId),
  });

  const gate = useProposalGateState({
    queryClient,
    selectedProposalId,
    proposalFilter,
    onClearedFromOpenList: () => setSelectedProposalId(null),
  });

  return (
    <section className="layout-single">
      <section className="panel">
        <div className="panel-title-row">
          <h2>{t("proposals.title")}</h2>
          <div className="proposal-filter">
            <button
              type="button"
              className={proposalFilter === "open" ? "active" : ""}
              onClick={() => setProposalFilter("open")}
            >
              {t("proposals.filterOpen")}
            </button>
            <button
              type="button"
              className={proposalFilter === "all" ? "active" : ""}
              onClick={() => setProposalFilter("all")}
            >
              {t("proposals.filterAll")}
            </button>
          </div>
        </div>
        {proposals.isLoading ? <p>{t("proposals.loading")}</p> : null}
        {proposals.isError ? (
          <p>{t("common.loadFailed", { error: (proposals.error as Error).message })}</p>
        ) : null}
        <div className="proposal-grid">
          <ul className="list">
            {(proposals.data?.proposals || []).map((p) => (
              <li key={p.id}>
                <button
                  className={selectedProposalId === p.id ? "active" : ""}
                  onClick={() => {
                    setSelectedProposalId(p.id);
                    gate.resetForNewProposalSelection();
                  }}
                  type="button"
                >
                  <strong>{p.id}</strong>
                  <small>
                    {p.kind} · {p.occurrences}
                  </small>
                </button>
              </li>
            ))}
          </ul>
          <div className="proposal-detail">
            {!selectedProposalId ? <p>{t("proposals.selectProposal")}</p> : null}
            {proposalDetail.isLoading ? <p>{t("proposals.loadingDetail")}</p> : null}
            {proposalDetail.isError ? (
              <p>{t("common.loadFailed", { error: (proposalDetail.error as Error).message })}</p>
            ) : null}
            {proposalDetail.data ? (
              <>
                <pre className="meta-block">
{JSON.stringify(
  {
    id: proposalDetail.data.proposal.id,
    status: proposalDetail.data.proposal.status,
    kind: proposalDetail.data.proposal.kind,
    occurrences: proposalDetail.data.proposal.occurrences,
    generated_at: proposalDetail.data.proposal.generated_at,
    superseded_by: proposalDetail.data.proposal.superseded_by,
  },
  null,
  2
)}
                </pre>
                <div className="proposal-gates">
                  <label>
                    <input
                      type="checkbox"
                      checked={gate.confirmReviewed}
                      onChange={(e) => gate.setConfirmReviewed(e.target.checked)}
                      disabled={gate.proposalActionBusy}
                    />
                    {t("proposals.confirmReviewed")}
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={gate.confirmPytestGreen}
                      onChange={(e) => gate.setConfirmPytestGreen(e.target.checked)}
                      disabled={gate.proposalActionBusy}
                    />
                    {t("proposals.confirmPytest")}
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={gate.confirmEvalNoRegression}
                      onChange={(e) => gate.setConfirmEvalNoRegression(e.target.checked)}
                      disabled={gate.proposalActionBusy}
                    />
                    {t("proposals.confirmEval")}
                  </label>
                </div>
                <div className="proposal-gate-actions">
                  <button
                    type="button"
                    disabled={gate.proposalActionBusy || gate.gateBusy !== null}
                    onClick={() => gate.runGate("pytest")}
                  >
                    {gate.gateBusy === "pytest" ? t("proposals.runningPytest") : t("proposals.runPytest")}
                  </button>
                  <button
                    type="button"
                    disabled={gate.proposalActionBusy || gate.gateBusy !== null}
                    onClick={() => gate.runGate("eval")}
                  >
                    {gate.gateBusy === "eval" ? t("proposals.runningEval") : t("proposals.runEval")}
                  </button>
                </div>
                {(gate.gateResults.pytest || gate.gateResults.eval) && (
                  <div className="proposal-gate-results">
                    {gate.gateResults.pytest && (
                      <GateResultCard result={gate.gateResults.pytest} />
                    )}
                    {gate.gateResults.eval && (
                      <GateResultCard result={gate.gateResults.eval} />
                    )}
                  </div>
                )}
                <div className="proposal-actions">
                  <button
                    type="button"
                    disabled={gate.proposalActionBusy || !gate.canAccept}
                    onClick={() => gate.updateProposalStatus("accepted")}
                  >
                    {t("proposals.accept")}
                  </button>
                  <button
                    type="button"
                    disabled={gate.proposalActionBusy}
                    onClick={() => gate.updateProposalStatus("rejected")}
                  >
                    {t("proposals.reject")}
                  </button>
                  <button
                    type="button"
                    disabled={gate.proposalActionBusy}
                    onClick={() => gate.updateProposalStatus("superseded")}
                  >
                    {t("proposals.supersede")}
                  </button>
                  {gate.proposalActionError ? (
                    <span className="error-text">{gate.proposalActionError}</span>
                  ) : null}
                </div>
                <div className="proposal-action-inputs">
                  <textarea
                    rows={3}
                    placeholder={t("proposals.decisionPlaceholder")}
                    value={gate.proposalDecisionNote}
                    onChange={(e) => gate.setProposalDecisionNote(e.target.value)}
                    disabled={gate.proposalActionBusy}
                  />
                  <input
                    placeholder={t("proposals.supersededPlaceholder")}
                    value={gate.proposalSupersededBy}
                    onChange={(e) => gate.setProposalSupersededBy(e.target.value)}
                    disabled={gate.proposalActionBusy}
                  />
                </div>
                <MarkdownView markdown={proposalDetail.data.proposal.body_markdown} />
              </>
            ) : null}
          </div>
        </div>
      </section>
    </section>
  );
}

function GateResultCard({ result }: { result: ProposalGateRunResult }) {
  const { t } = useI18n();
  const preview = summarizeGateOutput(result.stdout || result.stderr || "");
  const statusText = result.ok ? t("proposals.gateOk") : t("proposals.gateFailed");
  return (
    <div className={`proposal-gate-result ${result.ok ? "ok" : "fail"}`}>
      <div className="proposal-gate-result-head">
        <strong>{result.gate}</strong>
        <span>
          {statusText}
          {result.timed_out ? ` (${t("proposals.timeout")})` : ""} · {result.elapsed_ms}ms
        </span>
      </div>
      <pre>{preview || t("common.noOutput")}</pre>
      <details>
        <summary>{t("proposals.viewFullOutput")}</summary>
        <pre>{result.stdout || result.stderr || t("common.noOutput")}</pre>
      </details>
    </div>
  );
}
