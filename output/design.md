# Agent Desk: dashboard design

The React + Vite + TypeScript dashboard in `frontend/`. Start the backend from `backend/` with `uvicorn main:app --reload --port 8000`, then the board from `frontend/` with `npm run dev`. That opens **http://localhost:5173** in the browser. The page calls the FastAPI routes at `http://localhost:8000` (set in `frontend/.env`), and the backend's CORS settings allow the Vite origin `http://localhost:5173`.

## The look: a cozy pastel shop room

The board continues the theme of `output/desk_tickets.html`, which came from a pastel "kawaii room" reference picture:

- **Palette:** pink gingham background, with baby blue, cream, butter yellow and peach. The text is a soft plum instead of black.
- **Header:** a small retro **TV**. Its cream screen holds a tilted pink **"Agent Desk"** sign, the shop date, open and resolved counts, and the model (`openai-gpt-luna-6`).
- **Control bar:** below the TV, a cream **dock** holds the "You're approving as" name field and the Reset button, like an app dock on a phone home screen.
- **Cards:** rounded "sticker" cards with a soft colored shadow underneath. The font is the rounded **Nunito**. Small ♡ hearts appear in the title and footer. There are no emojis; the cuteness comes from shape and color.
- **Color by job:** each panel's tint matches its purpose. Cash is baby blue (calm, money), approvals are butter yellow (attention, without the alarm of red), and everything else is cream.

### Why it looks this way

We wanted the board to be somewhere you *want* to be. Everyone deserves a fun work environment, and work tools don't have to be boring. Working remotely with an agentic team is hard when the window you watch them through is flat, one-toned and one-dimensional. A gray admin table makes the agents feel like log lines. A cozy room where each teammate has a face, a color and a speech bubble makes you feel like you're **on the team**, watching coworkers talk to each other and checking in when they need you.

The playfulness has rules, though, so it never gets in the way of the job:
- **Calm by default:** colors are soft and stay consistent. Motion only happens when something actually changes, like an agent working, a payment approved, or a ticket resolved.
- **Cute never hides real information:** money, statuses and tool names stay crisp and readable (tabular numbers for cash, monospace for tool names).
- **Fun interactions are also safety features:** see hold-to-approve below.

## Layout

| Left: what needs doing | Center: the team at work | Right: what needs *you* |
|---|---|---|
| **Ticket board**: the 3 tickets as cards (id, type, subject, requester, open / team working / resolved). Click to select; **Start the team** appears on the selected open ticket. | **Team room**: five avatars, speech bubbles, status chips, a "3 of 5 teammates on this ticket" count, and the **token budget** bar (used / 150,000). | **Needs your OK**: payment and purchase-order requests the agents prepared, each with **Hold to approve** or *decline*. |
| **Checking**: the live balance, pending total, balance if you approve everything, and the payment history with who approved each one. | **Live feed** (who said what, tool by tool) and **Who did what** (a per-agent summary) side by side. | **On the board**: the ticket's drafts, team notes, Boss's decision and escalations. |

On narrower screens it collapses to two columns, then one.

## How the agents look and read differently

Each teammate has their own **pastel color and a little hand-drawn character** (an inline SVG in `frontend/src/components/AgentIcon.tsx`, with no emojis or images). The character appears everywhere they do (team room, feed, summaries, board posts), so you can follow a conversation without reading names:

| Agent | Color | Character |
|---|---|---|
| Boss | pink | a woman in a navy blazer with a pink bow, gold earrings and a tiny gold crown |
| Inventory | baby blue | baseball cap, holding a taped cardboard box |
| Accounting | butter yellow | a woman with her hair in a bun under a green accountant's visor, round glasses, a pencil behind her ear |
| Facilities | mint | yellow hard hat and work overalls |
| Customer Service | lavender | headset with a mic, a little heart on the sweater |

Each one looks like their job, so the team room reads like a staff photo, and the team is deliberately mixed. The leader and the numbers person are women, so the look doesn't fall back on stereotypes about who runs the shop or who answers the phone. Teammates who weren't called on a ticket fade to grey.

**When an agent is called on a ticket**, the team room comes alive from the audit trail (`GET /events`, polled every 1.2 seconds during a run):
- **Working:** a speech bubble appears above the avatar only while it's working or waiting, so there's no empty space when no one is talking. The avatar gently bobs with a pulsing ring, and the chip turns solid in their color. The speech bubble shows what they're doing in plain words, translated from the MCP tool they called ("checking stock & vendors", "checking the lease", "preparing a payment for approval"), or the last thing they said.
- **Waiting:** a dashed chip reading "waiting on Facilities" while a teammate they asked is working. Delegation shows in the feed as a dashed bubble ("asked Accounting …" with the exact request).
- **Done:** a mint chip.
- **Not called:** the avatar stays faded and grey, and the summary says *"Not called on this ticket. Boss kept them free."* This is deliberate. It makes Boss's routing visible, so you can see at a glance that a rent notice used 3 teammates, not 5, which is the cost discipline we planned in Problem 6.

The **live feed** reads like a group chat. Each line has the agent's mini avatar and a colored name, plus:
- what they said
- the tool chip (`check_stock_and_vendors`)
- handoffs to teammates
- **refusals in yellow**, for when a tool says no (e.g. "agents cannot approve payments")
- the final report in mint

**Who did what** gives each agent's one-paragraph summary (Boss shows its decision and final status) with tool chips and counts, e.g. `get_lease_rent_status ×2`.

## How tickets resolve

- **Start the team** → `POST /tickets/{id}/run`. The card turns butter yellow with a "team working ···" pill. To keep the shared-cash reasoning orderly, only one ticket runs at a time.
- When Boss hands in its final decision, the ticket **flips to Resolved**. It gets a mint pill, a green RESOLVED stamp that thumps onto the card, a burst of floating hearts, and a toast ("Ticket 102 resolved by the team").
- Boss's exact database status (e.g. "waiting on human") stays visible under the subject, so "resolved" never hides that a payment still needs your click.
- If a run fails or hits its token budget, the toast says the ticket needs a human look, and it stays open.

## How cash shows up and moves

- The **Checking** card shows `cash_accounts.balance` (`GET /cash`) in large blue numbers. Under it: *waiting for approval*, and *if you approve everything*, which turns red with a warning when there isn't enough cash for every request.
- Money moves only when a human approves. When the balance drops, the number **counts down** smoothly, a pink "−$2,400" floats up, and a few **gold coins fall** out of the card. The payment then appears in the history with *by Daria*.
- The card states plainly: *No revenue is modeled. Cash only goes out, and only when a human approves.*

## The fun approval: Hold to approve

The agents can only prepare requests, so every payment and purchase order lands in **Needs your OK**. You type your name once in the dock ("You're approving as"); the backend stores it as `approved_by`.

To approve, you **press and hold** the button for about 1.2 seconds. A pink fill sweeps across it ("keep holding…"). When it's full, the payment goes through (`POST /approvals/{id}/approve`), a red **APPROVED** rubber stamp slams onto the card with your name, hearts float up, the coins fall in the cash card, and a toast confirms "Paid $2,400 · checking is now $1,000".

**Why holding instead of clicking:** it's satisfying, and it's a deliberate "are you sure?" that can't happen by accident. Letting go early cancels it. That matters when one click moves real money. If the pay tool refuses (not enough cash, the vendor still has an unpaid invoice, the request isn't pending), the card **shakes** and shows the tool's exact reason in a soft red note. Nothing moves. **Decline** asks for an optional reason and moves no money.

## Cash timeline

A chart under the Team room shows **checking, step by step**:
- **Solid line:** a step line from the starting balance down through each payment a human approved (`start → invoice #501 → …`).
- **Dashed line:** the same line continued through every request still waiting for approval (`rent #1?`, `PO #1?`), with a direct label such as "−$104 if all approved".
- **Below $0:** a dotted $0 floor line appears, plus a note that the pay tool will refuse whichever request would make checking negative. That is the "no negative balances" rule made visible before anyone clicks.

Why it's built this way:
- **One series, one axis:** it's the same account, actual and projected. So it uses one color, and the solid-vs-dashed line (plus the key below the chart) carries the difference, not a second color. A step line fits because cash changes in discrete payments, not smoothly.
- **Color checked, not guessed:** the line color was run through the dataviz palette validator against each mode's card color: `#3a74ad` for day and `#5f97d4` for night. Both pass the lightness, chroma and 3:1 contrast checks.
- **Hover:** each point shows a tooltip with the balance, the amount, and who approved it, or "pending, not paid". **Show as table** swaps the chart for a plain table for screen readers.

## Night shift

A **Night shift** button sits in the top-right corner. Its sun slides into a crescent moon, and the whole desk changes to the night palette, with a smooth color fade. The choice is remembered, and the page starts in the right mode without flashing.

Night shift isn't an automatic invert. It's a separate set of steps from the same hues:
- **Background:** deep plum with faint gingham. The cards are dusky purple.
- **TV screen:** a dark sky with small stars, and the pink sign glows softly.
- **Agents:** they keep their pastel colors. On the dark background their names switch to the pastel itself, so they stay readable, and avatar initials switch to dark ink.
- **Panels:** cash stays blue, approvals stay butter, and resolved stays mint, each in a darker version, so the color-by-job meanings don't change.

It's for late study sessions and for anyone whose eyes are tired, so the team is still pleasant to be with at 1 a.m.

## Small details that keep it trustworthy

- Customer drafts on the board look like **lined notebook paper**, labeled *"Customer draft · not sent"*, so it's clear nothing is ever emailed.
- **Reset database** asks for confirmation and is disabled while agents are working.
- If the backend is down, a friendly banner gives the exact `uvicorn` command to start it.
- `?ticket=102` in the URL opens the board with that ticket selected.
