"""Campus Customs MCP server.

The single shop-tools layer for the Campus Customs Multi-Agent Operations team.
Every agent reads and writes shop data only through these tools. All tools work on
the working copy data/campus_customs_new.db; the original data/campus_customs.db is
never opened here.

Rules enforced in this file (not just in prompts):
- Facts come from database rows only. Missing rows return an error, never a guess.
  Money amounts are always read from the database, never taken from the caller.
- "Today" is desk.date_today, never the system clock.
- Agents can only *request* payments and purchase orders. Money moves only in
  approve_and_pay, which needs a named human approver and refuses if cash would
  go negative or the vendor still has an open invoice.
- Drafts for customers and vendors are posted to the board. Nothing is ever sent.
"""

import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# No network update check on startup: keeps stdio startup fast for the agents.
os.environ.setdefault("FASTMCP_CHECK_FOR_UPDATES", "off")

from fastmcp import FastMCP  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"

AGENT_ROLES = {"boss", "inventory", "accounting", "facilities", "customer_service"}
BOARD_POST_KINDS = {
    "customer_draft",  # message to a customer; stays on the board, never sent
    "vendor_draft",  # message to a vendor or landlord; stays on the board, never sent
    "internal_note",  # findings shared with the team
    "decision",  # Boss's final call on a ticket
    "escalation",  # needs a human to review before anything else happens
}
TICKET_STATUSES = {"open", "in_progress", "waiting_on_human", "waiting_on_stock", "resolved"}

mcp = FastMCP("campus-customs")


# --------------------------------------------------------------------------- db helpers

# Tables the team adds to the working copy. The original database does not have them;
# they are created on first use and disappear when the working copy is reset.
_TEAM_TABLES = """
CREATE TABLE IF NOT EXISTS board_posts (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    author_role TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER REFERENCES tickets(id),
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    sku TEXT NOT NULL,
    size TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL,
    expected_arrival TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER REFERENCES tickets(id),
    kind TEXT NOT NULL,
    ref_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    account TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    decision_note TEXT,
    payment_id INTEGER REFERENCES payments(id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _db(write: bool = False):
    """Open the working database. Read-only unless write=True; writes are one transaction."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}")
    if write:
        conn = sqlite3.connect(DB_PATH, isolation_level=None)
    else:
        conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    with closing(conn):
        if write:
            conn.executescript(_TEAM_TABLES)
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        else:
            yield conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def _rows(conn: sqlite3.Connection, table: str, sql: str, params=()) -> list[dict]:
    """Rows from a team table, or [] if the table hasn't been created yet."""
    if not _has_table(conn, table):
        return []
    return [dict(r) for r in conn.execute(sql, params)]


def _shop_today(conn: sqlite3.Connection) -> str:
    """The shop's 'today' comes from desk.date_today, never the system clock."""
    row = conn.execute("SELECT date_today FROM desk").fetchone()
    if row is None:
        raise ValueError("desk.date_today is missing from the database")
    return row["date_today"]


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days


def _add_one_month(iso_day: str) -> str:
    d = date.fromisoformat(iso_day)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    raise ValueError(f"Cannot add a month to {iso_day}")


def _open_invoices_for_vendor(conn: sqlite3.Connection, vendor_id: int, today: str) -> list[dict]:
    return [
        {
            "invoice_id": inv["id"],
            "amount": inv["amount"],
            "due_date": inv["due_date"],
            "days_overdue": max(_days_between(inv["due_date"], today), 0),
            "description": inv["description"],
        }
        for inv in conn.execute(
            "SELECT id, amount, due_date, description FROM invoices "
            "WHERE vendor_id = ? AND status = 'open' ORDER BY id",
            (vendor_id,),
        )
    ]


def _pending_total(conn: sqlite3.Connection, account: str) -> float:
    if not _has_table(conn, "approvals"):
        return 0.0
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM approvals WHERE account = ? AND status = 'pending'",
        (account,),
    ).fetchone()
    return round(row["s"], 2)


def _check_role(role: str) -> str | None:
    if role not in AGENT_ROLES:
        return f"Unknown role {role!r}; must be one of {sorted(AGENT_ROLES)}"
    return None


# --------------------------------------------------------------------------- read tools


@mcp.tool
def list_open_tickets() -> dict:
    """List every ticket whose status is not 'resolved', oldest first, with the shop date.

    Boss uses this to see the board before routing work.
    """
    with _db() as conn:
        tickets = [
            dict(t)
            for t in conn.execute(
                "SELECT * FROM tickets WHERE status != 'resolved' ORDER BY created_at, id"
            )
        ]
        return {"shop_today": _shop_today(conn), "count": len(tickets), "tickets": tickets}


@mcp.tool
def list_all_tickets() -> dict:
    """List every ticket (open or resolved) with its status, oldest first, and counts
    of open vs resolved. The dashboard uses this for the ticket board.
    """
    with _db() as conn:
        tickets = []
        for t in conn.execute("SELECT * FROM tickets ORDER BY created_at, id"):
            row = dict(t)
            row["is_resolved"] = t["status"] == "resolved"
            tickets.append(row)
        resolved = sum(t["is_resolved"] for t in tickets)
        return {
            "shop_today": _shop_today(conn),
            "count": len(tickets),
            "open_count": len(tickets) - resolved,
            "resolved_count": resolved,
            "tickets": tickets,
        }


@mcp.tool
def get_ticket_details(ticket_id: int) -> dict:
    """Return one ticket plus every row it links to: inventory and pricing for its sku/size,
    its lease, its invoice and that invoice's vendor, plus board posts, approvals and
    purchase orders already filed against it.

    Every agent starts here so they all work from the same facts.
    """
    with _db() as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"error": f"No ticket with id={ticket_id}"}
        today = _shop_today(conn)
        out: dict = {"shop_today": today, "ticket": dict(t), "linked": {}}

        if t["sku"]:
            rows = conn.execute(
                "SELECT * FROM inventory WHERE sku = ? AND size = ?", (t["sku"], t["size"])
            ).fetchall()
            out["linked"]["inventory"] = [dict(r) for r in rows]
            price = conn.execute("SELECT * FROM pricing WHERE sku = ?", (t["sku"],)).fetchone()
            out["linked"]["pricing"] = dict(price) if price else None
        if t["lease_id"] is not None:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (t["lease_id"],)).fetchone()
            out["linked"]["lease"] = dict(lease) if lease else None
        if t["invoice_id"] is not None:
            inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (t["invoice_id"],)).fetchone()
            if inv:
                inv = dict(inv)
                inv["days_overdue"] = (
                    max(_days_between(inv["due_date"], today), 0) if inv["status"] == "open" else 0
                )
                vendor = conn.execute(
                    "SELECT * FROM vendors WHERE id = ?", (inv["vendor_id"],)
                ).fetchone()
                out["linked"]["invoice"] = inv
                out["linked"]["invoice_vendor"] = dict(vendor) if vendor else None
            else:
                out["linked"]["invoice"] = None

        out["board_posts"] = _rows(
            conn, "board_posts", "SELECT * FROM board_posts WHERE ticket_id = ? ORDER BY id", (ticket_id,)
        )
        out["approvals"] = _rows(
            conn, "approvals", "SELECT * FROM approvals WHERE ticket_id = ? ORDER BY id", (ticket_id,)
        )
        out["purchase_orders"] = _rows(
            conn,
            "purchase_orders",
            "SELECT * FROM purchase_orders WHERE ticket_id = ? ORDER BY id",
            (ticket_id,),
        )
        return out


@mcp.tool
def check_stock_and_vendors(sku: str, size: str, qty_needed: int) -> dict:
    """Check on-hand stock for one SKU + size against the quantity a ticket needs, and
    list every vendor with its specialty, lead time, open invoices, and whether it can
    ship (a vendor with any open invoice will not ship).

    Inventory uses this for customer orders and bulk requests (tickets 101, 103).
    """
    with _db() as conn:
        today = _shop_today(conn)
        item = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()
        if item is None:
            return {"error": f"No inventory row for sku={sku!r}, size={size!r}"}

        vendors = []
        for v in conn.execute("SELECT id, name, specialty, lead_days FROM vendors ORDER BY id"):
            open_invoices = _open_invoices_for_vendor(conn, v["id"], today)
            vendors.append(
                {
                    "vendor_id": v["id"],
                    "name": v["name"],
                    "specialty": v["specialty"],
                    "lead_days": v["lead_days"],
                    "earliest_arrival_if_ordered_today": (
                        date.fromisoformat(today) + timedelta(days=v["lead_days"])
                    ).isoformat(),
                    "open_invoices": open_invoices,
                    "can_ship": not open_invoices,
                }
            )

        return {
            "shop_today": today,
            "sku": item["sku"],
            "name": item["name"],
            "size": item["size"],
            "location": item["location"],
            "on_hand": item["qty"],
            "qty_needed": qty_needed,
            "shortfall": max(qty_needed - item["qty"], 0),
            "vendors": vendors,
        }


@mcp.tool
def get_pricing_and_margin(sku: str, qty: int, discount_pct: float = 0.0) -> dict:
    """Return the database unit cost and list price for a SKU, and the per-unit and total
    margin for a quantity at a proposed discount off list price. Flags any discount that
    would sell below unit cost.

    Accounting uses this for discount / price-override requests (ticket 103).
    """
    if not 0 <= discount_pct < 100:
        return {"error": "discount_pct must be between 0 and 100"}
    with _db() as conn:
        price = conn.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
        if price is None:
            return {"error": f"No pricing row for sku={sku!r}"}

        unit_cost = price["unit_cost"]
        list_price = price["list_price"]
        unit_price = round(list_price * (1 - discount_pct / 100), 2)
        unit_margin = round(unit_price - unit_cost, 2)

        return {
            "sku": price["sku"],
            "qty": qty,
            "unit_cost": unit_cost,
            "list_price": list_price,
            "discount_pct": discount_pct,
            "unit_price": unit_price,
            "unit_margin": unit_margin,
            "margin_pct": round(unit_margin / unit_price * 100, 2) if unit_price else None,
            "quote_total": round(unit_price * qty, 2),
            "total_cost": round(unit_cost * qty, 2),
            "total_margin": round(unit_margin * qty, 2),
            "below_cost": unit_margin < 0,
            "max_discount_pct_before_loss": round((1 - unit_cost / list_price) * 100, 2),
        }


@mcp.tool
def get_lease_rent_status(lease_id: int) -> dict:
    """Look up a lease's rent amount and next due date, how many days until (or past) due
    based on desk.date_today, any rent requests already pending, and whether each cash
    account covers the rent after other pending approvals.

    Facilities uses this for rent notices (ticket 102).
    """
    with _db() as conn:
        today = _shop_today(conn)
        lease = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if lease is None:
            return {"error": f"No lease with id={lease_id}"}

        days_until_due = _days_between(today, lease["next_due"])
        accounts = []
        for a in conn.execute("SELECT name, balance, date FROM cash_accounts ORDER BY name"):
            pending = _pending_total(conn, a["name"])
            accounts.append(
                {
                    "account": a["name"],
                    "balance": a["balance"],
                    "as_of": a["date"],
                    "pending_approvals_total": pending,
                    "covers_rent": a["balance"] >= lease["monthly_rent"],
                    "covers_rent_after_pending": a["balance"] - pending >= lease["monthly_rent"],
                }
            )

        return {
            "shop_today": today,
            "lease_id": lease["id"],
            "space_name": lease["space_name"],
            "landlord": lease["landlord"],
            "monthly_rent": lease["monthly_rent"],
            "next_due": lease["next_due"],
            "days_until_due": days_until_due,
            "overdue": days_until_due < 0,
            "notes": lease["notes"],
            "rent_requests": _rows(
                conn,
                "approvals",
                "SELECT * FROM approvals WHERE kind = 'rent' AND ref_id = ? ORDER BY id",
                (lease_id,),
            ),
            "rent_payments": [
                dict(p)
                for p in conn.execute(
                    "SELECT * FROM payments WHERE kind = 'rent' AND ref_id = ? ORDER BY id", (lease_id,)
                )
            ],
            "cash_accounts": accounts,
        }


@mcp.tool
def get_invoice_status(invoice_id: int) -> dict:
    """Return one vendor invoice with its vendor, days overdue against desk.date_today,
    whether it is blocking that vendor from shipping, and any payment requests or
    payments already made against it.

    Accounting uses this before preparing an invoice payment (ticket 101 / invoice 501).
    """
    with _db() as conn:
        today = _shop_today(conn)
        inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if inv is None:
            return {"error": f"No invoice with id={invoice_id}"}
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (inv["vendor_id"],)).fetchone()
        is_open = inv["status"] == "open"
        days_past_due = _days_between(inv["due_date"], today)
        return {
            "shop_today": today,
            "invoice": dict(inv),
            "vendor": dict(vendor) if vendor else None,
            "overdue": is_open and days_past_due > 0,
            "days_overdue": max(days_past_due, 0) if is_open else 0,
            "blocks_vendor_shipping": is_open,
            "payment_requests": _rows(
                conn,
                "approvals",
                "SELECT * FROM approvals WHERE kind = 'invoice' AND ref_id = ? ORDER BY id",
                (invoice_id,),
            ),
            "payments": [
                dict(p)
                for p in conn.execute(
                    "SELECT * FROM payments WHERE kind = 'invoice' AND ref_id = ? ORDER BY id",
                    (invoice_id,),
                )
            ],
        }


@mcp.tool
def get_cash_position() -> dict:
    """Return every cash account balance, the total of approvals still pending against it,
    what would be left if all pending approvals were paid, every open invoice, the next
    rent due, and the payment history. Revenue is not modeled: cash only goes out.

    Accounting and Boss use this to decide what can be paid and in what order.
    """
    with _db() as conn:
        today = _shop_today(conn)
        accounts = []
        for a in conn.execute("SELECT name, balance, date FROM cash_accounts ORDER BY name"):
            pending = _pending_total(conn, a["name"])
            accounts.append(
                {
                    "account": a["name"],
                    "balance": a["balance"],
                    "as_of": a["date"],
                    "pending_approvals_total": pending,
                    "balance_if_all_pending_paid": round(a["balance"] - pending, 2),
                }
            )
        open_invoices = []
        for inv in conn.execute(
            "SELECT i.*, v.name AS vendor_name FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
            "WHERE i.status = 'open' ORDER BY i.due_date"
        ):
            row = dict(inv)
            row["days_overdue"] = max(_days_between(inv["due_date"], today), 0)
            open_invoices.append(row)
        leases = []
        for lease in conn.execute("SELECT * FROM leases ORDER BY next_due"):
            row = dict(lease)
            row["days_until_due"] = _days_between(today, lease["next_due"])
            leases.append(row)
        return {
            "shop_today": today,
            "accounts": accounts,
            "open_invoices": open_invoices,
            "leases": leases,
            "pending_approvals": _rows(
                conn, "approvals", "SELECT * FROM approvals WHERE status = 'pending' ORDER BY id"
            ),
            "payments": [dict(p) for p in conn.execute("SELECT * FROM payments ORDER BY id")],
            "revenue_modeled": False,
        }


@mcp.tool
def list_pending_approvals() -> dict:
    """List every payment or purchase-order request waiting for a human decision, with the
    cash balance each one would draw from.
    """
    with _db() as conn:
        pending = _rows(
            conn, "approvals", "SELECT * FROM approvals WHERE status = 'pending' ORDER BY id"
        )
        balances = {
            a["name"]: a["balance"] for a in conn.execute("SELECT name, balance FROM cash_accounts")
        }
        return {"shop_today": _shop_today(conn), "balances": balances, "pending": pending}


# --------------------------------------------------------------------------- agent write tools


@mcp.tool
def post_to_board(ticket_id: int, author_role: str, kind: str, content: str) -> dict:
    """Post to a ticket's board thread. kind is one of: customer_draft, vendor_draft,
    internal_note, decision, escalation. Drafts are NEVER sent to anyone; they stay on the
    board for a human to read.
    """
    if err := _check_role(author_role):
        return {"error": err}
    if kind not in BOARD_POST_KINDS:
        return {"error": f"kind must be one of {sorted(BOARD_POST_KINDS)}"}
    if kind == "customer_draft" and author_role != "customer_service":
        return {"error": "Only customer_service writes customer_draft posts"}
    if kind == "decision" and author_role != "boss":
        return {"error": "Only boss posts decisions"}
    if not content.strip():
        return {"error": "content is empty"}
    with _db(write=True) as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return {"error": f"No ticket with id={ticket_id}"}
        cur = conn.execute(
            "INSERT INTO board_posts (ticket_id, author_role, kind, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (ticket_id, author_role, kind, content.strip(), _now()),
        )
        return {"posted": True, "post_id": cur.lastrowid, "sent_to_anyone": False}


@mcp.tool
def request_payment(
    ticket_id: int, kind: str, ref_id: int, account: str, requested_by: str, reason: str
) -> dict:
    """Prepare a payment for HUMAN APPROVAL. Moves no money.

    kind='invoice' pays invoices.id=ref_id (amount = invoices.amount).
    kind='rent' pays leases.id=ref_id (amount = leases.monthly_rent).
    The amount is always read from the database. Refuses duplicates, already-paid
    invoices, and requests the account balance could never cover.
    """
    if err := _check_role(requested_by):
        return {"error": err}
    if kind not in ("invoice", "rent"):
        return {"error": "kind must be 'invoice' or 'rent' (use request_purchase_order for restocks)"}
    with _db(write=True) as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return {"error": f"No ticket with id={ticket_id}"}
        acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if acct is None:
            return {"error": f"No cash account named {account!r}"}

        if kind == "invoice":
            inv = conn.execute("SELECT amount, status FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if inv is None:
                return {"error": f"No invoice with id={ref_id}"}
            if inv["status"] != "open":
                return {"error": f"Invoice {ref_id} is {inv['status']!r}, not open; nothing to pay"}
            amount = inv["amount"]
        else:
            lease = conn.execute("SELECT monthly_rent FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if lease is None:
                return {"error": f"No lease with id={ref_id}"}
            amount = lease["monthly_rent"]

        dup = conn.execute(
            "SELECT id FROM approvals WHERE kind = ? AND ref_id = ? AND status = 'pending'",
            (kind, ref_id),
        ).fetchone()
        if dup:
            return {"error": f"A pending {kind} request for ref_id={ref_id} already exists (approval {dup['id']})"}
        if amount > acct["balance"]:
            return {
                "error": f"Refused: {kind} amount {amount} exceeds {account} balance {acct['balance']}"
            }

        cur = conn.execute(
            "INSERT INTO approvals (ticket_id, kind, ref_id, amount, account, requested_by, reason, "
            "status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (ticket_id, kind, ref_id, amount, account, requested_by, reason, _now()),
        )
        pending = _pending_total(conn, account)
        return {
            "approval_id": cur.lastrowid,
            "status": "pending",
            "kind": kind,
            "ref_id": ref_id,
            "amount": amount,
            "account": account,
            "money_moved": False,
            "needs": "human approval on the dashboard",
            "balance": acct["balance"],
            "pending_approvals_total": pending,
            "over_committed": pending > acct["balance"],
        }


@mcp.tool
def request_purchase_order(
    ticket_id: int,
    vendor_id: int,
    sku: str,
    size: str,
    qty: int,
    account: str,
    requested_by: str,
    reason: str,
) -> dict:
    """Prepare a restock purchase order for HUMAN APPROVAL. Moves no money.

    The unit cost comes from pricing.unit_cost and the lead time from vendors.lead_days.
    If the vendor has an open invoice it will not ship: the PO is still filed so the
    human sees it, but it is flagged blocked and cannot be paid until that invoice is paid.
    """
    if err := _check_role(requested_by):
        return {"error": err}
    if qty <= 0:
        return {"error": "qty must be positive"}
    with _db(write=True) as conn:
        today = _shop_today(conn)
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return {"error": f"No ticket with id={ticket_id}"}
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            return {"error": f"No vendor with id={vendor_id}"}
        if conn.execute(
            "SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone() is None:
            return {"error": f"No inventory row for sku={sku!r}, size={size!r}"}
        price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if price is None:
            return {"error": f"No pricing row for sku={sku!r}"}
        acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if acct is None:
            return {"error": f"No cash account named {account!r}"}

        total = round(price["unit_cost"] * qty, 2)
        if total > acct["balance"]:
            return {"error": f"Refused: PO total {total} exceeds {account} balance {acct['balance']}"}
        blockers = _open_invoices_for_vendor(conn, vendor_id, today)

        po = conn.execute(
            "INSERT INTO purchase_orders (ticket_id, vendor_id, sku, size, qty, unit_cost, total, "
            "status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?)",
            (ticket_id, vendor_id, sku, size, qty, price["unit_cost"], total, _now()),
        )
        appr = conn.execute(
            "INSERT INTO approvals (ticket_id, kind, ref_id, amount, account, requested_by, reason, "
            "status, created_at) VALUES (?, 'purchase_order', ?, ?, ?, ?, ?, 'pending', ?)",
            (ticket_id, po.lastrowid, total, account, requested_by, reason, _now()),
        )
        pending = _pending_total(conn, account)
        return {
            "purchase_order_id": po.lastrowid,
            "approval_id": appr.lastrowid,
            "status": "pending",
            "vendor": vendor["name"],
            "sku": sku,
            "size": size,
            "qty": qty,
            "unit_cost": price["unit_cost"],
            "total": total,
            "lead_days": vendor["lead_days"],
            "blocked_by_open_invoices": blockers,
            "money_moved": False,
            "needs": "human approval on the dashboard",
            "balance": acct["balance"],
            "pending_approvals_total": pending,
            "over_committed": pending > acct["balance"],
        }


@mcp.tool
def update_ticket_status(ticket_id: int, status: str, note: str, updated_by: str) -> dict:
    """Set a ticket's status (open, in_progress, waiting_on_human, waiting_on_stock,
    resolved) and append a dated note. Only Boss changes ticket status.
    """
    if updated_by != "boss":
        return {"error": "Only boss updates ticket status"}
    if status not in TICKET_STATUSES:
        return {"error": f"status must be one of {sorted(TICKET_STATUSES)}"}
    with _db(write=True) as conn:
        t = conn.execute("SELECT status, notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"error": f"No ticket with id={ticket_id}"}
        today = _shop_today(conn)
        notes = (t["notes"] or "") + f"\n[{today} boss] {status}: {note}"
        conn.execute(
            "UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, notes.strip(), ticket_id)
        )
        return {"ticket_id": ticket_id, "old_status": t["status"], "new_status": status}


# --------------------------------------------------------------------------- human-only tools
# These are never given to any agent (see backend/mcp_tools.py). Only the human dashboard
# calls them.


@mcp.tool
def approve_and_pay(approval_id: int, approved_by: str) -> dict:
    """HUMAN ONLY. Approve a pending request and pay it in one transaction.

    Refuses if: the approver is blank or an agent role; the request is not pending; the
    account balance is less than the amount (no negative balances); or, for a purchase
    order, the vendor still has an open invoice. On success it writes a payments row,
    lowers cash_accounts.balance, and marks the invoice paid / moves the lease's next_due
    forward one month / marks the purchase order ordered with its expected arrival.
    """
    approver = (approved_by or "").strip()
    if not approver:
        return {"error": "Refused: a named human approver is required"}
    if approver.lower().replace(" ", "_") in AGENT_ROLES:
        return {"error": "Refused: agents cannot approve payments"}
    with _db(write=True) as conn:
        today = _shop_today(conn)
        a = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if a is None:
            return {"error": f"No approval with id={approval_id}"}
        if a["status"] != "pending":
            return {"error": f"Refused: approval {approval_id} is {a['status']!r}, not pending"}
        acct = conn.execute(
            "SELECT balance FROM cash_accounts WHERE name = ?", (a["account"],)
        ).fetchone()
        if acct is None:
            return {"error": f"No cash account named {a['account']!r}"}
        if a["amount"] > acct["balance"]:
            return {
                "error": f"Refused: insufficient cash. {a['account']} has {acct['balance']}, "
                f"payment needs {a['amount']}. Balances may not go negative."
            }

        effect: dict = {}
        if a["kind"] == "invoice":
            inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (a["ref_id"],)).fetchone()
            if inv is None or inv["status"] != "open":
                return {"error": f"Refused: invoice {a['ref_id']} is not open"}
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (a["ref_id"],))
            effect = {"invoice_id": a["ref_id"], "invoice_status": "paid"}
        elif a["kind"] == "rent":
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (a["ref_id"],)).fetchone()
            if lease is None:
                return {"error": f"Refused: lease {a['ref_id']} not found"}
            new_due = _add_one_month(lease["next_due"])
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, a["ref_id"]))
            effect = {"lease_id": a["ref_id"], "paid_period_due": lease["next_due"], "next_due": new_due}
        elif a["kind"] == "purchase_order":
            po = conn.execute("SELECT * FROM purchase_orders WHERE id = ?", (a["ref_id"],)).fetchone()
            if po is None or po["status"] != "pending_approval":
                return {"error": f"Refused: purchase order {a['ref_id']} is not awaiting approval"}
            blockers = _open_invoices_for_vendor(conn, po["vendor_id"], today)
            if blockers:
                return {
                    "error": "Refused: vendor has open invoices and will not ship until they are paid",
                    "open_invoices": blockers,
                }
            lead = conn.execute(
                "SELECT lead_days FROM vendors WHERE id = ?", (po["vendor_id"],)
            ).fetchone()["lead_days"]
            arrival = (date.fromisoformat(today) + timedelta(days=lead)).isoformat()
            conn.execute(
                "UPDATE purchase_orders SET status = 'ordered', expected_arrival = ? WHERE id = ?",
                (arrival, po["id"]),
            )
            effect = {"purchase_order_id": po["id"], "po_status": "ordered", "expected_arrival": arrival}
        else:
            return {"error": f"Unknown approval kind {a['kind']!r}"}

        new_balance = round(acct["balance"] - a["amount"], 2)
        conn.execute(
            "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
            (new_balance, today, a["account"]),
        )
        pay = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (a["kind"], a["ref_id"], a["amount"], a["account"], today, approver),
        )
        conn.execute(
            "UPDATE approvals SET status = 'approved_paid', decided_by = ?, decided_at = ?, "
            "payment_id = ? WHERE id = ?",
            (approver, _now(), pay.lastrowid, approval_id),
        )
        return {
            "approval_id": approval_id,
            "ticket_id": a["ticket_id"],
            "payment_id": pay.lastrowid,
            "kind": a["kind"],
            "amount": a["amount"],
            "account": a["account"],
            "new_balance": new_balance,
            "approved_by": approver,
            **effect,
        }


@mcp.tool
def reject_approval(approval_id: int, decided_by: str, reason: str) -> dict:
    """HUMAN ONLY. Reject a pending payment or purchase-order request. Moves no money."""
    decider = (decided_by or "").strip()
    if not decider or decider.lower().replace(" ", "_") in AGENT_ROLES:
        return {"error": "Refused: a named human is required to reject"}
    with _db(write=True) as conn:
        a = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if a is None:
            return {"error": f"No approval with id={approval_id}"}
        if a["status"] != "pending":
            return {"error": f"Approval {approval_id} is {a['status']!r}, not pending"}
        conn.execute(
            "UPDATE approvals SET status = 'rejected', decided_by = ?, decided_at = ?, "
            "decision_note = ? WHERE id = ?",
            (decider, _now(), reason, approval_id),
        )
        if a["kind"] == "purchase_order":
            conn.execute(
                "UPDATE purchase_orders SET status = 'rejected' WHERE id = ?", (a["ref_id"],)
            )
        return {
            "approval_id": approval_id,
            "ticket_id": a["ticket_id"],
            "status": "rejected",
            "money_moved": False,
        }


if __name__ == "__main__":
    mcp.run(show_banner=False)
