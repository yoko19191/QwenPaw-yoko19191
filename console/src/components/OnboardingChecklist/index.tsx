import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Progress } from "antd";
import { CheckCircle2, Circle, ExternalLink, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "../../api";
import type { OnboardingStatus, OnboardingStep } from "../../api/types";
import { useAgentStore } from "../../stores/agentStore";
import styles from "./index.module.less";

export default function OnboardingChecklist() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const selectedAgent = useAgentStore((state) => state.selectedAgent);
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [loadingStepId, setLoadingStepId] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await api.getOnboardingStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus, selectedAgent]);

  const visibleSteps = useMemo<OnboardingStep[]>(() => {
    if (!status || status.completed) return [];
    return status.steps.filter((step) => !step.complete && !step.dismissed);
  }, [status]);

  const completeCount = useMemo(
    () => status?.steps.filter((step) => step.complete).length ?? 0,
    [status],
  );

  const handleDismissStep = async (stepId: string) => {
    setLoadingStepId(stepId);
    try {
      setStatus(await api.dismissOnboardingStep(stepId));
    } finally {
      setLoadingStepId(null);
    }
  };

  const handleComplete = async () => {
    setLoadingStepId("__complete__");
    try {
      setStatus(await api.completeOnboarding());
    } finally {
      setLoadingStepId(null);
    }
  };

  if (!status || visibleSteps.length === 0) {
    return null;
  }

  return (
    <div className={styles.onboardingChecklist}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <div className={styles.title}>
            {t("onboarding.title", { defaultValue: "Setup checklist" })}
          </div>
          <div className={styles.subtitle}>
            {t("onboarding.progress", {
              defaultValue: "{{done}}/{{total}} ready",
              done: completeCount,
              total: status.steps.length,
            })}
          </div>
        </div>
        <Progress
          className={styles.progress}
          percent={Math.round(status.progress * 100)}
          showInfo={false}
          size="small"
        />
        <Button
          type="text"
          size="small"
          icon={<X size={15} />}
          loading={loadingStepId === "__complete__"}
          onClick={() => void handleComplete()}
          aria-label={t("common.close")}
        />
      </div>
      <div className={styles.steps}>
        {visibleSteps.map((step) => (
          <div key={step.id} className={styles.step}>
            <Circle size={16} className={styles.stepIcon} />
            <div className={styles.stepText}>
              <div className={styles.stepTitle}>{step.title}</div>
              <div className={styles.stepDescription}>{step.description}</div>
            </div>
            <Button
              size="small"
              icon={<ExternalLink size={14} />}
              onClick={() => navigate(step.action_path)}
            >
              {step.action_label}
            </Button>
            <Button
              type="text"
              size="small"
              icon={<X size={14} />}
              loading={loadingStepId === step.id}
              onClick={() => void handleDismissStep(step.id)}
              aria-label={t("common.close")}
            />
          </div>
        ))}
        {status.steps
          .filter((step) => step.complete)
          .slice(0, 1)
          .map((step) => (
            <div key={step.id} className={`${styles.step} ${styles.stepDone}`}>
              <CheckCircle2 size={16} className={styles.stepDoneIcon} />
              <div className={styles.stepText}>
                <div className={styles.stepTitle}>{step.title}</div>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
