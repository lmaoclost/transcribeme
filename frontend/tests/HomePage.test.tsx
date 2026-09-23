import { render, screen } from "@testing-library/react";
import { SWRConfig } from "swr";
import { vi } from "vitest";

import HomePage from "@/app/page";

const fetchMock = vi.fn();

vi.stubGlobal("fetch", fetchMock);

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/settings")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          cookies_configured: false,
          cookies_path: null,
          whisper_model: "small",
          translation_target_lang_code: "por_Latn",
          transcription_speed: 1.5,
          youtube_prefer_captions: true,
          youtube_sub_langs: "pt,en"
        })
      });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ jobs: [], total: 0 })
    });
  });
});

test("renders hero and queue form", async () => {
  render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <HomePage />
    </SWRConfig>
  );

  expect(
    await screen.findByRole("heading", { name: /transcribeme/i })
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Add to queue/i })).toBeInTheDocument();
});
