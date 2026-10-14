import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, API_URL } from "./api";
import type { AgentEvent, Approval, Cash, TicketDetails, TicketsResponse } from "./api";
import { agentStates } from "./agents";
import Header from "./components/Header";
import TicketList from "./components/TicketList";
import TeamRoom from "./components/TeamRoom";
import LiveFeed from "./components/LiveFeed";
import AgentSummary from "./components/AgentSummary";
import CashCard from "./components/CashCard";
import Approvals from "./components/Approvals";
import BoardPosts from "./components/BoardPosts";
import Hearts from "./components/Hearts";
import CashTimeline from "./components/CashTimeline";
import ThemeToggle from "./components/ThemeToggle";

const FAST_POLL_MS = 1200; // while agents are working
const SLOW_POLL_MS = 4000;
const TICKET_TOKEN_CAP = 150_000; // matches backend/config.py

export default function App() {
  const [tickets, setTickets] = useState<TicketsResponse | null>(null);
  const [cash, setCash] = useState<Cash | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [selected, setSelected] = useState<number | null>(
    () => Number(new URLSearchParams(location.search).get("ticket")) || null, // e.g. ?ticket=102
  );
  const [details, setDetails] = useState<TicketDetails | null>(null);
  const [offline, setOffline] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [hearts, setHearts] = useState(0); // bump to throw a heart burst
  const [approver, setApprover] = useState(() => localStorage.getItem("cc-approver") ?? "");
  const lastSeq = useRef<number | null>(null);
  const wasRunning = useRef<Set<number>>(new Set());

  const anyRunning = !!tickets?.tickets.some((t) => t.agents_running);

  const refresh = useCallback(async () => {
    try {
      const [t, c, a, ev] = await Promise.all([
        api.tickets(), api.cash(), api.approvals(), api.events(lastSeq.current),
      ]);
      setOffline(false);
      setTickets(t);
      setCash(c);
      setApprovals(a.pending);
      if (ev.events.length) {
        // two overlapping refreshes can return the same events: keep each seq once
        setEvents((prev) => {
          const seen = new Set(prev.map((e) => e.seq));
          return [...prev, ...ev.events.filter((e) => !seen.has(e.seq))];
        });
        lastSeq.current = Math.max(lastSeq.current ?? -1, ev.last_seq ?? -1);
      } else if (lastSeq.current === null) {
        lastSeq.current = -1;
      }
      // celebrate a ticket that just finished
      for (const tk of t.tickets) {
        if (wasRunning.current.has(tk.id) && !tk.agents_running) {
          wasRunning.current.delete(tk.id);
          if (tk.state === "resolved") {
            setToast(`Ticket ${tk.id} resolved by the team`);
            setHearts((h) => h + 1);
          } else {
            setToast(`The team stopped on ticket ${tk.id} — it needs a human look`);
          }
        }
        if (tk.agents_running) wasRunning.current.add(tk.id);
      }
      setSelected((s) => s ?? t.tickets[0]?.id ?? null);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, anyRunning ? FAST_POLL_MS : SLOW_POLL_MS);
    return () => clearInterval(id);
  }, [refresh, anyRunning]);

  useEffect(() => {
    if (selected === null) return;
    let live = true;
    const load = () => api.ticket(selected).then((d) => live && setDetails(d)).catch(() => {});
    load();
    const id = setInterval(load, anyRunning ? FAST_POLL_MS : SLOW_POLL_MS);
    return () => { live = false; clearInterval(id); };
  }, [selected, anyRunning]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 3800);
    return () => clearTimeout(id);
  }, [toast]);

  const saveApprover = (name: string) => {
    setApprover(name);
    localStorage.setItem("cc-approver", name);
  };

  // events of the latest run on the selected ticket
  const runEvents = useMemo(() => {
    const mine = events.filter((e) => e.ticket_id === selected && e.agent !== "human");
    const starts = mine.filter((e) => e.event === "run_start" && e.agent === "boss" && e.chain.length === 1);
    const runId = starts.length ? starts[starts.length - 1].run_id : null;
    return runId ? mine.filter((e) => e.run_id === runId) : [];
  }, [events, selected]);

  const states = useMemo(() => agentStates(runEvents), [runEvents]);
  const ticket = tickets?.tickets.find((t) => t.id === selected) ?? null;
  const tokensUsed = runEvents.reduce((m, e) => Math.max(m, e.total_tokens ?? 0), 0);

  const startTeam = async (id: number) => {
    try {
      await api.run(id);
      setSelected(id);
      wasRunning.current.add(id);
      setToast(`Boss picked up ticket ${id}`);
      refresh();
    } catch (err) {
      setToast(err instanceof ApiError ? err.message : "Couldn't start the team");
    }
  };

  const reset = async () => {
    if (!confirm("Reset the shop database to the original values? This clears all approvals and payments.")) return;
    try {
      await api.reset();
      setToast("Fresh start: the database is back to the original");
      setDetails(null);
      refresh();
    } catch (err) {
      setToast(err instanceof ApiError ? err.message : "Reset failed");
    }
  };

  return (
    <>
      <ThemeToggle />
      <Header
        shopToday={tickets?.shop_today}
        openCount={tickets?.open_count}
        resolvedCount={tickets?.resolved_count}
        approver={approver}
        onApprover={saveApprover}
        onReset={reset}
        resetDisabled={anyRunning}
      />

      {offline && (
        <div className="offline">
          Can't reach the backend at <code>{API_URL}</code>. Start it from <code>backend/</code> with{" "}
          <code>uvicorn main:app --reload --port 8000</code>.
        </div>
      )}

      <main className="desk">
        <aside className="col-left">
          <TicketList
            tickets={tickets?.tickets ?? []}
            selected={selected}
            onSelect={setSelected}
            onStart={startTeam}
            anyRunning={anyRunning}
          />
          <CashCard cash={cash} />
        </aside>

        <section className="col-main">
          <TeamRoom states={states} ticket={ticket} tokensUsed={tokensUsed} tokenCap={TICKET_TOKEN_CAP} hasRun={runEvents.length > 0} />
          <CashTimeline cash={cash} pending={approvals} />
          <div className="two-up">
            <LiveFeed events={runEvents} running={!!ticket?.agents_running} />
            <AgentSummary states={states} hasRun={runEvents.length > 0} />
          </div>
        </section>

        <aside className="col-right">
          <Approvals
            approvals={approvals}
            approver={approver}
            onApproved={(msg) => { setToast(msg); setHearts((h) => h + 1); refresh(); }}
            onMessage={(msg) => { setToast(msg); refresh(); }}
          />
          <BoardPosts details={details} />
        </aside>
      </main>

      <footer>made with &#9825; by the Campus Customs team</footer>
      {toast && <div className="toast">{toast}</div>}
      <Hearts trigger={hearts} />
    </>
  );
}
