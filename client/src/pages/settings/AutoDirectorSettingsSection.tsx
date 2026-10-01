import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getAutoDirectorApprovalPreferenceSettings,
  getAutoDirectorIssuePolicy,
  getPendingReviewAutoPromotionSettings,
  saveAutoDirectorApprovalPreferenceSettings,
  saveAutoDirectorIssuePolicy,
  savePendingReviewAutoPromotionSettings,
} from "@/api/settings";
import { queryKeys } from "@/api/queryKeys";
import { AutoDirectorApprovalPreferenceCard } from "./AutoDirectorApprovalPreferenceCard";
import { AutoDirectorPendingReviewAutoPromotionCard } from "./AutoDirectorPendingReviewAutoPromotionCard";
import { AutoDirectorIssuePolicyCard } from "./AutoDirectorIssuePolicyCard";

export default function AutoDirectorSettingsSection(props: {
  onActionResult: (message: string) => void;
  collapseAdvanced?: boolean;
}) {
  const { onActionResult, collapseAdvanced = false } = props;
  const queryClient = useQueryClient();
  const [approvalPreferenceDraft, setApprovalPreferenceDraft] = useState<string[] | null>(null);

  const approvalPreferenceQuery = useQuery({
    queryKey: queryKeys.settings.autoDirectorApprovalPreferences,
    queryFn: getAutoDirectorApprovalPreferenceSettings,
  });
  const issuePolicyQuery = useQuery({
    queryKey: queryKeys.settings.autoDirectorIssuePolicy,
    queryFn: getAutoDirectorIssuePolicy,
  });
  const pendingReviewAutoPromotionQuery = useQuery({
    queryKey: queryKeys.settings.pendingReviewAutoPromotion,
    queryFn: getPendingReviewAutoPromotionSettings,
  });
  const approvalPreference = approvalPreferenceQuery.data?.data;
  const pendingReviewAutoPromotion = pendingReviewAutoPromotionQuery.data?.data;
  const issuePolicy = issuePolicyQuery.data?.data;
  const approvalCodes = approvalPreferenceDraft ?? approvalPreference?.approvalPointCodes ?? [];

  const saveApprovalPreferenceMutation = useMutation({
    mutationFn: saveAutoDirectorApprovalPreferenceSettings,
    onSuccess: async (response) => {
      onActionResult(response.message ?? "审批授权偏好已保存。");
      if (response.data) {
        setApprovalPreferenceDraft(response.data.approvalPointCodes);
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.autoDirectorApprovalPreferences });
    },
    onError: (error) => {
      onActionResult(error instanceof Error ? error.message : "保存审批授权偏好失败。");
    },
  });

  const savePendingReviewAutoPromotionMutation = useMutation({
    mutationFn: savePendingReviewAutoPromotionSettings,
    onSuccess: async (response) => {
      onActionResult(response.message ?? "待确认状态自动放行设置已保存。");
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.pendingReviewAutoPromotion });
    },
    onError: (error) => {
      onActionResult(error instanceof Error ? error.message : "保存待确认状态自动放行设置失败。");
    },
  });
  const saveIssuePolicyMutation = useMutation({
    mutationFn: saveAutoDirectorIssuePolicy,
    onSuccess: async (response) => {
      onActionResult(response.message ?? "问题处理规则已保存。");
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings.autoDirectorIssuePolicy });
    },
    onError: (error) => {
      onActionResult(error instanceof Error ? error.message : "保存问题处理规则失败。");
    },
  });

  return (
    <>
      <AutoDirectorIssuePolicyCard
        policy={issuePolicy}
        isLoading={issuePolicyQuery.isLoading}
        isSaving={saveIssuePolicyMutation.isPending}
        onSave={(nextPolicy) => saveIssuePolicyMutation.mutate(nextPolicy)}
      />

      <AutoDirectorApprovalPreferenceCard
        settings={approvalPreference}
        draftCodes={approvalCodes}
        onDraftCodesChange={setApprovalPreferenceDraft}
        onSave={() => saveApprovalPreferenceMutation.mutate({
          approvalPointCodes: approvalCodes,
        })}
        isSaving={saveApprovalPreferenceMutation.isPending}
      />

      {collapseAdvanced ? (
        <details className="rounded-md border bg-muted/20 p-4">
          <summary className="cursor-pointer text-sm font-medium">高级控制</summary>
          <div className="mt-4 space-y-4">
            <AdvancedControls />
          </div>
        </details>
      ) : <AdvancedControls />}
    </>
  );

  function AdvancedControls() {
    return <>
      <AutoDirectorPendingReviewAutoPromotionCard
        settings={pendingReviewAutoPromotion}
        isLoading={pendingReviewAutoPromotionQuery.isLoading}
        isSaving={savePendingReviewAutoPromotionMutation.isPending}
        onEnable={(payload) => savePendingReviewAutoPromotionMutation.mutate({ enabled: true, acknowledgedRisks: payload.acknowledgedRisks, confirmationText: payload.confirmationText })}
        onDisable={() => savePendingReviewAutoPromotionMutation.mutate({ enabled: false })}
      />
    </>;
  }
}
