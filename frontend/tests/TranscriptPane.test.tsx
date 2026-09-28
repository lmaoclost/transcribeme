import { render, screen } from "@testing-library/react";
import { TranscriptPane, tsToSeconds, seekUrl } from "@/components/TranscriptPane";

describe("tsToSeconds", () => {
  it("parses MM:SS", () => {
    expect(tsToSeconds("01:23")).toBe(83);
  });
  it("parses HH:MM:SS", () => {
    expect(tsToSeconds("01:00:05")).toBe(3605);
  });
  it("returns 0 on garbage", () => {
    expect(tsToSeconds("xx:yy")).toBe(0);
  });
});

describe("seekUrl", () => {
  it("appends t param with ? when no query", () => {
    expect(seekUrl("/media", 83)).toBe("/media?t=83s");
  });
  it("appends with & when query exists", () => {
    expect(seekUrl("/media?a=1", 5)).toBe("/media?a=1&t=5s");
  });
});

describe("TranscriptPane", () => {
  it("plain text fallback when no segments", () => {
    render(<TranscriptPane text={"linha 1\nlinha 2"} segments={null} mediaUrl={null} />);
    expect(screen.getByText(/linha 1/)).toBeInTheDocument();
    expect(screen.queryByText("[00:01]")).not.toBeInTheDocument();
  });

  it("renders clickable timestamps with segments", () => {
    render(
      <TranscriptPane
        text="full"
        segments={[
          { start: "00:01", end: "00:29", text: "bem-vindos ao video" },
          { start: "00:30", end: "00:58", text: "hoje falamos de IA" },
        ]}
        mediaUrl="/api/jobs/x/media"
      />
    );
    expect(screen.getByText(/bem-vindos ao video/)).toBeInTheDocument();
    const ts = screen.getByText("[00:01]");
    expect(ts).toHaveAttribute("href", "/api/jobs/x/media?t=1s");
    expect(screen.getByText("[00:30]")).toHaveAttribute("href", "/api/jobs/x/media?t=30s");
  });
});