import type { Role } from "../api";
import { AGENTS, prettyStatus } from "../agents";
import type { AgentState } from "../agents";
import AgentIcon from "./AgentIcon";

interface Props {
  states: Record<Role, AgentState>;
  hasRun: boolean;
}

export default function AgentSummary({ states, hasRun }: Props) {
  return (
    <div className="card">
      <h2>Who did what</h2>
      {!hasRun && <p className="muted">After a run, each teammate's work shows up here.</p>}
      {hasRun && (
        <div className="summaries">
          {AGENTS.map((a) => {
            const s = states[a.role];
            const out = s.output ?? {};
            const tools = Object.entries(s.toolsUsed).filter(([t]) => t !== "final_result");
            const text = String(out.decision ?? out.summary ?? (s.status === "idle" ? "" : s.doing ?? ""));
            return (
              <div key={a.role} className={`summary ${s.status}`} style={{ "--c": a.color, "--d": a.deep } as React.CSSProperties}>
                <div className="summary-head">
                  <span className="mini-avatar"><AgentIcon role={a.role} label={a.name} /></span>
                  <b>{a.name}</b>
                  {a.role === "boss" && typeof out.final_status === "string" && (
                    <span className="pill soft">{prettyStatus(out.final_status)}</span>
                  )}
                </div>
                {s.status === "idle" ? (
                  <p className="muted small">Not called on this ticket. Boss kept them free.</p>
                ) : (
                  <>
                    <p className="small">{text}</p>
                    {Array.isArray(out.actions_taken) && out.actions_taken.length > 0 && (
                      <ul className="small">{(out.actions_taken as string[]).map((x, i) => <li key={i}>{x}</li>)}</ul>
                    )}
                    {tools.length > 0 && (
                      <div className="chips">{tools.map(([t, n]) => <code key={t}>{t}{n > 1 ? ` ×${n}` : ""}</code>)}</div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
