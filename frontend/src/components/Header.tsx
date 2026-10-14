interface Props {
  shopToday?: string;
  openCount?: number;
  resolvedCount?: number;
  approver: string;
  onApprover: (name: string) => void;
  onReset: () => void;
  resetDisabled: boolean;
}

export default function Header({ shopToday, openCount, resolvedCount, approver, onApprover, onReset, resetDisabled }: Props) {
  return (
    <header className="top">
      <div className="tv">
        <div className="screen">
          <div className="kicker">&#9825; Campus Customs Multi-Agent Operations &#9825;</div>
          <span className="title-tag">Agent Desk</span>
          <div className="sub">
            Shop date <b>{shopToday ?? "…"}</b> &middot; <b>{openCount ?? "–"}</b> open &middot;{" "}
            <b>{resolvedCount ?? "–"}</b> resolved &middot; Model <code>openai-gpt-luna-6</code> via Portkey
          </div>
        </div>
        <div className="knobs"><i /><i /><i /><i /></div>
      </div>

      <div className="dock">
        <label className="approver">
          <span>You're approving as</span>
          <input
            value={approver}
            placeholder="type your name"
            onChange={(e) => onApprover(e.target.value)}
            maxLength={40}
          />
        </label>
        <button className="ghost-btn" onClick={onReset} disabled={resetDisabled} title="Copy the original database over the working copy">
          Reset database
        </button>
      </div>
    </header>
  );
}
