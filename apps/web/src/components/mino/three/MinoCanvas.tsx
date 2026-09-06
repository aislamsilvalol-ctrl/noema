"use client";

/**
 * The 3D Mino, made safe for a page.
 *
 * Loads the WebGL stage only on the client and only once it is near the
 * viewport; pauses the frame loop while it is off screen or the tab is
 * hidden; picks a pixel ratio from the device; and falls back to the
 * rendered still when WebGL is unavailable or the device asked for data
 * saving. Until the stage has drawn its first frame the still stands in,
 * so nothing shifts or flashes.
 */

import dynamic from "next/dynamic";
import { Component, useEffect, useRef, useState, type ReactNode } from "react";
import { MINO_RENDERS, type MinoRenderPose } from "@/brand/mino";
import type { Pose } from "@/components/mino/machine";
import type { Framing } from "./MinoStage";

const Stage = dynamic(() => import("./MinoStage").then((m) => m.MinoStage), {
  ssr: false,
});

/** A GL failure (context lost, a driver that lies about WebGL) leaves the still in place. */
class StageBoundary extends Component<
  { children: ReactNode; onFail: () => void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onFail();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export type Tier = "high" | "medium" | "low" | "reduced";

let webglChecked: boolean | null = null;
export function hasWebGL(): boolean {
  if (webglChecked !== null) return webglChecked;
  try {
    const c = document.createElement("canvas");
    webglChecked = !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    webglChecked = false;
  }
  return webglChecked;
}

function saveData(): boolean {
  const nav = navigator as Navigator & { connection?: { saveData?: boolean } };
  return nav.connection?.saveData === true;
}

export function MinoCanvas({
  pose,
  blink = 0,
  tier = "high",
  framing = "full",
  still = "idle",
  priority = false,
  className = "",
}: {
  pose: Pose;
  blink?: number;
  tier?: Tier;
  framing?: Framing;
  /** The render shown before the stage is ready and when it cannot run. */
  still?: MinoRenderPose;
  /** Mount the stage immediately instead of waiting for the viewport. */
  priority?: boolean;
  className?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<"still" | "stage">("still");
  const [ready, setReady] = useState(false);
  const [near, setNear] = useState(priority);
  const [onScreen, setOnScreen] = useState(priority);
  const [visibleTab, setVisibleTab] = useState(true);

  useEffect(() => {
    if (tier === "low" || !hasWebGL() || saveData()) return;
    setMode("stage");
  }, [tier]);

  useEffect(() => {
    const el = host.current;
    if (!el || typeof IntersectionObserver !== "function") {
      setNear(true);
      setOnScreen(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          setOnScreen(e.isIntersecting);
          if (e.isIntersecting) setNear(true);
        }
      },
      { rootMargin: "240px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    const update = () => setVisibleTab(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);

  const motion = tier !== "reduced";
  const dpr: [number, number] = tier === "high" ? [1, 1.75] : [1, 1.25];
  const showStage = mode === "stage" && near;

  return (
    <div
      ref={host}
      className={`relative ${className}`}
      data-mino-stage={showStage ? (ready ? "live" : "loading") : "still"}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- a plain still; next/image adds nothing here */}
      <img
        src={MINO_RENDERS[still]}
        alt=""
        draggable={false}
        aria-hidden="true"
        className={`block h-auto w-full select-none transition-opacity duration-slow ease-noema ${
          showStage && ready ? "opacity-0" : "opacity-100"
        }`}
      />
      {showStage && (
        <div
          className={`absolute inset-0 transition-opacity duration-slow ease-noema ${ready ? "opacity-100" : "opacity-0"}`}
        >
          <StageBoundary
            onFail={() => {
              setMode("still");
              setReady(false);
            }}
          >
            <Stage
              pose={pose}
              blink={blink}
              active={onScreen && visibleTab}
              motion={motion}
              framing={framing}
              dpr={dpr}
              fps={tier === "high" ? 30 : 24}
              onReady={() => setReady(true)}
            />
          </StageBoundary>
        </div>
      )}
    </div>
  );
}
