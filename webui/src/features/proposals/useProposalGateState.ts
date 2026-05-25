import { useState } from "react";
import type { QueryClient } from "@tanstack/react-query";
import { apiPost } from "../../lib/api-client";
import type {
  ProposalDetailResponse,
  ProposalGateRunResponse,
  ProposalGateRunResult,
  ProposalStatusUpdateRequest,
} from "../../lib/schemas";

type GateName = "pytest" | "eval";

type UseProposalGateStateArgs = {
  queryClient: QueryClient;
  selectedProposalId: string | null;
  proposalFilter: "open" | "all";
  onClearedFromOpenList: () => void;
};

export function useProposalGateState(args: UseProposalGateStateArgs) {
  const { queryClient, selectedProposalId, proposalFilter, onClearedFromOpenList } = args;
  const [proposalDecisionNote, setProposalDecisionNote] = useState("");
  const [proposalSupersededBy, setProposalSupersededBy] = useState("");
  const [proposalActionError, setProposalActionError] = useState<string | null>(null);
  const [proposalActionBusy, setProposalActionBusy] = useState(false);
  const [confirmReviewed, setConfirmReviewed] = useState(false);
  const [confirmPytestGreen, setConfirmPytestGreen] = useState(false);
  const [confirmEvalNoRegression, setConfirmEvalNoRegression] = useState(false);
  const [gateBusy, setGateBusy] = useState<GateName | null>(null);
  const [gateResults, setGateResults] = useState<Partial<Record<GateName, ProposalGateRunResult>>>(
    {}
  );

  const canAccept = confirmReviewed && confirmPytestGreen && confirmEvalNoRegression;

  function resetForNewProposalSelection() {
    setProposalActionError(null);
    setProposalDecisionNote("");
    setProposalSupersededBy("");
    setConfirmReviewed(false);
    setConfirmPytestGreen(false);
    setConfirmEvalNoRegression(false);
    setGateResults({});
  }

  async function runGate(gate: GateName) {
    if (gateBusy) return;
    setProposalActionError(null);
    setGateBusy(gate);
    try {
      const data = await apiPost<ProposalGateRunResponse>("/api/proposals/gates/run", { gate });
      const result = data.result;
      setGateResults((prev) => ({ ...prev, [gate]: result }));
      if (gate === "pytest") setConfirmPytestGreen(result.ok);
      if (gate === "eval") setConfirmEvalNoRegression(result.ok);
    } catch (err) {
      setProposalActionError((err as Error).message);
    } finally {
      setGateBusy(null);
    }
  }

  async function updateProposalStatus(nextStatus: ProposalStatusUpdateRequest["status"]) {
    if (!selectedProposalId || proposalActionBusy) return;
    setProposalActionBusy(true);
    setProposalActionError(null);
    const payload: ProposalStatusUpdateRequest = { status: nextStatus };
    if (nextStatus === "rejected") payload.decision_note = proposalDecisionNote;
    if (nextStatus === "superseded") payload.superseded_by = proposalSupersededBy;
    if (nextStatus === "accepted") {
      payload.confirm_reviewed = confirmReviewed;
      payload.confirm_pytest_green = confirmPytestGreen;
      payload.confirm_eval_no_regression = confirmEvalNoRegression;
    }
    try {
      await apiPost<ProposalDetailResponse>(
        `/api/proposals/${encodeURIComponent(selectedProposalId)}/status`,
        payload as Record<string, unknown>
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["proposals"] }),
        queryClient.invalidateQueries({ queryKey: ["proposal", selectedProposalId] }),
      ]);
      if (nextStatus !== "open" && proposalFilter === "open") {
        onClearedFromOpenList();
      }
    } catch (err) {
      setProposalActionError((err as Error).message);
    } finally {
      setProposalActionBusy(false);
    }
  }

  return {
    proposalDecisionNote,
    setProposalDecisionNote,
    proposalSupersededBy,
    setProposalSupersededBy,
    proposalActionError,
    proposalActionBusy,
    confirmReviewed,
    setConfirmReviewed,
    confirmPytestGreen,
    setConfirmPytestGreen,
    confirmEvalNoRegression,
    setConfirmEvalNoRegression,
    gateBusy,
    gateResults,
    canAccept,
    resetForNewProposalSelection,
    runGate,
    updateProposalStatus,
  };
}
