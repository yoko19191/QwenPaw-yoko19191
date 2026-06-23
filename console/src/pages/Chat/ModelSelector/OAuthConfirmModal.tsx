import { useState, useEffect, useCallback, useRef } from "react";
import { Modal, Button } from "@agentscope-ai/design";
import { Loader2, ExternalLink, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import { providerApi } from "../../../api/modules/provider";
import { useAppMessage } from "../../../hooks/useAppMessage";
import { openExternalLink } from "../../../utils/openExternalLink";

interface OAuthConfirmModalProps {
  open: boolean;
  providerId: string;
  providerName: string;
  onSuccess: () => void;
  onCancel: () => void;
}

export function OAuthConfirmModal({
  open,
  providerId,
  providerName,
  onSuccess,
  onCancel,
}: OAuthConfirmModalProps) {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const [phase, setPhase] = useState<"confirm" | "waiting">("confirm");
  const [deviceCode, setDeviceCode] = useState<{
    userCode: string;
    verificationUrl: string;
  } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) {
      setPhase("confirm");
      setDeviceCode(null);
      if (pollRef.current) clearInterval(pollRef.current);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    }
  }, [open]);

  const handleContinue = useCallback(async () => {
    try {
      const start = await providerApi.startOAuth(providerId);
      const {
        authorize_url,
        state,
        flow_type,
        user_code,
        verification_url,
        poll_interval,
      } = start;
      setPhase("waiting");

      if (flow_type === "device_code") {
        setDeviceCode({
          userCode: user_code || "",
          verificationUrl: verification_url || authorize_url,
        });
        openExternalLink(verification_url || authorize_url, "_blank");
      } else {
        openExternalLink(authorize_url, "_blank", "popup,width=600,height=700");
      }

      // Poll backend status until completion (same pattern as MCP OAuth)
      pollRef.current = setInterval(
        async () => {
          try {
            const { status, error } = await providerApi.getOAuthStatus(
              providerId,
              state,
            );
            if (status === "completed") {
              if (pollRef.current) clearInterval(pollRef.current);
              if (timeoutRef.current) clearTimeout(timeoutRef.current);
              message.success(
                t("modelSelector.oauthConnected", { provider: providerName }),
              );
              onSuccess();
            } else if (status === "failed") {
              if (pollRef.current) clearInterval(pollRef.current);
              if (timeoutRef.current) clearTimeout(timeoutRef.current);
              message.error(t("modelSelector.oauthFailed"));
              onCancel();
            } else if (status === "expired") {
              if (pollRef.current) clearInterval(pollRef.current);
              if (timeoutRef.current) clearTimeout(timeoutRef.current);
              message.error(error || t("modelSelector.oauthExpired"));
              onCancel();
            }
          } catch {
            // Ignore polling errors
          }
        },
        Math.max(1000, (poll_interval || 2) * 1000),
      );

      // Timeout after 5 minutes
      timeoutRef.current = setTimeout(() => {
        if (pollRef.current) clearInterval(pollRef.current);
      }, 300000);
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("modelSelector.oauthFailed"),
      );
      onCancel();
    }
  }, [providerId, providerName, onSuccess, onCancel, message, t]);

  const handleCopyCode = useCallback(async () => {
    if (!deviceCode?.userCode) return;
    try {
      await navigator.clipboard.writeText(deviceCode.userCode);
      message.success(t("modelSelector.oauthCodeCopied"));
    } catch {
      message.error(t("common.copyFailed"));
    }
  }, [deviceCode?.userCode, message, t]);

  return (
    <Modal
      open={open}
      onCancel={onCancel}
      footer={null}
      closable={phase === "confirm"}
      maskClosable={phase === "confirm"}
      width={420}
    >
      {phase === "confirm" ? (
        <div style={{ textAlign: "center", padding: "16px 0" }}>
          <ExternalLink
            size={40}
            style={{ color: "#6366f1", marginBottom: 16 }}
          />
          <h3 style={{ margin: "0 0 8px", fontSize: 16, fontWeight: 600 }}>
            {t("modelSelector.oauthTitle", { provider: providerName })}
          </h3>
          <p style={{ color: "var(--text-secondary)", margin: "0 0 24px" }}>
            {t("modelSelector.oauthDescription", { provider: providerName })}
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
            <Button onClick={onCancel}>{t("common.cancel")}</Button>
            <Button type="primary" onClick={handleContinue}>
              {t("modelSelector.oauthContinue")}
            </Button>
          </div>
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: "24px 0" }}>
          <Loader2
            size={32}
            style={{ color: "#6366f1", animation: "spin 1s linear infinite" }}
          />
          <h3 style={{ margin: "16px 0 8px", fontSize: 16, fontWeight: 600 }}>
            {t("modelSelector.oauthWaiting")}
          </h3>
          {deviceCode ? (
            <>
              <p
                style={{
                  color: "var(--text-secondary)",
                  margin: "0 0 16px",
                }}
              >
                {t("modelSelector.oauthDeviceDescription")}
              </p>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                  marginBottom: 16,
                }}
              >
                <code
                  style={{
                    fontSize: 22,
                    fontWeight: 700,
                    letterSpacing: 1,
                    padding: "8px 12px",
                    borderRadius: 6,
                    background: "var(--color-bg-layout, #f5f5f5)",
                  }}
                >
                  {deviceCode.userCode}
                </code>
                <Button icon={<Copy size={14} />} onClick={handleCopyCode} />
              </div>
              <Button
                icon={<ExternalLink size={14} />}
                onClick={() => openExternalLink(deviceCode.verificationUrl)}
                style={{ marginBottom: 16 }}
              >
                {t("modelSelector.oauthOpenVerification")}
              </Button>
            </>
          ) : (
            <p style={{ color: "var(--text-secondary)", margin: "0 0 24px" }}>
              {t("modelSelector.oauthWaitingDescription")}
            </p>
          )}
          <Button onClick={onCancel}>{t("common.cancel")}</Button>
        </div>
      )}
    </Modal>
  );
}
