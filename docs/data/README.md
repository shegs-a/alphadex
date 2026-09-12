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

### Provenance

Each observation stores `source_provider` (e.g. `coingecko`), `source_timestamp`
(the provider's own timestamp for the data, when supplied), and `source_status`.
Freshness is derived from `observed_at` at read time and exposed by the API as
`age_seconds`.

---

## Providers

Market data is fetched behind the `MarketDataProvider` interface; the first
concrete provider is **CoinGecko** (`/coins/markets`). A provider's wire shape
never leaves its adapter — everything downstream sees the provider-agnostic
`RawMarketSnapshot`, which normalization maps into the metrics above.
