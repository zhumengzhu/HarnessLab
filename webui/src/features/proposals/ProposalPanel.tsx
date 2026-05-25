import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "../../lib/api-client";
import type {
  ProposalDetailResponse,
  ProposalGateRunResult,
  ProposalsResponse,
} from "../../lib/schemas";
import { summarizeGateOutput } from "./gate-utils";
import { useProposalGateState } from "./useProposalGateState";

export function ProposalPanel() {
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
          <h2>Proposals</h2>
          <div className="proposal-filter">
            <button
              type="button"
              className={proposalFilter === "open" ? "active" : ""}
              onClick={() => setProposalFilter("open")}
            >
              Open
            </button>
            <button
              type="button"
              className={proposalFilter === "all" ? "active" : ""}
              onClick={() => setProposalFilter("all")}
            >
              All
            </button>
          </div>
        </div>
        {proposals.isLoading ? <p>Loading...</p> : null}
        {proposals.isError ? <p>Failed: {(proposals.error as Error).message}</p> : null}
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
                  <small>{p.kind} · {p.occurrences}</small>
                </button>
              </li>
            ))}
          </ul>
          <div className="proposal-detail">
            {!selectedProposalId ? <p>Select a proposal.</p> : null}
            {proposalDetail.isLoading ? <p>Loading proposal...</p> : null}
            {proposalDetail.isError ? (
              <p>Failed: {(proposalDetail.error as Error).message}</p>
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
                    已人工审阅变更
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={gate.confirmPytestGreen}
                      onChange={(e) => gate.setConfirmPytestGreen(e.target.checked)}
                      disabled={gate.proposalActionBusy}
                    />
                    `uv run pytest` 已通过
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={gate.confirmEvalNoRegression}
                      onChange={(e) => gate.setConfirmEvalNoRegression(e.target.checked)}
                      disabled={gate.proposalActionBusy}
                    />
                    `uv run harnesslab eval` 无回归
                  </label>
                </div>
                <div className="proposal-gate-actions">
                  <button
                    type="button"
                    disabled={gate.proposalActionBusy || gate.gateBusy !== null}
                    onClick={() => gate.runGate("pytest")}
                  >
                    {gate.gateBusy === "pytest" ? "Running pytest..." : "Run uv run pytest"}
                  </button>
                  <button
                    type="button"
                    disabled={gate.proposalActionBusy || gate.gateBusy !== null}
                    onClick={() => gate.runGate("eval")}
                  >
                    {gate.gateBusy === "eval" ? "Running eval..." : "Run uv run harnesslab eval"}
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
                    Accept
                  </button>
                  <button
                    type="button"
                    disabled={gate.proposalActionBusy}
                    onClick={() => gate.updateProposalStatus("rejected")}
                  >
                    Reject
                  </button>
                  <button
                    type="button"
                    disabled={gate.proposalActionBusy}
                    onClick={() => gate.updateProposalStatus("superseded")}
                  >
                    Supersede
                  </button>
                  {gate.proposalActionError ? (
                    <span className="error-text">{gate.proposalActionError}</span>
                  ) : null}
                </div>
                <div className="proposal-action-inputs">
                  <textarea
                    rows={3}
                    placeholder="Decision note (for reject)"
                    value={gate.proposalDecisionNote}
                    onChange={(e) => gate.setProposalDecisionNote(e.target.value)}
                    disabled={gate.proposalActionBusy}
                  />
                  <input
                    placeholder="Superseded by proposal id"
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

function MarkdownView({ markdown }: { markdown: string }) {
  const lines = markdown.split("\n");
  return (
    <div className="markdown-view">
      {lines.map((line, idx) => {
        if (line.startsWith("### ")) return <h4 key={idx}>{line.slice(4)}</h4>;
        if (line.startsWith("## ")) return <h3 key={idx}>{line.slice(3)}</h3>;
        if (line.startsWith("# ")) return <h2 key={idx}>{line.slice(2)}</h2>;
        if (line.startsWith("- ")) return <li key={idx}>{line.slice(2)}</li>;
        if (/^\d+\.\s+/.test(line)) return <li key={idx}>{line.replace(/^\d+\.\s+/, "")}</li>;
        if (!line.trim()) return <br key={idx} />;
        return <p key={idx}>{line}</p>;
      })}
    </div>
  );
}

function GateResultCard({ result }: { result: ProposalGateRunResult }) {
  const preview = summarizeGateOutput(result.stdout || result.stderr || "");
  return (
    <div className={`proposal-gate-result ${result.ok ? "ok" : "fail"}`}>
      <div className="proposal-gate-result-head">
        <strong>{result.gate}</strong>
        <span>
          {result.ok ? "ok" : "failed"}
          {result.timed_out ? " (timeout)" : ""} · {result.elapsed_ms}ms
        </span>
      </div>
      <pre>{preview || "(no output)"}</pre>
      <details>
        <summary>查看完整输出</summary>
        <pre>{result.stdout || result.stderr || "(no output)"}</pre>
      </details>
    </div>
  );
}
