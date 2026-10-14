import { useEffect, useRef } from "react";
import type { AgentEvent, Role } from "../api";
import { AGENT_BY_ROLE, TOOL_LABELS } from "../agents";
import AgentIcon from "./AgentIcon";

interface Props {
  events: AgentEvent[];
  running: boolean;
}

interface Line {
  key: string;
  role: Role;
  kind: "said" | "tool" | "ask" | "done" | "error" | "start" | "refused";
  text: string;
  sub?: string;
}

const hasError = (c: unknown) => typeof c === "object" && c !== null && "error" in c;

function toLines(events: AgentEvent[]): Line[] {
  const lines: Line[] = [];
  for (const e of events) {
    if (e.agent === "human") continue;
    const role = e.agent;
    const k = `${e.seq}`;
    if (e.event === "run_start" && e.chain.length === 1) {
      lines.push({ key: k, role, kind: "start", text: "picked up the ticket" });
    } else if (e.event === "delegate" && e.to) {
      const ask = e.said[0]?.replace(/^Asked [a-z_]+: /, "") ?? "";
      lines.push({ key: k, role, kind: "ask", text: `asked ${AGENT_BY_ROLE[e.to]?.name}`, sub: ask });
    } else if (e.event === "model_response") {
      e.said.forEach((s, i) => lines.push({ key: `${k}-s${i}`, role, kind: "said", text: s }));
      e.tool_calls
        .filter((c) => c.tool !== "ask_teammate")
        .forEach((c, i) =>
          lines.push({ key: `${k}-t${i}`, role, kind: "tool", text: TOOL_LABELS[c.tool] ?? c.tool, sub: c.tool }),
        );
    } else if (e.event === "model_request") {
      e.tool_results
        .filter((r) => hasError(r.content))
        .forEach((r, i) =>
          lines.push({
            key: `${k}-r${i}`, role, kind: "refused", text: `${r.tool} said no`,
            sub: String((r.content as { error: unknown }).error),
          }),
        );
    } else if (e.event === "run_end") {
      const out = e.output ?? {};
      const text = String(out.decision ?? out.summary ?? "finished");
      lines.push({ key: k, role, kind: "done", text: role === "boss" ? "made the final call" : "sent their report", sub: text });
    } else if (e.event === "error") {
      lines.push({ key: k, role, kind: "error", text: "stopped", sub: String(e.detail?.message ?? "") });
    }
  }
  return lines;
}

export default function LiveFeed({ events, running }: Props) {
  const lines = toLines(events);
  const box = useRef<HTMLDivElement>(null);
  // keep the newest line in view without scrolling the whole page
  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [lines.length]);

  return (
    <div className="card feed-card">
      <div className="section-head">
        <h2>Live feed</h2>
        {running && <span className="pill working">live<span className="dots"><i /><i /><i /></span></span>}
      </div>
      <div className="feed" ref={box}>
        {!lines.length && <p className="muted">Pick a ticket and press <b>Start the team</b> to watch the agents work.</p>}
        {lines.map((l) => {
          const a = AGENT_BY_ROLE[l.role];
          return (
            <div key={l.key} className={`line ${l.kind}`} style={{ "--c": a.color, "--d": a.deep } as React.CSSProperties}>
              <span className="mini-avatar"><AgentIcon role={a.role} label={a.name} /></span>
              <div className="line-body">
                <div className="line-head"><b>{a.name}</b> {l.kind !== "said" && <span>{l.text}</span>}</div>
                {l.kind === "said" && <div className="said">{l.text}</div>}
                {l.sub && l.kind === "tool" && l.sub !== "final_result" && <code>{l.sub}</code>}
                {l.sub && l.kind !== "tool" && <div className="sub">{l.sub}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
