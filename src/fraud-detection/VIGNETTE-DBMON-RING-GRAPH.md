# Vignette — Ring-Graph slow query (SQL Server / fraud-detection)

## Alpha

> NOTE: until version 2.0.7 is released in production, you can run this demo
> in **workshop** (`https://workshop.splunko11y.com`) or **dev-astronomy**
> (`https://dev-astronomy.splunko11y.com`) which sends telemetry to eu0.
> (Be aware these are development / test environments and can be taken
> down or used for other demos without warning.)

## Intro

**Question:** How do you catch a query that returns the *right* answer, doesn't error, doesn't crash — but takes 6 seconds every single time it runs, and no one on the app team can tell you why?

**Answer:** Database Monitoring in Splunk Observability Cloud — correlated with the APM trace that called it.

## When and Why

The classic query-performance regression: a developer wants a "smarter" fraud check, so instead of matching shipping addresses exactly they wrap both sides of the join in `UPPER(...)` to be case-insensitive and add a `LIKE '%...%'` for good measure. The intent is honest. The result is correct.

But the moment `UPPER()` wraps an indexed column, the optimizer can't use the index anymore. It falls back to a full table scan, forced further by a stray `OPTION (LOOP JOIN)` hint left over from a "let me just force the plan" experiment. What was a millisecond index seek becomes a multi-second scan of every order in the last 30 days. Same result set, hundreds of times more work. Functional tests pass. Load tests didn't cover it. The only sign of trouble is a Kafka consumer that suddenly can't keep up.

This demo shows that regression in the fraud-detection service:

1. **APM** shows the slow fraud-detection process; the `sql-server` DB span under the Kafka consume trace is where the latency lives.
2. **Database Monitoring** shows the offending query, its execution plan, and the top-query metrics that expose the anti-pattern.
3. *(WIP)* **APM ↔ DBMon correlation** connects the two — the trace tells you a database call was slow; DBMon tells you why.

**Takeaway:** code review catches logic bugs; performance regressions need telemetry. DBMon plus APM turns a "fraud pipeline is behind on lag" ticket into a one-click root cause.

## Pre-requisites

**Always on:**

- Login to US Splunk Show / EU Splunk Show using Unified Identity — use your Cisco email address

**On demand via the Observability Portfolio Demo (DIAB) on Splunk Show:**

- Start your instance via Splunk Show. Once running, open the demo management UI
- Start the Unified Observability demo that deploys the Splunk version of the Astronomy Shop

**All platforms:**

- Database Monitoring visible in the APM menu
- Verify you can see a **SQL Server** database named `astronomy-shop-us` / `astronomy-shop-eu` (or your DIAB instance) in the Overview
- Superpowers enabled in Settings → Superpowers:
  - `dbMonitoring`
  - `dbMonAiAssitant`
  - `dbmonEnhancedFilters`

## The Ring-Graph anti-pattern

### 1. Locate the slow service

In the APM Service Map, find `fraud-detection`. The `sql-server-fraud` database node underneath it should show a red latency badge in the 4–8 second range.

> **Say:** "The fraud pipeline just started getting behind on Kafka lag. Consumer group's still up, no errors, no restarts. Looking at the Service Map, the link between fraud-detection and its SQL Server is showing a red number — that's the latency on that call, somewhere between 5 and 7 seconds. That's absurd for a fraud check that runs once per order, so let's follow it and see what the database is actually being asked to do."

### 2. Open Database Monitoring

Click **APM → Database Monitoring → Overview**.

Filter down to **SQL Server** instances, and optionally to your deployment via the `deployment.environment` filter.

> **Say:** "This is the Database Monitoring overview — where we start when we suspect a slow service is actually a slow database. Every instance the collector picks up, across database types, ranked by total query time.
>
> For this demo we care about the SQL Server instance behind fraud-detection. Let's click into it."

### 3. Find the offending query

Click into the `sql-server-fraud` (or your instance) SQL Server link. The Queries pane opens.

Click on the query starting with:

```sql
SELECT COUNT(DISTINCT ol2.order_id) AS related_orders
FROM OrderLogs ol1
INNER JOIN OrderLogs ol2
    ON UPPER(REPLACE(ol2.shipping_street, ' ', '')) = UPPER(REPLACE(ol1.shipping_street, ' ', ''))
    OR ol2.shipping_city LIKE ...
```

Average duration ~5 seconds.

> **Say:** "This view shows every query hitting the database, ranked so the heavy hitters float to the top. Most are running in milliseconds — normal. But the one at the top has a 5-second average on what looks like a related-orders lookup. That's our slow path from the Service Map, and now we know exactly which statement is responsible. Let's click in."

### 4. Look at the plan

The side pane opens with the normalized query statement at the top and the execution plan below.

Pause. Let the audience see both.

> **Say:** "DBMon shows us the query and the execution plan — a step-by-step of how SQL Server answered it. The plan tree calls out where the time is going. See the giant Nested Loops node fed by a Clustered Index Scan? That's SQL Server scanning every row in `OrderLogs`, then per-row evaluating a bunch of string functions to compare each one. Not a seek. Something's off about how this query was written. Let's bring in the AI assistant to explain."

### 5. Summarize

Click the ✨ **Summarize** button at the top of the query statement pane. A summarization panel appears explaining the query in plain English.

> **Say:** "Before diving into the plan, let's get a plain-English read on what this query is even meant to do. The ✨ Summarize button gives us a description — it's counting orders whose shipping address matches the current order's, in the last 30 days. Standard fraud-ring lookup. Knowing what it's *meant* to do makes it much easier to spot what's going wrong."

### 6. AI recommendations

Close the summary. Click the ✨ **AI recommendations** tab.

A side-by-side comparison appears: **Original SQL** on the left, **Optimized SQL** on the right.

> **Say:** "Now for the good part. AI recommendations don't just tell us what's wrong — they propose the fix. On the left is the original with `UPPER(REPLACE(...))` on both sides of the join and a leading-wildcard `LIKE '%city%'`. Textbook non-sargable predicates — the optimizer can't touch the index. On the right is the same query rewritten with a plain equality join on `shipping_street`, letting `idx_shipping_street` do its job.
>
> That's the difference between 5 seconds and 20 milliseconds. Same rows returned, same fraud signal. The kind of suggestion you'd hand straight back to whoever wrote the query."

### 7. Full remediation

Scroll down and expand the **Recommendations** panel. AI lists detailed findings.

> **Say:** "This is where the AI shows its full working. The first recommendation — **remove the function-on-column predicate** — is our sargability killer, spelled out: `UPPER(REPLACE(col, ' ', ''))` prevents the optimizer from using `idx_shipping_street`, forcing a full table scan of a million-row table per query.
>
> Below that: suggestions to drop the `OR ... LIKE '%needle%'` (leading wildcard, also non-sargable), consider a computed column if case-insensitive matching is a real requirement, and re-evaluate the stray `OPTION (LOOP JOIN)` hint that forces the worst join type. We didn't just get a fix — we got a full remediation plan. The kind of thing that would normally take a DBA an afternoon, ready in seconds."

### 8. WIP — Trace correlation

*(Trace ↔ query correlation coming with sqlcommenter integration.)*

### 9. Toggle back to fast

To close the loop live: in flagd-ui at `https://<host>/feature/`, set `fraudDetectionRingGraph` from `slow` to `fast`. Wait 30 seconds. Reload the DBMon Queries pane.

The `UPPER(REPLACE(...))` query drops out of the top-query list. In its place, the fast version (`ON ol2.shipping_street = ol1.shipping_street`) sits at the bottom with a 10–30 ms average.

> **Say:** "And here's the ending we wanted. The bad query is gone from the top of the list. The fixed version is running in tens of milliseconds. Same fraud check, same results, index-seek plan. If you'd shipped this fix via a code change, DBMon would have showed you the win the moment it went live."

## Summary

> "When I talk to teams about Observability, I'm usually helping them answer one question fast: *what's happening in production, and where should we look first?*
>
> Splunk Database Monitoring extends that story down into the data layer, without asking anyone to run a separate query profiler or live in a second product.
>
> We surface slow queries, execution plans, and resource contention inside the same pane as your traces and metrics, using the instrumentation you already run: continuous collection from your databases, correlated back to the services and requests that called them.
>
> The payoff is simple: the database stops being a black box at the end of a span. A slow API call doesn't end at 'something's wrong in SQL Server' — it ends at the specific query, the plan it chose, and the rows it had to touch to get there.
>
> The value I want you to leave with is alignment. When database signal sits inside Observability, a performance regression isn't 'the app team blaming the DBA' or 'the DBA blaming the app team' — it's one trace that shows exactly where the time went.
>
> That's how teams get to a faster, cleaner bridge between application engineers and the people who own the data, because you're no longer translating between two different views of the world."

## Troubleshooting

The demo is driven by a **flagd** setting `fraudDetectionRingGraph` with three variants:

| Variant | Behavior |
|---|---|
| `disabled` | Ring-graph check skipped — no additional query beyond baseline fraud analytics |
| `fast` | Indexed equality join → 10–30 ms per call, uses `idx_shipping_street` |
| `slow` | `UPPER(REPLACE(...)) = ... OR ... LIKE '%...%'` + `OPTION (LOOP JOIN, MAXDOP 1)` → 4–8 s per call, full-scan nested loop |

The ring-graph check fires **once per Kafka `orders` message consumed by fraud-detection**, which is typically 1–5 orders per second under normal loadgen. So when the flag is `slow`, expect a slow query in DBMon roughly every second.

If you don't see the slow query as described:

1. **Check flag state** — go to the frontend of your demo and add `/feature` to the URL, or check via flagd directly:
   ```
   kubectl run flagd-probe --rm -i --restart=Never --image=curlimages/curl:8.1.2 -- \
     curl -s -X POST http://flagd:8013/flagd.evaluation.v1.Service/ResolveString \
     -H "Content-Type: application/json" \
     -d '{"flagKey":"fraudDetectionRingGraph","context":{}}'
   ```
   Expect `{"value":"slow", "reason":"STATIC", "variant":"slow"}`.

2. **Verify fraud-detection is consuming** — no query, no DBMon entry:
   ```
   kubectl logs -n default deploy/fraud-detection --tail=20 | grep "🕸️ Ring graph"
   ```
   You should see `Ring graph SLOW: ... wall=NNNNms alert=true` lines.

3. **Verify OrderLogs is seeded** — slow query needs data to be slow. On pod startup a daemon thread inserts synthetic rows until `OrderLogs` has ≥ 1_000_000 rows. Check:
   ```
   kubectl logs -n default deploy/fraud-detection | grep "Ring graph seed"
   ```
   Should show `Ring graph seed: complete, inserted N synthetic rows` (only on first startup or after cleanup shrank the table below target).

4. **Always-on environments (`workshop`, `dev-astronomy`)** — the `/feature` page may be protected. Reach out to the **`#o11y-demo-environements`** channel in Slack and ask for the flag to be checked or flipped.

5. **DIAB environments** — you own the flag. Set it yourself via the `/feature` UI or by editing the flagd ConfigMap.

## Under the hood

**Service:** `fraud-detection` (Kotlin/Java, `splunk-otel-javaagent`, JDBC auto-instrumentation)
**Database:** SQL Server (`sql-server-fraud`, database `frauddetection`)
**Table:** `OrderLogs` — indexed on `shipping_street`, `shipping_city`, `consumed_at`
**Seed target:** 1_000_000 synthetic rows dated within last 3 days
**Retention:** `DatabaseCleanup` deletes rows > 4 days old every 6 hours
**Cap:** hard ceiling of 1_200_000 rows enforced by `DatabaseCleanup.deleteExcessRows` (keeps slow query wall time bounded regardless of Kafka volume)
**Query code:** `src/fraud-detection/src/main/kotlin/frauddetection/FraudRingGraphCheck.kt`
**Flag definition:** `src/flagd/demo.flagd.json` → `fraudDetectionRingGraph`
