import type { Role, Ticket } from "../api";
import { AGENTS, AGENT_BY_ROLE } from "../agents";
import type { AgentState } from "../agents";
import AgentIcon from "./AgentIcon";

interface Props {
  states: Record<Role, AgentState>;
  ticket: Ticket | null;
  tokensUsed: number;
  tokenCap: number;
  hasRun: boolean;
}

const STATUS_TEXT = { idle: "not called", working: "working", waiting: "waiting", done: "done" } as const;

export default function TeamRoom({ states, ticket, tokensUsed, tokenCap, hasRun }: Props) {
  const pct = Math.min(100, (tokensUsed / tokenCap) * 100);
  const called = AGENTS.filter((a) => states[a.role].status !== "idle").length;
  // speech bubbles only while someone is working or waiting; "done" is already on the chip
  const bubbleFor = (st: AgentState) =>
    st.status === "working" || st.status === "waiting" ? (st.lastSaid ?? st.doing) : null;
  const anyBubble = AGENTS.some((a) => bubbleFor(states[a.role]));
  return (
    <div className="card team-room">
      <div className="section-head">
        <h2>Team room {ticket && <span className="muted-h">· ticket #{ticket.id}</span>}</h2>
        {called > 0 && <span className="pill soft">{called} of 5 teammates on this ticket</span>}
      </div>

      <div className="agents">
        {AGENTS.map((a) => {
          const s = states[a.role];
          const bubble = bubbleFor(s);
          return (
            <div key={a.role} className={`agent ${hasRun ? s.status : "ready"}`} style={{ "--c": a.color, "--d": a.deep } as React.CSSProperties}>
              {anyBubble && (
                <div className="bubble-slot">
                  {bubble && <div className="bubble" title={bubble}>{bubble}</div>}
                </div>
              )}
              <div className="avatar">
                <AgentIcon role={a.role} label={a.name} />
                {s.status === "working" && <i className="pulse" />}
              </div>
              <div className="agent-name">{a.name}</div>
              <div className="agent-job">{a.job}</div>
              <span className={`status-chip ${s.status}`}>
                {hasRun ? STATUS_TEXT[s.status] : "ready"}
                {s.status === "waiting" && s.waitingOn && <> on {AGENT_BY_ROLE[s.waitingOn]?.name}</>}
              </span>
            </div>
          );
        })}
      </div>

      <div className="meter" title="Tokens used on this ticket out of its budget">
        <div className="meter-label">
          <span>Token budget</span>
          <span><b>{tokensUsed.toLocaleString()}</b> / {tokenCap.toLocaleString()}</span>
        </div>
        <div className="meter-track"><div className="meter-fill" style={{ width: `${pct}%` }} /></div>
      </div>
    </div>
  );
}
