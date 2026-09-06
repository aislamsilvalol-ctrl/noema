// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import LandingPage from "./page";

vi.mock("@/components/LanguageSwitcher", () => ({
  LanguageSwitcher: () => null,
}));

// jsdom has no matchMedia or IntersectionObserver: every media query is "no
// match" and the scroll observer never mounts, which is the reduced-motion
// path — the page must render fully on it.
window.matchMedia = vi.fn().mockImplementation((query: string) => ({
  matches: false,
  media: query,
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  addListener: vi.fn(),
  removeListener: vi.fn(),
  dispatchEvent: vi.fn(),
}));

const { meFn, demoFn } = vi.hoisted(() => ({ meFn: vi.fn(), demoFn: vi.fn() }));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: { me: meFn }, demoTeach: demoFn };
});

afterEach(() => vi.clearAllMocks());
meFn.mockRejectedValue(new Error("not signed in"));

describe("LandingPage", () => {
  it("opens with the one line and the one question, and offers to sign in", async () => {
    render(<LandingPage />);
    expect(
      screen.getAllByText("Learn anything.").length,
    ).toBeGreaterThanOrEqual(2);
    expect(
      screen.getByLabelText("What do you want to learn?"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start" })).toHaveAttribute(
      "href",
      "/login",
    );
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it('switches to "Continue learning" once a session is confirmed', async () => {
    meFn.mockResolvedValueOnce({ id: "u1", email: "x@y.z" });
    render(<LandingPage />);
    await waitFor(() =>
      expect(
        screen.getAllByRole("link", { name: "Continue learning" })[0],
      ).toHaveAttribute("href", "/chat"),
    );
  });

  it("streams the real tutor reply for a typed subject and carries it into the lesson step", async () => {
    demoFn.mockImplementation(
      async (_subject: string, callbacks: { onToken: (t: string) => void }) => {
        callbacks.onToken("Start with the slip. ");
        callbacks.onToken("Which part did the work?");
      },
    );
    const user = userEvent.setup();
    render(<LandingPage />);

    await user.type(
      screen.getByLabelText("What do you want to learn?"),
      "Psychology according to Freud",
    );
    await user.click(screen.getByRole("button", { name: /teach me/i }));

    // The reply is shown in the hero, in step 4 (the lesson) and in the rhythm demo.
    await waitFor(() =>
      expect(screen.getAllByText(/Which part did the work\?/)).toHaveLength(3),
    );
    expect(demoFn).toHaveBeenCalledWith(
      "Psychology according to Freud",
      expect.anything(),
      expect.anything(),
    );
    expect(screen.getByText(/That was the real tutor/)).toBeInTheDocument();
  });

  it("falls back to the written sample when the tutor is unavailable, and says so", async () => {
    demoFn.mockRejectedValue(new Error("503"));
    const user = userEvent.setup();
    render(<LandingPage />);

    await user.type(
      screen.getByLabelText("What do you want to learn?"),
      "Italian",
    );
    await user.click(screen.getByRole("button", { name: /teach me/i }));

    await screen.findByText(/The tutor is busy right now/);
    expect(screen.getAllByText(/Ragazzo/).length).toBeGreaterThan(0);
  });

  it("shows the engine as eight steps, and a wrong answer moves what it knows and what it will do", async () => {
    demoFn.mockRejectedValue(new Error("503"));
    const user = userEvent.setup();
    render(<LandingPage />);
    for (const id of [
      "step-1",
      "step-2",
      "step-3",
      "step-4",
      "step-5",
      "step-6",
      "step-7",
      "step-8",
    ]) {
      expect(document.querySelector(`[data-section="${id}"]`)).not.toBeNull();
    }
    expect(
      screen.getByText("Then we will not start with Freud."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Answer the question above/)).toBeInTheDocument();

    await user.type(
      screen.getByLabelText("What do you want to learn?"),
      "JavaScript",
    );
    await user.click(screen.getByRole("button", { name: /teach me/i }));
    await screen.findByText(/The tutor is busy right now/);

    await user.click(screen.getByRole("button", { name: "6" }));
    await user.click(screen.getByRole("button", { name: "Sure" }));
    expect(
      screen.getByText(/Close\. Look at this difference/),
    ).toBeInTheDocument();
    expect(screen.getByText(/returns a/)).toBeInTheDocument();
    expect(screen.getByText(/reordered after your answer/)).toBeInTheDocument();
    expect(
      screen.getByText(/Next time it will not define/),
    ).toBeInTheDocument();
  });

  it("says plainly how it differs from a chatbot, and keeps the legal links real", () => {
    render(<LandingPage />);
    expect(screen.getByText("Why not open a chatbot?")).toBeInTheDocument();
    expect(
      screen.getByText("Noema asks what you do not know yet."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute(
      "href",
      "/privacy",
    );
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute(
      "href",
      "/terms",
    );
    for (const id of ["ask", "versus", "rhythm", "close"]) {
      expect(document.querySelector(`[data-section="${id}"]`)).not.toBeNull();
    }
  });

  it("keeps Mino decorative: the figures are stills until the stage is ready, never announced", () => {
    render(<LandingPage />);
    const stages = document.querySelectorAll("[data-mino-stage]");
    expect(stages.length).toBeGreaterThanOrEqual(2);
    for (const img of document.querySelectorAll("[data-mino-stage] img")) {
      expect(img).toHaveAttribute("aria-hidden", "true");
      expect(img).toHaveAttribute("alt", "");
    }
  });
});
