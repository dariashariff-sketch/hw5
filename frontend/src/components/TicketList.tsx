import type { Ticket } from "../api";
import { prettyStatus } from "../agents";

interface Props {
  tickets: Ticket[];
  selected: number | null;
  onSelect: (id: number) => void;
  onStart: (id: number) => void;
  anyRunning: boolean;
}

const TYPE_LABEL: Record<string, string> = {
  customer_order: "Customer order",
  rent_notice: "Rent notice",
  price_override: "Discount request",
};

export default function TicketList({ tickets, selected, onSelect, onStart, anyRunning }: Props) {
  return (
    <div className="card">
      <h2>Ticket board</h2>
      <div className="tickets">
        {tickets.map((t) => {
          const isSel = t.id === selected;
          return (
            <div
              key={t.id}
              className={`ticket ${isSel ? "selected" : ""} ${t.state} ${t.agents_running ? "running" : ""}`}
              onClick={() => onSelect(t.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onSelect(t.id)}
            >
              <div className="ticket-top">
                <span className="ticket-id">#{t.id}</span>
                <span className="type">{TYPE_LABEL[t.type] ?? prettyStatus(t.type)}</span>
                {t.agents_running ? (
                  <span className="pill working">team working<span className="dots"><i /><i /><i /></span></span>
                ) : (
                  <span className={`pill ${t.state}`}>{t.state}</span>
                )}
              </div>
              <div className="ticket-subject">{t.subject}</div>
              <div className="ticket-meta">
                from <b>{t.requester}</b>
                {t.status !== "open" && t.status !== "resolved" && <> &middot; {prettyStatus(t.status)}</>}
              </div>
              {t.state === "resolved" && !t.agents_running && <div className="stamp small">Resolved</div>}
              {isSel && t.state === "open" && !t.agents_running && (
                <button
                  className="candy-btn"
                  disabled={anyRunning}
                  onClick={(e) => { e.stopPropagation(); onStart(t.id); }}
                  title={anyRunning ? "Wait for the current run to finish" : "Boss reads it first and calls only the teammates it needs"}
                >
                  Start the team
                </button>
              )}
            </div>
          );
        })}
        {!tickets.length && <p className="muted">Loading tickets…</p>}
      </div>
    </div>
  );
}
