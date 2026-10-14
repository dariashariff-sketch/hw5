import { useEffect, useRef, useState } from "react";
import type { Cash } from "../api";
import { money } from "../agents";

const cents = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Counts smoothly from the old value to the new one. */
function useCountTo(target: number | undefined, ms = 1400) {
  const [value, setValue] = useState(target ?? 0);
  const from = useRef(target ?? 0);
  useEffect(() => {
    if (target === undefined) return;
    const start = performance.now();
    const begin = from.current;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(begin + (target - begin) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return value;
}

export default function CashCard({ cash }: { cash: Cash | null }) {
  const shown = useCountTo(cash?.balance);
  const prev = useRef<number | null>(null);
  const [drop, setDrop] = useState<{ amount: number; key: number } | null>(null);

  useEffect(() => {
    if (!cash) return;
    if (prev.current !== null && cash.balance < prev.current) {
      setDrop({ amount: prev.current - cash.balance, key: Date.now() });
    }
    prev.current = cash.balance;
  }, [cash]);

  return (
    <div className="card cash-card">
      <h2>Checking</h2>
      <div className="balance-wrap">
        <div className="balance">{cash ? cents(shown) : "…"}</div>
        {drop && (
          <div key={drop.key} className="drop">
            −{money(drop.amount)}
            <span className="coins"><i /><i /><i /><i /><i /></span>
          </div>
        )}
      </div>
      {cash && (
        <>
          <div className="cash-rows">
            <div><span>Waiting for approval</span><b>{money(cash.pending_approvals_total)}</b></div>
            <div className={cash.balance_if_all_pending_paid < 0 ? "neg" : ""}>
              <span>If you approve everything</span><b>{money(cash.balance_if_all_pending_paid)}</b>
            </div>
          </div>
          {cash.balance_if_all_pending_paid < 0 && (
            <p className="warn small">Not enough cash for every request. The pay tool will refuse the last one.</p>
          )}
          {cash.payments.length > 0 && (
            <ul className="payments small">
              {cash.payments.map((p) => (
                <li key={p.id}>
                  <span>{p.kind.replace("_", " ")} #{p.ref_id}</span>
                  <b>−{money(p.amount)}</b>
                  <em>by {p.approved_by}</em>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small">No revenue is modeled. Cash only goes out, and only when a human approves.</p>
        </>
      )}
    </div>
  );
}
