import { describe, it, expect, vi, afterEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/common_setup";
import { OAuthConfirmModal } from "./OAuthConfirmModal";
import { providerApi } from "../../../api/modules/provider";
import { openExternalLink } from "../../../utils/openExternalLink";

vi.mock("../../../api/modules/provider", () => ({
  providerApi: {
    startOAuth: vi.fn(),
    getOAuthStatus: vi.fn(),
  },
}));

vi.mock("../../../utils/openExternalLink", () => ({
  openExternalLink: vi.fn(),
}));

vi.mock("../../../hooks/useAppMessage", () => ({
  useAppMessage: () => ({
    message: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, string>) =>
      params?.provider ? `${key} ${params.provider}` : key,
  }),
}));

describe("OAuthConfirmModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows device-code details for Codex OAuth", async () => {
    const user = userEvent.setup();
    vi.mocked(providerApi.startOAuth).mockResolvedValue({
      authorize_url: "https://auth.openai.com/codex/device",
      state: "state-1",
      flow_type: "device_code",
      user_code: "ABCD-EFGH",
      verification_url: "https://auth.openai.com/codex/device",
      poll_interval: 3,
    });
    vi.mocked(providerApi.getOAuthStatus).mockResolvedValue({
      status: "pending",
    });

    renderWithProviders(
      <OAuthConfirmModal
        open
        providerId="openai"
        providerName="OpenAI"
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    await user.click(screen.getByText("modelSelector.oauthContinue"));

    expect(await screen.findByText("ABCD-EFGH")).toBeInTheDocument();
    expect(openExternalLink).toHaveBeenCalledWith(
      "https://auth.openai.com/codex/device",
      "_blank",
    );

    expect(providerApi.getOAuthStatus).not.toHaveBeenCalled();
  });
});
