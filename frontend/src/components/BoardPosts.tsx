import type { TicketDetails } from "../api";
import { AGENT_BY_ROLE } from "../agents";
import AgentIcon from "./AgentIcon";

const KIND_LABEL = {
  customer_draft: "Customer draft · not sent",
  vendor_draft: "Vendor / landlord draft · not sent",
  internal_note: "Team note",
  decision: "Boss's decision",
  escalation: "Needs a human",
};

export default function BoardPosts({ details }: { details: TicketDetails | null }) {
  const posts = details?.board_posts ?? [];
  return (
    <div className="card">
      <h2>On the board {details && <span className="muted-h">· #{details.ticket.id}</span>}</h2>
      {!posts.length && <p className="muted">Drafts, notes and decisions for this ticket will pin here. Nothing is ever emailed.</p>}
      <div className="posts">
        {posts.map((p) => {
          const a = AGENT_BY_ROLE[p.author_role];
          return (
            <div key={p.id} className={`post ${p.kind}`} style={{ "--c": a?.color, "--d": a?.deep } as React.CSSProperties}>
              <div className="post-head">
                <span className="mini-avatar">{a && <AgentIcon role={a.role} label={a.name} />}</span>
                <b>{a?.name ?? p.author_role}</b>
                <span className="post-kind">{KIND_LABEL[p.kind] ?? p.kind}</span>
              </div>
              <div className="post-body">{p.content}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
