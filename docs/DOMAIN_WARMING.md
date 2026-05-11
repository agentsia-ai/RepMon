# Domain warming (operator guide)

## Why it matters

Mailbox providers infer **domain and IP reputation** from observed sending patterns. A brand-new domain that blasts cold mail looks like abuse; messages land in spam or are throttled.

## What “warming” means

Start with **low daily volume**, send only to **engaged recipients**, and increase volume gradually so providers see consistent, low-complaint behavior over **weeks**, not days.

## RepMon `WarmupPlan`

The AI advisor proposes a **day-by-day send target** and Markdown guidance. Echo (or your persona) should tune the narrative; the engine stores the structured JSON targets in SQLite.

## Signals that help

- Replies and meaningful engagement  
- Low spam complaints  
- “Not spam” recoveries (where measurable)  
- Stable SPF/DKIM/DMARC alignment (check DMARC reports)

## Timelines

Expect **2–6 weeks** before a new domain behaves like a “known good” sender for cold outreach — longer if lists are cold or content is promotional.

## How to verify

- [mail-tester.com](https://www.mail-tester.com) — quick DNS / content sanity  
- [MXToolbox](https://mxtoolbox.com) — blacklist and DNS checks  
- **DMARC aggregate reports** ingested via RepMon (`repmon dmarc`, MCP `get_dmarc_summary`)

Treat warming plans as **starting points**; your list quality and offer relevance dominate outcomes.
