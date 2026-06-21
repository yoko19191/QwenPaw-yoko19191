export interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  action_label: string;
  action_path: string;
  complete: boolean;
  optional: boolean;
  dismissed: boolean;
}

export interface OnboardingStatus {
  completed: boolean;
  progress: number;
  steps: OnboardingStep[];
}
