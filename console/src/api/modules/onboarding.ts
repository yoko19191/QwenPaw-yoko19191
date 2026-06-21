import { request } from "../request";
import type { OnboardingStatus } from "../types";

export const onboardingApi = {
  getOnboardingStatus: () => request<OnboardingStatus>("/onboarding/status"),

  completeOnboarding: () =>
    request<OnboardingStatus>("/onboarding/complete", { method: "POST" }),

  dismissOnboardingStep: (stepId: string) =>
    request<OnboardingStatus>(
      `/onboarding/steps/${encodeURIComponent(stepId)}/dismiss`,
      { method: "POST" },
    ),
};
