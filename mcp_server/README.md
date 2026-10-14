# Campus Customs MCP Server

**What it's for:** This server is the only shop-tools layer for the Campus Customs Multi-Agent Operations team. Every agent (Boss, Inventory, Accounting, Facilities, Customer Service) reads and writes shop data only through these tools. The backend has no SQL of its own. Tools return only what's in the database: a missing row gives an error, never a guess, and money amounts are always read from the database rather than taken from the caller.

**Database:** `data/campus_customs_new.db` is the working copy. The original `data/campus_customs.db` is never opened by this server, so the working copy can always be reset from it (`python -m backend.team --reset`). On first write, the server adds three team tables to the working copy: `board_posts`, `approvals` and `purchase_orders`.

**"Today":** All date math (overdue, days until due, arrival dates) uses `desk.date_today`, not the computer's clock.

## Tools (15)

### Read
| Tool | Inputs | Returns |
|---|---|---|
| `list_open_tickets` | none | Every ticket not yet `resolved`, oldest first, plus the shop date. |
| `list_all_tickets` | none | Every ticket, open or resolved, with `is_resolved` and open and resolved counts (used by the dashboard). |
| `get_ticket_details` | `ticket_id` | The ticket plus its linked inventory, pricing, lease, invoice and vendor rows, and the board posts, approvals and POs already filed against it. |
| `check_stock_and_vendors` | `sku`, `size`, `qty_needed` | On-hand stock and shortfall for that exact SKU and size, plus every vendor's specialty, lead days, earliest arrival, open invoices and `can_ship`. |
| `get_pricing_and_margin` | `sku`, `qty`, `discount_pct` | Unit cost, list price, the discounted price, per-unit and total margin, `below_cost`, and the largest discount before a loss. |
| `get_lease_rent_status` | `lease_id` | Rent, next due date, days until due, rent already requested or paid, and whether cash covers it before and after pending approvals. |
| `get_invoice_status` | `invoice_id` | The invoice and its vendor, days overdue, whether it blocks shipping, and requests or payments against it. |
| `get_cash_position` | none | Balances, the pending-approval total, the balance if all pending were paid, open invoices, leases, payment history, and `revenue_modeled: false`. |
| `list_pending_approvals` | none | Every payment or PO request waiting on a human, with balances. |

### Agent writes (no money moves)
| Tool | Inputs | Effect |
|---|---|---|
| `post_to_board` | `ticket_id`, `author_role`, `kind`, `content` | Adds a `customer_draft`, `vendor_draft`, `internal_note`, `decision` or `escalation` post. Drafts are **never sent**. |
| `request_payment` | `ticket_id`, `kind` (`invoice`/`rent`), `ref_id`, `account`, `requested_by`, `reason` | Files a pending approval. The amount comes from `invoices.amount` or `leases.monthly_rent`. Refuses duplicates, already-paid invoices, and amounts over the balance. |
| `request_purchase_order` | `ticket_id`, `vendor_id`, `sku`, `size`, `qty`, `account`, `requested_by`, `reason` | Files a pending PO and approval at `pricing.unit_cost`, flagged as blocked if the vendor has an open invoice. |
| `update_ticket_status` | `ticket_id`, `status`, `note`, `updated_by` | Boss only. Sets the status and appends a dated note. |

### Human only (never given to any agent)
| Tool | Inputs | Effect |
|---|---|---|
| `approve_and_pay` | `approval_id`, `approved_by` | Approves and pays in one transaction (called only by the backend's `POST /approvals/{id}/approve` route): a `payments` row, a lower `cash_accounts.balance`, and the invoice marked paid, the lease's `next_due` moved forward a month, or the PO marked ordered. **Refuses** if the balance would go negative, the vendor still has an open invoice (POs), the request isn't pending, or the approver is blank or an agent role. |
| `reject_approval` | `approval_id`, `decided_by`, `reason` | Rejects a pending request. Moves no money. |

## Run

```bash
pip install fastmcp
python mcp_server/server.py
```

The project's `.mcp.json` registers this server as `campus-customs`.
