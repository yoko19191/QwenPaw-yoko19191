import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/common_setup";
import { ModelsSection } from "./ModelsSection";
import api from "../../../../../api";

vi.mock("../../../../../api", () => ({
  default: {
    setActiveLlm: vi.fn(),
  },
}));

vi.mock("@/utils/freeModelSwitchWarning", () => ({
  confirmFreeModelSwitch: vi.fn().mockResolvedValue(true),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, string | number>) =>
      params?.index ? `${key} ${params.index}` : key,
  }),
}));

const providers = [
  {
    id: "openai",
    name: "OpenAI",
    api_key: "sk-test",
    is_local: false,
    is_custom: false,
    require_api_key: true,
    models: [
      { id: "gpt-5", name: "GPT-5" },
      { id: "gpt-5-mini", name: "GPT-5 Mini" },
    ],
    extra_models: [],
  },
  {
    id: "dashscope",
    name: "DashScope",
    api_key: "sk-test",
    is_local: false,
    is_custom: false,
    require_api_key: true,
    models: [{ id: "qwen3-max", name: "Qwen3 Max" }],
    extra_models: [],
  },
];

describe("ModelsSection", () => {
  beforeEach(() => {
    vi.mocked(api.setActiveLlm).mockResolvedValue({
      active_llm: { provider_id: "openai", model: "gpt-5-mini" },
      fallback_llms: [
        { provider_id: "openai", model: "gpt-5" },
        { provider_id: "dashscope", model: "qwen3-max" },
      ],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("saves reordered fallback rows with primary first", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const { container } = renderWithProviders(
      <ModelsSection
        providers={providers}
        activeModels={{
          active_llm: { provider_id: "openai", model: "gpt-5" },
          fallback_llms: [
            { provider_id: "openai", model: "gpt-5-mini" },
            { provider_id: "dashscope", model: "qwen3-max" },
          ],
        }}
        onSaved={onSaved}
      />,
    );

    expect(screen.getByText("models.primaryModel")).toBeInTheDocument();
    expect(screen.getByText("models.fallbackModel 1")).toBeInTheDocument();
    expect(screen.getByText("models.fallbackModel 2")).toBeInTheDocument();

    const moveUpButtons = Array.from(
      container.querySelectorAll('button[title="models.moveUp"]'),
    );
    await user.click(moveUpButtons[1]);
    await user.click(screen.getByText("models.saveFallbackOrder"));

    await waitFor(() => {
      expect(api.setActiveLlm).toHaveBeenCalledWith({
        provider_id: "openai",
        model: "gpt-5-mini",
        scope: "global",
        fallback_llms: [
          { provider_id: "openai", model: "gpt-5" },
          { provider_id: "dashscope", model: "qwen3-max" },
        ],
      });
    });
    expect(onSaved).toHaveBeenCalledOnce();
  });
});
