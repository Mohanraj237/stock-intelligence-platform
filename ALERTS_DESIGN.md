# Alerts Engine — Design Document (WS-6)

> **Status:** Design only — awaiting sign-off before any code.  
> **Author:** Claude Sonnet 4.6 (Phase 3 agent)  
> **Date:** 2026-06-09

---

## 1. Problem Statement

The platform currently has no way to notify a user when a trade-relevant event occurs:
- A live scanner setup crosses the confluence threshold (score ≥ 80)
- An open paper-trade hits its stop-loss or target price
- India VIX crosses a user-defined threshold (e.g. > 20 → "elevated fear")
- PCR for NIFTY/BANKNIFTY crosses a user-defined extreme (e.g. < 0.5 or > 1.5)

Without alerts, users must manually re-run the scanner or check the paper-trade page.
The platform has no background scheduler, no WebSocket server, and no external notification
service. Any alert architecture must work within these constraints.

---

## 2. Constraints

| Constraint | Source |
|-----------|--------|
| No broker/order-routing integration | Phase 2 hard constraint |
| File-based JSON storage only; no database | Hard constraint |
| Do not add a scheduler framework (cron, Celery, APScheduler) | Workstream 5 (append_daily_iv_snapshot reuses existing pattern) |
| Read-only external data sources | Architecture constraint |
| No new external delivery vendor without sign-off | Phase 3 WS-4 constraint |

---

## 3. Proposed Architecture — Minimal v1

### 3.1 Alert Rules (JSON storage)

Rules stored in `storage/config/alert_rules.json`. Each rule is a JSON object:

```json
{
  "id": "rule_abc123",
  "type": "scanner_score",
  "symbol": "NIFTY",
  "condition": "gte",
  "threshold": 80,
  "timeframe": "1d",
  "enabled": true,
  "created_at": "2026-06-09T10:00:00"
}
```

**Supported rule types in v1:**

| type | Triggers when |
|------|--------------|
| `scanner_score` | Confluence score for `symbol` on `timeframe` ≥ threshold |
| `paper_trade_sl` | Any open paper trade for `symbol` hits stop-loss |
| `paper_trade_tp` | Any open paper trade for `symbol` hits target |
| `vix_threshold` | India VIX ≥ or ≤ threshold |
| `pcr_threshold` | PCR OI for `symbol` ≥ or ≤ threshold |

**Alert event (emitted when a rule fires):**

```json
{
  "id": "evt_xyz789",
  "rule_id": "rule_abc123",
  "type": "scanner_score",
  "symbol": "NIFTY",
  "message": "NIFTY 1d confluence score hit 83/100 (Bullish)",
  "value": 83,
  "threshold": 80,
  "fired_at": "2026-06-09T11:35:22",
  "read": false
}
```

Events stored in `storage/data/alert_events.json` (rolling last 200 events).

### 3.2 Delivery: In-App SSE (recommended for v1)

Reuse the existing SSE infrastructure from the live scanner (`/api/live-scanner/scan/stream`).
Add a new endpoint `GET /api/alerts/stream` that:

1. Keeps the connection open (SSE)
2. Every 60 seconds: runs a lightweight "alert check" against all enabled rules
3. If any rule fires, emits a `data: {event}` SSE message
4. Frontend subscribes on mount and shows an in-app toast/banner when an event arrives

**Why SSE (not WebSocket)?**
- Already in use in this codebase; no new protocol/library needed
- Works through the existing ConditionalGZipMiddleware (skip-stream pattern)
- Stateless on reconnect — frontend reconnects automatically on disconnect
- No persistent connection state needed server-side

### 3.3 Frontend Alert Display

**Toast notifications** using the existing `sonner` library (already in `dependencies`):
```typescript
// On SSE event received:
toast.success(`NIFTY: Confluence score 83/100 (Bullish, 1d)`)
toast.warning(`VIX crossed 20 — elevated fear`)
toast.error(`NIFTY CE 24000: Stop-loss hit at ₹45`)
```

**Alert bell** icon in the top-right header showing unread count.
**Alerts page** (`/alerts`) listing recent fired events with read/dismiss.
This would be the 14th F&O page (add to `FO_NAV_ROUTES` in `nav-config.ts`).

### 3.4 Alert Check Logic

The alert-check function runs inside the SSE stream coroutine (no separate process):

```python
async def check_alerts(rules: list[dict]) -> list[dict]:
    events = []
    for rule in rules:
        if not rule.get("enabled"):
            continue
        if rule["type"] == "scanner_score":
            # Run a quick single-symbol confluence score (already have this)
            ...
        elif rule["type"] == "vix_threshold":
            # Single API call to /api/allIndices
            ...
        elif rule["type"] in ("paper_trade_sl", "paper_trade_tp"):
            # Compare against paper_trade_service.update_all_prices() result
            ...
    return events
```

---

## 4. API Surface (v1)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/alerts/stream` | SSE stream — emits alert events when rules fire |
| GET | `/api/alerts/rules` | List all alert rules |
| POST | `/api/alerts/rules` | Create an alert rule |
| DELETE | `/api/alerts/rules/{id}` | Delete a rule |
| GET | `/api/alerts/events` | Recent fired events (last 200) |
| POST | `/api/alerts/events/{id}/read` | Mark event as read |
| DELETE | `/api/alerts/events` | Clear all events |

---

## 5. External Delivery (deferred to v2)

| Channel | Complexity | Requires |
|---------|-----------|---------|
| Browser push notifications | Medium | Service worker + VAPID keys |
| Email | Medium | SMTP config or Mailgun/SendGrid (new vendor) |
| Telegram | Low | Bot token (new vendor, read-only flow) |
| WhatsApp | High | Official Business API (paid) |

**Recommendation:** Start with in-app SSE (v1). Add Telegram bot as v2 (lowest friction: one
config value, no server-side infrastructure). Requires sign-off because it introduces a new
external vendor dependency.

---

## 6. Effort Estimate

| Component | Effort |
|-----------|--------|
| `storage/config/alert_rules.json` schema + CRUD service | 2h |
| `storage/data/alert_events.json` service | 1h |
| `/api/alerts/*` router (7 endpoints) | 3h |
| Alert check logic (5 rule types) | 4h |
| SSE stream endpoint + check loop | 2h |
| Frontend: SSE subscription + sonner toasts | 2h |
| Frontend: Alert bell + `/alerts` page | 3h |
| Tests (mock NSE/YF, rule fire assertions) | 3h |
| **Total** | **~20h** |

---

## 7. Recommendation

**Proceed with v1 (in-app SSE alerts)** before any external delivery. This delivers the
highest-value capability (timely notification while the platform is open) with zero new
external dependencies and reuse of existing SSE infrastructure.

**Sign-off needed on:**
1. The 5 rule types listed in §3.1 — are these the right ones for v1?
2. The 60-second poll interval for the SSE check loop.
3. Whether Telegram v2 should be scoped for the next phase.
