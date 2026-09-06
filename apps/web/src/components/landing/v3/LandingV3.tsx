"use client";

/**
 * The landing page: the tutor at work, once.
 *
 * One opening line, a live demo, and then the engine shown step by step —
 * you say, it probes, it plans, it teaches, it asks, it notices, it
 * adjusts, it returns — each step carrying a real fragment of the product
 * rather than a claim about it. The visitor's own subject runs through all
 * of it: the hero calls the real tutor (POST /ai/demo; a written sample
 * when it cannot) and the later fragments adapt to what was typed. Mino is
 * one character across the page, in WebGL: the hero figure, the companion
 * that follows the scroll and the figure at the close share a controller.
 *
 * Editorial, not templated: hairlines and space instead of boxes, two
 * display sizes for the two lines that matter, and the only card on the
 * page is the one that is a card.
 */

import Link from "next/link";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Wordmark } from "@/components/brand/Wordmark";
import { MinoLive, MinoProvider, useMino } from "@/components/mino/Mino";
import type { MinoState } from "@/components/mino/machine";
import { Button, ButtonLink } from "@/components/ui/Button";
import { track } from "@/lib/analytics";
import { ApiError, api, demoTeach } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Markdown } from "@/lib/markdown";
import { rememberPrefill } from "@/lib/prefill";
import { bankFor, type SubjectBank } from "./subjects";
import { useActiveSection } from "./useActiveSection";

const SECTIONS = [
  "ask",
  "step-1",
  "step-2",
  "step-3",
  "step-4",
  "step-5",
  "step-6",
  "step-7",
  "step-8",
  "versus",
  "rhythm",
  "close",
] as const;
type Section = (typeof SECTIONS)[number];

// What Mino is doing while each part of the page is in view.
const SECTION_STATE: Record<Section, MinoState> = {
  ask: "idle",
  "step-1": "listening",
  "step-2": "questioning",
  "step-3": "writing",
  "step-4": "teaching",
  "step-5": "curious",
  "step-6": "thinking",
  "step-7": "correcting",
  "step-8": "reading",
  versus: "idle",
  rhythm: "teaching",
  close: "wave",
};

const REMEMBERED_DAYS = 9;
const NEXT_REVIEW_DAYS = 11;

type DemoStatus = "idle" | "streaming" | "live" | "sample";

export function LandingV3() {
  return (
    <MinoProvider>
      <Page />
    </MinoProvider>
  );
}

function Page() {
  const { t, locale } = useI18n();
  const copy = t.landing4;
  const mino = useMino();
  const { active, register } = useActiveSection(SECTIONS);

  const [signedIn, setSignedIn] = useState(false);
  const [subject, setSubject] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [status, setStatus] = useState<DemoStatus>("idle");
  const [rotating, setRotating] = useState(0);
  const [answer, setAnswer] = useState<number | null>(null);
  const [sure, setSure] = useState<boolean | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [demoMode, setDemoMode] = useState<"normal" | "focus">("normal");
  const abort = useRef<AbortController | null>(null);
  const pauseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const bank: SubjectBank = bankFor(
    asked ?? copy.hero.subjects[0] ?? "",
    locale,
  );
  const answered = answer !== null && sure !== null;
  const correct = answer === bank.correct;
  const lessonText = reply || bank.sample;

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then(() => {
        if (!cancelled) setSignedIn(true);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // The subject under the title turns over until the visitor names one.
  useEffect(() => {
    if (asked) return;
    if (
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    const timer = window.setInterval(
      () => setRotating((i) => (i + 1) % copy.hero.subjects.length),
      2600,
    );
    return () => window.clearInterval(timer);
  }, [asked, copy.hero.subjects.length]);

  // Scroll moves the character between parts — unless it is busy with the
  // demo, or the visitor is in the field, which directs it itself.
  useEffect(() => {
    if (status === "streaming") return;
    if (active === "step-5" && answered) return;
    if (active === "ask" && document.activeElement === input.current) return;
    mino.setState(SECTION_STATE[active as Section] ?? "idle");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `mino` is stable; status/answered gate only
  }, [active]);

  function onType(value: string) {
    setSubject(value);
    if (pauseTimer.current) clearTimeout(pauseTimer.current);
    if (!value.trim()) {
      mino.on("input_focus");
      return;
    }
    mino.on("input_typing");
    mino.focus(input.current);
    pauseTimer.current = setTimeout(() => mino.on("input_pause"), 800);
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    const trimmed = subject.trim();
    if (!trimmed || status === "streaming") return;
    if (pauseTimer.current) clearTimeout(pauseTimer.current);
    track("cta_clicked", { location: "hero_ask" });

    setAsked(trimmed);
    setReply("");
    setAnswer(null);
    setSure(null);
    setFlipped(false);
    setStatus("streaming");
    mino.on("request_started");

    abort.current?.abort();
    abort.current = new AbortController();
    let sawToken = false;
    let failed = false;
    try {
      await demoTeach(
        trimmed,
        {
          onToken: (text) => {
            if (!sawToken) {
              sawToken = true;
              mino.on("response_streaming");
            }
            setReply((current) => current + text);
          },
          onError: () => {
            failed = true;
          },
        },
        abort.current.signal,
      );
    } catch (err) {
      failed = !(err instanceof DOMException && err.name === "AbortError");
      if (err instanceof ApiError) failed = true;
    }
    if (failed || !sawToken) {
      setReply(bankFor(trimmed, locale).sample);
      setStatus("sample");
    } else {
      setStatus("live");
    }
    mino.on("response_done");
    mino.setState("teaching");
  }

  function changeSubject() {
    abort.current?.abort();
    setAsked(null);
    setReply("");
    setStatus("idle");
    setSubject("");
    mino.reset();
    input.current?.focus();
  }

  function pick(index: number) {
    if (answered) return;
    setAnswer(index);
    mino.on("input_pause");
  }

  function confirm(wasSure: boolean) {
    if (answer === null) return;
    setSure(wasSure);
    mino.react(answer === bank.correct ? "correct" : "wrong");
  }

  function start() {
    if (asked) rememberPrefill(asked);
    track("cta_clicked", { location: "landing_close" });
  }

  const primaryHref = signedIn ? "/chat" : "/login";
  const rotatingSubject = asked ?? copy.hero.subjects[rotating] ?? "";
  const steps = copy.engine.steps;
  const stepAt = (i: number) =>
    steps[i] ?? { n: String(i + 1), title: "", body: "" };

  return (
    <main className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Wordmark size="md" className="text-ink-900" />
        <nav className="flex items-center gap-5 text-sm text-ink-600">
          <a
            href="https://github.com/aislamsilvalol-ctrl/noema"
            className="transition-colors duration-fast hover:text-ink-900"
          >
            {copy.nav.code}
          </a>
          <Link
            href={signedIn ? "/chat" : "/login"}
            onClick={() => track("cta_clicked", { location: "header" })}
            className="transition-colors duration-fast hover:text-ink-900"
          >
            {signedIn ? copy.nav.continueLearning : copy.nav.signIn}
          </Link>
          <LanguageSwitcher />
        </nav>
      </header>

      {/* ── the opening ─────────────────────────────────────────────────── */}
      <section
        ref={register("ask")}
        data-section="ask"
        className="mx-auto grid max-w-6xl gap-8 px-6 pb-24 pt-8 md:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] md:items-center md:pt-16"
      >
        <div>
          <h1 className="font-display text-5xl text-ink-900 md:text-6xl">
            {copy.hero.title}
            <span className="mt-2 block text-signal" aria-live="off">
              <span
                key={rotatingSubject}
                className="inline-block animate-fade-up"
              >
                {rotatingSubject}
              </span>
            </span>
          </h1>
          <p className="mt-8 max-w-reading text-md text-ink-600">
            {copy.hero.lead}
          </p>

          <form onSubmit={ask} className="mt-10">
            <label
              htmlFor="ask"
              className="block font-display text-xl text-ink-900"
            >
              {copy.hero.label}
            </label>
            <div className="mt-4 flex max-w-xl gap-2">
              <input
                id="ask"
                ref={input}
                value={subject}
                onChange={(event) => onType(event.target.value)}
                onFocus={() => {
                  mino.on("input_focus");
                  mino.focus(input.current);
                }}
                onBlur={() => !subject && mino.on("input_blur")}
                placeholder={copy.hero.placeholder}
                autoComplete="off"
                enterKeyHint="go"
                className="min-w-0 flex-1 border-b-2 border-line bg-transparent px-0 py-3 text-lg text-ink-900 outline-none transition-colors duration-fast placeholder:text-ink-400 focus:border-signal"
              />
              <Button
                type="submit"
                variant="primary"
                size="lg"
                disabled={!subject.trim()}
                busy={status === "streaming" ? copy.hero.thinking : undefined}
              >
                {copy.hero.submit}
              </Button>
            </div>
            {!asked && (
              <p className="mt-3 text-sm text-ink-500">{copy.hero.note}</p>
            )}
          </form>

          {asked && (
            <div className="mt-8 max-w-xl animate-fade-up" aria-live="polite">
              <Speaker>Mino</Speaker>
              <div className="mt-2 min-h-[4rem]">
                {reply ? (
                  <Markdown text={reply} className="text-md" />
                ) : (
                  <p className="text-sm text-ink-400">{copy.hero.thinking}</p>
                )}
                {status === "streaming" && reply && (
                  <span
                    aria-hidden="true"
                    className="ml-0.5 inline-block h-4 w-px animate-pulse bg-signal align-middle"
                  />
                )}
              </div>
              {status !== "streaming" && (
                <div className="mt-4 flex flex-wrap items-center gap-4">
                  <p className="text-xs text-ink-400">
                    {status === "live"
                      ? copy.hero.liveNote
                      : copy.hero.sampleNote}
                  </p>
                  <button
                    type="button"
                    onClick={changeSubject}
                    className="text-xs text-ink-500 transition-colors duration-fast hover:text-ink-900"
                  >
                    {copy.hero.change}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* On a phone the figure is small and comes first, at the right, so it
            shares the first screen with the opening line. From md up it takes
            the right column. */}
        <div className="order-first -mb-2 ml-auto w-32 md:order-none md:mx-auto md:mb-0 md:w-full md:max-w-sm">
          <MinoLive size="xl" primary priority className="w-full" />
        </div>
      </section>

      {/* ── the engine ──────────────────────────────────────────────────── */}
      <section className="border-t border-line">
        <div className="mx-auto max-w-6xl px-6 pt-20 md:pt-28">
          <Kicker>{copy.engine.kicker}</Kicker>
          <h2 className="mt-4 max-w-4xl font-display text-3xl text-ink-900 md:text-4xl">
            {copy.engine.title}
          </h2>
        </div>

        <div className="mx-auto max-w-6xl px-6 pb-8 pt-12 md:pt-16">
          <Step id="step-1" register={register} step={stepAt(0)} state={active}>
            <Dialogue
              lines={[
                {
                  who: t.chat.you,
                  text: asked
                    ? `${copy.engine.askExample.replace(/Freud/i, asked)}`
                    : copy.engine.askExample,
                },
              ]}
            />
          </Step>

          <Step id="step-2" register={register} step={stepAt(1)} state={active}>
            <Dialogue
              lines={[
                { who: "Mino", text: copy.engine.probeReply },
                { who: "Mino", text: copy.engine.probeQuestion },
                { who: t.chat.you, text: copy.engine.probeAnswer },
                { who: "Mino", text: copy.engine.probeVerdict },
              ]}
            />
          </Step>

          <Step id="step-3" register={register} step={stepAt(2)} state={active}>
            <ol data-landing-path className="max-w-md">
              {bank.path.map((module, index) => (
                <li
                  key={module}
                  className={`flex items-baseline gap-4 border-t border-line py-3 ${index === 0 ? "text-ink-900" : "text-ink-500"}`}
                >
                  <span className="w-6 shrink-0 font-mono text-xs text-ink-400">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="flex-1 text-base">{module}</span>
                  <span
                    className={`font-mono text-xs ${index === 0 ? "text-signal" : "text-ink-400"}`}
                  >
                    {index === 0 ? copy.engine.pathNow : copy.engine.pathLater}
                  </span>
                </li>
              ))}
            </ol>
          </Step>

          <Step id="step-4" register={register} step={stepAt(3)} state={active}>
            <div className="max-w-md">
              <p className="text-xs text-ink-400">{copy.engine.lessonFrom}</p>
              <Markdown
                text={lessonText}
                className="mt-3 font-serif text-md text-ink-900"
              />
            </div>
          </Step>

          <Step id="step-5" register={register} step={stepAt(4)} state={active}>
            <div className="max-w-md">
              <p className="font-display text-lg text-ink-900">
                {bank.question}
              </p>
              <ul className="mt-4" role="group" aria-label={bank.question}>
                {bank.options.map((option, index) => {
                  const chosen = answer === index;
                  const tone = answered
                    ? index === bank.correct
                      ? "text-positive"
                      : chosen
                        ? "text-critical"
                        : "text-ink-400"
                    : chosen
                      ? "text-signal"
                      : "text-ink-800 hover:text-ink-900";
                  return (
                    <li key={option} className="border-t border-line">
                      <button
                        type="button"
                        onClick={() => pick(index)}
                        aria-pressed={chosen}
                        disabled={answered}
                        className={`flex w-full items-baseline gap-4 py-3 text-left text-base transition-colors duration-fast disabled:cursor-default ${tone}`}
                      >
                        <span
                          aria-hidden="true"
                          className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full border transition-colors duration-fast ${
                            chosen
                              ? "border-current bg-current"
                              : "border-ink-300"
                          }`}
                        />
                        {option}
                      </button>
                    </li>
                  );
                })}
              </ul>
              {answer !== null && !answered && (
                <div className="mt-4 flex items-center gap-3 border-t border-line pt-4">
                  <span className="text-sm text-ink-600">
                    {copy.engine.confident}
                  </span>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => confirm(true)}
                  >
                    {copy.engine.sure}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => confirm(false)}
                  >
                    {copy.engine.unsure}
                  </Button>
                </div>
              )}
              {answered && (
                <p
                  className={`mt-4 border-t border-line pt-4 text-sm font-medium ${correct ? "text-positive" : "text-critical"}`}
                >
                  {correct ? copy.engine.right : copy.engine.wrong}
                </p>
              )}
              {answered && !correct && (
                <p className="mt-2 text-sm text-ink-700">{bank.correction}</p>
              )}
            </div>
          </Step>

          <Step id="step-6" register={register} step={stepAt(5)} state={active}>
            {(() => {
              const moved = answered && !correct;
              const rows = [...bank.concepts]
                .map((c) => ({
                  name: c.name,
                  value: moved ? c.after : c.before,
                }))
                .sort((a, z) => a.value - z.value);
              return (
                <div className="max-w-md">
                  <p className="text-xs text-ink-400">
                    {copy.engine.masteryTitle}
                    {moved && (
                      <span className="text-signal">
                        {" "}
                        · {copy.engine.masteryMoved}
                      </span>
                    )}
                  </p>
                  <ul className="mt-3">
                    {rows.map((row) => (
                      <li key={row.name} className="border-t border-line py-3">
                        <div className="flex items-baseline justify-between gap-4 text-sm">
                          <span className="text-ink-800">{row.name}</span>
                          <span
                            className={`font-mono ${row.value < 40 ? "text-critical" : row.value < 60 ? "text-ink-600" : "text-positive"}`}
                          >
                            {row.value}
                          </span>
                        </div>
                        <div className="mt-2 h-px w-full bg-line">
                          <div
                            className={`h-px transition-[width] duration-slow ease-noema ${
                              row.value < 40
                                ? "bg-critical"
                                : row.value < 60
                                  ? "bg-ink-500"
                                  : "bg-positive"
                            }`}
                            style={{ width: `${row.value}%` }}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 text-xs text-ink-400">
                    {copy.engine.masteryHint}
                  </p>
                </div>
              );
            })()}
          </Step>

          <Step id="step-7" register={register} step={stepAt(6)} state={active}>
            <div className="max-w-md">
              <Speaker>Mino</Speaker>
              <p className="mt-2 font-serif text-md text-ink-900">
                {answered
                  ? correct
                    ? copy.engine.adjustAfterRight
                    : copy.engine.adjustAfterWrong
                  : copy.engine.adjustBefore}
              </p>
            </div>
          </Step>

          <Step id="step-8" register={register} step={stepAt(7)} state={active}>
            <div className="max-w-md">
              <Speaker>Mino</Speaker>
              <p className="mt-2 font-serif text-md text-ink-900">
                {copy.engine.returnWhen(REMEMBERED_DAYS)}
              </p>
              <button
                type="button"
                onClick={() => setFlipped((f) => !f)}
                className="mt-5 w-full text-left [perspective:1400px] focus-visible:outline-none"
                aria-pressed={flipped}
              >
                <div
                  className={`grid transition-transform duration-slow ease-noema [transform-style:preserve-3d] ${
                    flipped ? "[transform:rotateY(180deg)]" : ""
                  }`}
                >
                  <div className="col-start-1 row-start-1 rounded-lg border border-line bg-raised p-6 [backface-visibility:hidden]">
                    <p className="font-serif text-lg text-ink-900">
                      {bank.card.front}
                    </p>
                    <p className="mt-6 text-xs text-ink-400">
                      {copy.engine.returnTap}
                    </p>
                  </div>
                  <div className="col-start-1 row-start-1 rounded-lg border border-signal bg-raised p-6 [backface-visibility:hidden] [transform:rotateY(180deg)]">
                    <p className="text-sm text-ink-500">{bank.card.front}</p>
                    <p className="mt-3 font-serif text-lg text-ink-900">
                      {bank.card.back}
                    </p>
                    <p className="mt-5 text-xs text-ink-500">
                      {copy.engine.returnNext(NEXT_REVIEW_DAYS)}
                    </p>
                  </div>
                </div>
              </button>
            </div>
          </Step>
        </div>
      </section>

      {/* ── versus ──────────────────────────────────────────────────────── */}
      <section
        ref={register("versus")}
        data-section="versus"
        className="border-t border-line"
      >
        <div className="mx-auto max-w-6xl px-6 py-20 md:py-28">
          <h2 className="max-w-3xl font-display text-3xl text-ink-900 md:text-4xl">
            {copy.versus.title}
          </h2>
          <p className="mt-4 max-w-reading text-md text-ink-600">
            {copy.versus.body}
          </p>
          <dl className="mt-12 max-w-4xl">
            {copy.versus.pairs.map(([them, us]) => (
              <div
                key={us}
                className="grid gap-2 border-t border-line py-5 md:grid-cols-2 md:gap-10"
              >
                <dt className="text-base text-ink-500">{them}</dt>
                <dd className="text-base text-ink-900">{us}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ── rhythm ──────────────────────────────────────────────────────── */}
      <section
        ref={register("rhythm")}
        data-section="rhythm"
        className="border-t border-line"
      >
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-20 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:py-28">
          <div className="max-w-reading">
            <Kicker>{copy.rhythm.kicker}</Kicker>
            <h2 className="mt-4 font-display text-3xl text-ink-900">
              {copy.rhythm.title}
            </h2>
            <p className="mt-4 text-md text-ink-600">{copy.rhythm.body}</p>
          </div>
          <div
            data-landing-mode={demoMode}
            className="max-w-md md:justify-self-end"
          >
            <div
              className="flex gap-6 border-b border-line"
              role="tablist"
              aria-label={copy.rhythm.title}
            >
              {(["normal", "focus"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="tab"
                  aria-selected={demoMode === m}
                  onClick={() => setDemoMode(m)}
                  className={`-mb-px border-b-2 py-2 text-sm transition-colors duration-fast ${
                    demoMode === m
                      ? "border-signal text-ink-900"
                      : "border-transparent text-ink-500 hover:text-ink-900"
                  }`}
                >
                  {m === "normal" ? copy.rhythm.normal : copy.rhythm.focus}
                </button>
              ))}
            </div>
            {demoMode === "normal" ? (
              <div className="mt-6">
                <Speaker>Mino</Speaker>
                <Markdown
                  text={lessonText}
                  className="mt-2 font-serif text-md"
                />
              </div>
            ) : (
              (() => {
                const sentences = lessonText
                  .replace(/\*\*/g, "")
                  .split(/(?<=[.!?])\s+/)
                  .filter(Boolean);
                const hook = sentences[0] ?? "";
                const concept = sentences.slice(1, 4);
                return (
                  <ol className="mt-6 space-y-5">
                    <li>
                      <p className="text-xs text-signal">{copy.rhythm.hook}</p>
                      <p className="mt-1 font-display text-lg text-ink-900">
                        {hook}
                      </p>
                    </li>
                    <li>
                      <p className="text-xs text-signal">
                        {copy.rhythm.concept}
                      </p>
                      <ul className="mt-1 space-y-1.5">
                        {concept.map((line) => (
                          <li key={line} className="text-sm text-ink-800">
                            {line}
                          </li>
                        ))}
                      </ul>
                    </li>
                    <li>
                      <p className="text-xs text-signal">
                        {copy.rhythm.interaction}
                      </p>
                      <p className="mt-1 text-sm text-ink-900">
                        {bank.question}
                      </p>
                      <ul className="mt-2 space-y-1">
                        {bank.options.map((o) => (
                          <li key={o} className="text-xs text-ink-600">
                            — {o}
                          </li>
                        ))}
                      </ul>
                    </li>
                    <li>
                      <p className="text-xs text-signal">
                        {copy.rhythm.recall}
                      </p>
                      <p className="mt-1 font-serif text-sm text-ink-900">
                        {bank.card.front}
                      </p>
                    </li>
                  </ol>
                );
              })()
            )}
          </div>
        </div>
      </section>

      {/* ── close ───────────────────────────────────────────────────────── */}
      <section
        ref={register("close")}
        data-section="close"
        className="border-t border-line"
      >
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-24 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:items-center md:py-32">
          <div className="mx-auto w-full max-w-[14rem] md:max-w-xs">
            <MinoLive size="xl" className="w-full" />
          </div>
          <div>
            <h2 className="font-display text-5xl text-ink-900 md:text-6xl">
              {copy.close.title}
            </h2>
            <p className="mt-6 max-w-reading text-md text-ink-600">
              {copy.close.body}
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <ButtonLink
                href={primaryHref}
                variant="primary"
                size="lg"
                onClick={start}
              >
                {signedIn ? copy.nav.continueLearning : copy.close.start}
              </ButtonLink>
              {asked && <span className="text-sm text-ink-500">{asked}</span>}
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-sm text-ink-500">
          <span>{copy.footer.license}</span>
          <nav className="flex items-center gap-4">
            <Link
              href="/privacy"
              className="transition-colors duration-fast hover:text-ink-900"
            >
              {copy.footer.privacy}
            </Link>
            <Link
              href="/terms"
              className="transition-colors duration-fast hover:text-ink-900"
            >
              {copy.footer.terms}
            </Link>
          </nav>
        </div>
      </footer>

      {/* The companion: the same character, small, once the hero has scrolled
          away and until the close brings the large figure back. */}
      <div
        aria-hidden="true"
        className={`pointer-events-none fixed bottom-5 right-5 z-40 h-20 w-20 transition-[opacity,transform] duration-normal ease-noema md:h-24 md:w-24 ${
          active === "ask" || active === "close"
            ? "translate-y-4 opacity-0"
            : "translate-y-0 opacity-100"
        }`}
      >
        <MinoLive size="fill" />
      </div>
    </main>
  );
}

/** A small serif line above a title: the page's only label style. */
function Kicker({ children }: { children: ReactNode }) {
  return <p className="font-display text-lg italic text-signal">{children}</p>;
}

/** Who is speaking, above a line of dialogue. */
function Speaker({ children }: { children: ReactNode }) {
  return <p className="font-mono text-xs text-signal">{children}</p>;
}

function Dialogue({ lines }: { lines: { who: string; text: string }[] }) {
  return (
    <ol className="max-w-md">
      {lines.map((line, index) => (
        <li key={`${index}-${line.text}`} className="border-t border-line py-3">
          <Speaker>{line.who}</Speaker>
          <p
            className={`mt-1 text-md ${line.who === "Mino" ? "text-ink-900" : "font-serif italic text-ink-700"}`}
          >
            {line.text}
          </p>
        </li>
      ))}
    </ol>
  );
}

function Step({
  id,
  register,
  step,
  state,
  children,
}: {
  id: Section;
  register: (id: string) => (element: Element | null) => void;
  step: { n: string; title: string; body: string };
  state: string;
  children: ReactNode;
}) {
  const here = state === id;
  return (
    <section
      ref={register(id)}
      data-section={id}
      data-here={here || undefined}
      className="grid gap-6 border-t border-line py-12 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:gap-12 md:py-16"
    >
      <div className="max-w-reading">
        <span
          aria-hidden="true"
          className={`font-display text-3xl transition-colors duration-slow ease-noema ${here ? "text-signal" : "text-ink-300"}`}
        >
          {step.n}
        </span>
        <h3 className="mt-2 font-display text-2xl text-ink-900">
          {step.title}
        </h3>
        <p className="mt-3 text-md text-ink-600">{step.body}</p>
      </div>
      <div className="md:pt-3">{children}</div>
    </section>
  );
}
