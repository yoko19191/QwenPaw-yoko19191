import type { CronJobRuntime, CronJobSchedule } from "./cronjob";

export interface HarvestTarget {
  channel: string;
  user_id: string;
  session_id: string;
}

export interface HarvestSpecInput {
  id?: string | null;
  name: string;
  template_id?: string;
  emoji?: string;
  enabled?: boolean;
  prompt: string;
  schedule: CronJobSchedule;
  target?: HarvestTarget;
  runtime?: CronJobRuntime;
  cron_job_id?: string | null;
  created_at?: number;
  updated_at?: number;
}

export interface HarvestStatsOutput {
  total_generated: number;
  success_rate: number;
  consecutive_days: number;
}

export interface HarvestLastGeneratedOutput {
  timestamp: string;
  success: boolean;
}

export interface HarvestViewOutput extends Required<HarvestSpecInput> {
  id: string;
  template_id: string;
  emoji: string;
  enabled: boolean;
  target: HarvestTarget;
  cron_job_id: string;
  created_at: number;
  updated_at: number;
  status: "active" | "paused" | "error";
  next_run_at?: string | null;
  last_generated?: HarvestLastGeneratedOutput | null;
  stats: HarvestStatsOutput;
}

export interface HarvestRunResponse {
  started: boolean;
  harvest: HarvestViewOutput;
}
