import { request } from "../request";
import type {
  HarvestRunResponse,
  HarvestSpecInput,
  HarvestViewOutput,
} from "../types";

export const harvestApi = {
  listHarvests: () => request<HarvestViewOutput[]>("/harvests"),

  createHarvest: (body: HarvestSpecInput) =>
    request<HarvestViewOutput>("/harvests", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  replaceHarvest: (harvestId: string, body: HarvestSpecInput) =>
    request<HarvestViewOutput>(`/harvests/${encodeURIComponent(harvestId)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deleteHarvest: (harvestId: string) =>
    request<{ deleted: boolean }>(
      `/harvests/${encodeURIComponent(harvestId)}`,
      {
        method: "DELETE",
      },
    ),

  runHarvest: (harvestId: string) =>
    request<HarvestRunResponse>(
      `/harvests/${encodeURIComponent(harvestId)}/run`,
      { method: "POST" },
    ),

  pauseHarvest: (harvestId: string) =>
    request<HarvestViewOutput>(
      `/harvests/${encodeURIComponent(harvestId)}/pause`,
      { method: "POST" },
    ),

  resumeHarvest: (harvestId: string) =>
    request<HarvestViewOutput>(
      `/harvests/${encodeURIComponent(harvestId)}/resume`,
      { method: "POST" },
    ),
};
