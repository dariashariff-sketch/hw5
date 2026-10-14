import { useRef, useState } from "react";
import { api, ApiError } from "../api";
import type { Approval } from "../api";
import { AGENT_BY_ROLE, money } from "../agents";
import type { Role } from "../api";

interface Props {
  approvals: Approval[];
  approver: string;
  onApproved: (msg: string) => void;
  onMessage: (msg: string) => void;
}

const KIND_LABEL = { invoice: "Pay vendor invoice", rent: "Pay rent", purchase_order: "Restock purchase order" };
const HOLD_MS = 1200;

export default function Approvals({ approvals, approver, onApproved, onMessage }: Props) {
  return (
    <div className="card approvals">
      <div className="section-head">
        <h2>Needs your OK</h2>
        {approvals.length > 0 && <span className="pill count">{approvals.length}</span>}
      </div>
      {!approvals.length && <p className="muted">Nothing waiting. The agents can only prepare payments, so they'll show up here for you.</p>}
      {approvals.map((a) => (
        <ApprovalCard key={a.id} a={a} approver={approver} onApproved={onApproved} onMessage={onMessage} />
      ))}
    </div>
  );
}

function ApprovalCard({ a, approver, onApproved, onMessage }: { a: Approval } & Omit<Props, "approvals">) {
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState<"idle" | "holding" | "sending" | "stamped" | "refused">("idle");
  const [refusal, setRefusal] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const raf = useRef(0);
  const started = useRef(0);
  const who = approver.trim();
  const requester = AGENT_BY_ROLE[a.requested_by as Role]?.name ?? a.requested_by;

  const approve = async () => {
    setPhase("sending");
    try {
      const r = await api.approve(a.id, who);
      setPhase("stamped");
      setTimeout(() => onApproved(`Paid ${money(Number(r.amount))} · checking is now ${money(Number(r.new_balance))}`), 1300);
    } catch (err) {
      setPhase("refused");
      setProgress(0);
      setRefusal(err instanceof ApiError ? err.message : "Approval failed");
    }
  };

  const down = () => {
    if (!who || phase === "sending" || phase === "stamped") return;
    setPhase("holding");
    setRefusal(null);
    started.current = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - started.current) / HOLD_MS);
      setProgress(p);
      if (p < 1) raf.current = requestAnimationFrame(tick);
      else approve();
    };
    raf.current = requestAnimationFrame(tick);
  };

  const up = () => {
    cancelAnimationFrame(raf.current);
    if (phase === "holding") { setPhase("idle"); setProgress(0); }
  };

  const reject = async () => {
    try {
      await api.reject(a.id, who, reason.trim() || "Declined on the dashboard");
      onMessage(`Declined: ${KIND_LABEL[a.kind]} for ticket ${a.ticket_id}`);
    } catch (err) {
      setRefusal(err instanceof ApiError ? err.message : "Couldn't decline");
    }
  };

  return (
    <div className={`approval ${phase}`}>
      <div className="approval-top">
        <span className="kind">{KIND_LABEL[a.kind]}</span>
        <span className="amount">{money(a.amount)}</span>
      </div>
      <div className="small muted">ticket #{a.ticket_id} &middot; prepared by {requester} &middot; request #{a.id}</div>
      <p className="small reason">{a.reason}</p>

      {refusal && <div className="refusal small"><b>The pay tool said no:</b> {refusal}</div>}

      <div className="approval-actions">
        <button
          className="hold-btn"
          style={{ "--p": progress } as React.CSSProperties}
          disabled={!who || phase === "sending" || phase === "stamped"}
          onPointerDown={down}
          onPointerUp={up}
          onPointerLeave={up}
          title={who ? "Press and hold to approve" : "Type your name at the top first"}
        >
          <span className="hold-fill" />
          <span className="hold-text">
            {phase === "holding" ? "keep holding…" : phase === "sending" ? "paying…" : who ? "Hold to approve" : "Add your name above"}
          </span>
        </button>
        <button className="link-btn" disabled={!who} onClick={() => setRejecting((r) => !r)}>decline</button>
      </div>
      {rejecting && (
        <div className="reject-row">
          <input placeholder="reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
          <button className="ghost-btn small" onClick={reject}>Decline request</button>
        </div>
      )}
      {phase === "stamped" && <div className="stamp">Approved<small>{who}</small></div>}
    </div>
  );
}
