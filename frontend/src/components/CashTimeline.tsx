import { useState } from "react";
import type { Approval, Cash } from "../api";
import { money } from "../agents";

interface Point {
  label: string;
  value: number; // checking balance after this step
  change: number; // negative = cash out
  who?: string;
  projected?: boolean;
}

const KIND = { invoice: "invoice", rent: "rent", purchase_order: "PO" } as Record<string, string>;
const W = 760, H = 200, PAD = { l: 56, r: 24, t: 26, b: 46 };

/** Checking balance step by step: every human-approved payment, then (dashed) what
 *  would happen if every pending request were approved too. One series, one axis. */
export default function CashTimeline({ cash, pending }: { cash: Cash | null; pending: Approval[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  if (!cash) return null;

  const paid = [...cash.payments].sort((a, b) => a.id - b.id);
  const start = cash.balance + paid.reduce((s, p) => s + p.amount, 0);
  const points: Point[] = [{ label: "start", value: start, change: 0 }];
  let bal = start;
  for (const p of paid) {
    bal -= p.amount;
    points.push({ label: `${KIND[p.kind] ?? p.kind} #${p.ref_id}`, value: bal, change: -p.amount, who: p.approved_by });
  }
  const actualCount = points.length;
  for (const a of [...pending].sort((x, y) => x.id - y.id)) {
    bal -= a.amount;
    points.push({ label: `${KIND[a.kind] ?? a.kind} #${a.ref_id}?`, value: bal, change: -a.amount, projected: true });
  }

  const max = Math.max(start, 1);
  const min = Math.min(0, ...points.map((p) => p.value));
  const x = (i: number) => PAD.l + (points.length === 1 ? 0 : (i * (W - PAD.l - PAD.r)) / (points.length - 1));
  const y = (v: number) => PAD.t + ((max - v) * (H - PAD.t - PAD.b)) / (max - min || 1);
  const step = (from: number, to: number) =>
    points.slice(from, to).reduce((d, p, i) => {
      const k = from + i;
      return i === 0 ? `M${x(k)},${y(p.value)}` : `${d} H${x(k)} V${y(p.value)}`;
    }, "");
  const actualPath = step(0, actualCount);
  const projPath = points.length > actualCount ? step(actualCount - 1, points.length) : "";
  const areaPath = `${actualPath} V${y(min < 0 ? 0 : min)} H${x(0)} Z`;
  const ticks = [0, max / 2, max];
  const last = points[actualCount - 1];
  const lastProj = points[points.length - 1];
  const hovered = hover === null ? null : points[hover];

  return (
    <div className="card timeline-card">
      <div className="section-head">
        <h2>Cash timeline</h2>
        <span className="pill soft">checking, step by step</span>
      </div>
      <div className="timeline">
        {table ? (
          <table>
            <thead><tr><th>Step</th><th>Change</th><th>Balance</th><th>Approved by</th></tr></thead>
            <tbody>
              {points.map((p, i) => (
                <tr key={i}>
                  <td>{p.projected ? `${p.label.replace("?", "")} (pending)` : p.label}</td>
                  <td className="num">{p.change ? `−${money(-p.change)}` : "–"}</td>
                  <td className="num">{money(p.value)}</td>
                  <td>{p.projected ? "waiting on you" : p.who ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <>
            <svg viewBox={`0 0 ${W} ${H}`} role="img"
              aria-label={`Checking balance went from ${money(start)} to ${money(last.value)}${points.length > actualCount ? `, ${money(lastProj.value)} if all pending requests are approved` : ""}.`}>
              {ticks.map((t) => (
                <g key={t}>
                  <line className="grid" x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} />
                  <text className="axis-text" x={PAD.l - 8} y={y(t) + 4} textAnchor="end">{money(Math.round(t))}</text>
                </g>
              ))}
              {min < 0 && <line className="zero" x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} />}
              <path className="area" d={areaPath} />
              <path className="line" d={actualPath} />
              {projPath && <path className="projection" d={projPath} />}
              {points.map((p, i) => (
                <circle key={i} className={`dot ${p.projected ? "proj" : ""}`} cx={x(i)} cy={y(p.value)} r={hover === i ? 6 : 4.5} />
              ))}
              <text className="label" x={x(actualCount - 1)} y={y(last.value) - 12} textAnchor={actualCount === points.length && actualCount > 1 ? "end" : "middle"}>
                {money(last.value)}
              </text>
              {points.length > actualCount && (
                <text className="label proj" x={x(points.length - 1) - 10}
                  y={lastProj.value < 0 ? y(lastProj.value) + 20 : y(lastProj.value) - 12} textAnchor="end">
                  {money(lastProj.value)} if all approved
                </text>
              )}
              {points.map((p, i) => (
                <text key={`x${i}`} className="axis-text" x={x(i)} y={H - 4} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}>
                  {p.label}
                </text>
              ))}
              {points.map((_, i) => {
                const half = points.length > 1 ? (W - PAD.l - PAD.r) / (points.length - 1) / 2 : 40;
                return (
                  <rect key={`h${i}`} className="hit" x={x(i) - half} y={0} width={half * 2} height={H}
                    onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
                );
              })}
            </svg>
            {hovered && hover !== null && (
              <div className="tip" style={{ left: `${(x(hover) / W) * 100}%`, top: `${(y(hovered.value) / H) * 100}%` }}>
                <b>{money(hovered.value)}</b>
                <span>
                  {hovered.change ? `−${money(-hovered.change)} · ` : "starting balance"}
                  {hovered.projected ? "pending, not paid" : hovered.who ? `approved by ${hovered.who}` : ""}
                </span>
              </div>
            )}
          </>
        )}
      </div>
      <div className="timeline-foot">
        <div>
          <span className="key"><i /> paid (human approved)</span>
          {points.length > actualCount && <span className="key"><i className="dash" /> if pending get approved</span>}
        </div>
        <button className="link-btn" onClick={() => setTable((t) => !t)}>{table ? "show chart" : "show as table"}</button>
      </div>
      {lastProj.value < 0 && (
        <p className="warn small">The dashed line dips below $0. The pay tool refuses whichever request would make checking negative.</p>
      )}
    </div>
  );
}
