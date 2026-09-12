# Data Documentation

Home for AlphaDex Scout's data model documentation:

- **Metric definitions** — precise meaning and units of each metric, preserving the
  distinctions Fees ≠ Revenue ≠ Holders Revenue ≠ Price Appreciation.
- **Data model** — entities, historical observations, and indexes
  (see `docs/decisions/ADR-004`).
- **Missing-data semantics** — `UNKNOWN` / `NOT_AVAILABLE` / `NOT_APPLICABLE`
  (see `docs/decisions/ADR-003`).
- **Provenance** — provider, timestamp, period, source status, freshness recorded
  per observation.

---

## Data model

- **`assets`** — one row per crypto asset in the scannable universe
  (`symbol`, `name`, optional `category`).
- **`asset_source_ids`** — maps a provider's own asset id to an internal asset:
  `(provider, external_id)` is unique. Asset identity is resolved by this mapping,
  **never by the ambiguous symbol**, so symbol collisions and duplicate listings
  across providers cannot merge two distinct assets (AGENTS.md §13).
- **`metric_observations`** — append-only observations (ADR-004). Each row is
  `(asset, metric, value, value_status, unit, period, observed_at, provenance…)`.
  "Current value" is a query over this history, not a stored field. A check
  constraint enforces that a numeric `value` is present **iff** `value_status = OK`
  (ADR-003) — missing data is never stored as `0`.
- **`ingestion_runs`** — run-level record of each ingestion cycle
  (`provider`, `status`, counts, timing, error) for observability (AGENTS.md §8).

### Missing-data semantics (ADR-003)

| `value_status`  | Meaning                                             | `value` |
|-----------------|-----------------------------------------------------|---------|
| `OK`            | A real, observed value                              | present |
| `UNKNOWN`       | Value exists but could not be obtained              | `NULL`  |
| `NOT_AVAILABLE` | Provider does not supply / did not report it        | `NULL`  |
| `NOT_APPLICABLE`| The metric does not apply to this asset             | `NULL`  |

---

## Market metrics (Sprint 02)

Market metrics live under the `market.*` namespace. They describe **price and
market state only** — they are not fundamentals (Fees/Revenue/TVL) and must never
be conflated with them (AGENTS.md §9). Each observation records its `unit`,
`period`, and provenance.

| Metric                                 | Unit     | Period | Meaning |
|----------------------------------------|----------|--------|---------|
| `market.price_usd`                     | USD      | point  | Spot price per token in USD. |
| `market.market_cap_usd`                | USD      | point  | Circulating market capitalization. |
| `market.fully_diluted_valuation_usd`   | USD      | point  | Valuation at max/total supply (FDV). |
| `market.total_volume_usd`              | USD      | 24h    | Trading volume over the trailing 24h. |
| `market.circulating_supply`            | tokens   | point  | Tokens currently in circulation. |
| `market.total_supply`                  | tokens   | point  | Total tokens that exist. |
| `market.max_supply`                    | tokens   | point  | Maximum tokens that can ever exist (often absent → `NOT_AVAILABLE`). |
| `market.price_change_pct_24h`          | percent  | 24h    | Price change % over the trailing 24h. |
| `market.price_change_pct_7d`           | percent  | 7d     | Price change % over the trailing 7 days. |
| `market.price_change_pct_30d`          | percent  | 30d    | Price change % over the trailing 30 days. |
| `market.market_cap_rank`               | rank     | point  | Rank by market capitalization (1 = largest). |

> Market cap and price appreciation are **market** signals. A rising price is not
> evidence of improving fundamentals — that distinction is the whole point of the
> system (AGENTS.md §1).

---

## Fundamental metrics (Sprint 03)

Fundamental metrics live under the `fundamental.*` namespace and describe a
**protocol's economics** — the "is the protocol becoming stronger?" signal. They
are kept **strictly distinct** from one another and from `market.*` price data:
**Fees ≠ Revenue ≠ Holders Revenue ≠ TVL ≠ Price** (AGENTS.md §9). They are never
summed, averaged, or derived from one another.

| Metric                                   | Unit | Period | Meaning |
|------------------------------------------|------|--------|---------|
| `fundamental.tvl_usd`                    | USD  | point  | Total value locked in the protocol. |
| `fundamental.fees_usd.24h`               | USD  | 24h    | Total fees paid by users over the trailing 24h. |
| `fundamental.fees_usd.7d`                | USD  | 7d     | Total fees over the trailing 7 days. |
| `fundamental.fees_usd.30d`               | USD  | 30d    | Total fees over the trailing 30 days. |
| `fundamental.revenue_usd.24h`            | USD  | 24h    | Revenue kept by the protocol over 24h (a subset of fees). |
| `fundamental.revenue_usd.7d`             | USD  | 7d     | Protocol revenue over 7 days. |
| `fundamental.revenue_usd.30d`            | USD  | 30d    | Protocol revenue over 30 days. |
| `fundamental.holders_revenue_usd.24h`    | USD  | 24h    | Revenue directed to token holders over 24h. |
| `fundamental.holders_revenue_usd.30d`    | USD  | 30d    | Holders-revenue over 30 days. |

> **Fees** are what users pay; **Revenue** is the portion the protocol keeps;
> **Holders Revenue** is the portion routed to token holders. A protocol can have
> large fees but little revenue, or revenue that does not reach holders — those are
> exactly the distinctions that determine whether protocol strength accrues to the
> token (AGENTS.md §1, distinctions #1–#2). Many protocols report some of these but
> not others; the unreported ones are stored as `NOT_AVAILABLE`, never `0`.

### Asset ↔ protocol matching (Phase 1)

Fundamentals are matched to assets **already in the market universe** by
`gecko_id` — the provider-neutral key that a DefiLlama protocol shares with its
CoinGecko listing. The matched protocol adds a `(provider="defillama",
external_id=<slug>)` row to `asset_source_ids` pointing to the **same** asset.
Protocols with no in-universe match (or no `gecko_id`) are **skipped and counted**,
not force-created — so every asset carrying fundamentals also has market data.
Broadening coverage to unmatched protocols is deferred to a later version.

### Provenance

Each observation stores `source_provider` (e.g. `coingecko`), `source_timestamp`
(the provider's own timestamp for the data, when supplied), and `source_status`.
Freshness is derived from `observed_at` at read time and exposed by the API as
`age_seconds`.

---

## Providers

Data is fetched behind provider interfaces; a provider's wire shape never leaves
its adapter — everything downstream sees a provider-agnostic snapshot, which
normalization maps into the metrics above.

- **Market data** — `MarketDataProvider`, first concrete provider **CoinGecko**
  (`/coins/markets`) → `RawMarketSnapshot` → `market.*` metrics.
- **Fundamentals** — `FundamentalDataProvider`, first concrete provider
  **DefiLlama** (`/protocols` + `/overview/fees`) → `RawFundamentalSnapshot` →
  `fundamental.*` metrics.
