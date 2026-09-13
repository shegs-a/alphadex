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
- **`scan_runs`** — one row per Opportunity Scanner run: timestamp, status,
  `universe_size`, `candidate_count`, and a **snapshot of the screen config**
  (thresholds + weights) used, so a scan's results are reproducible and auditable
  (§10).
- **`scan_results`** — one row per asset per scan: `status`
  (`candidate` / `watch` / `insufficient_data` / `excluded`), `passed`,
  `screen_score` (nullable — a preliminary ordering score, **not** the Alpha
  Score), `rank`, `data_completeness`, and a `reasons` JSON breakdown (per-criterion
  pass/fail with value + threshold, and the score signals). Decision fields are
  typed columns; JSON holds only the explanatory breakdown (§9). A missing score is
  `NULL` with a status explaining why — never `0` (ADR-003). Scan results are
  **derived data**, regenerable by re-running a scan.
- **`divergence_runs`** — one row per Divergence Engine run: timestamp, status,
  `analyzed_count`, `divergence_count`, and a snapshot of the config used.
- **`divergence_signals`** — one row per analyzed asset per run. **Measurement**
  fields (kept distinct — ADR-005): `divergence_gap` (raw `ft − pt`),
  `divergence_score` (blended, signed; a **component**, not the Alpha Score),
  `signal_strength` (magnitude), `fundamentals_trend`, `price_trend`,
  `valuation_trend`, `valuation_level` (the multiple, informational). **Interpretation
  & provenance**: `classification` (`potential_mispricing` / `fundamental_divergence`
  / `fundamental_repricing` / `momentum` / `thesis_weakening` / `watch` /
  `insufficient_data`), `window`, `method` (`growth_window` / `cross_time`),
  `data_quality` (separate from signal strength), `rank`, and an `evidence` JSON (the
  §10 questions + `evidence_strength`). A missing score is `NULL` with a
  classification — never `0`. Signals are **derived data**.
- **`tokenomics_runs` / `tokenomics_signals`** — Token Value Capture (Sprint 06).
  Per asset: distinct component ratios (`float_ratio`, `revenue_to_fees`,
  `holders_to_revenue`, `real_yield`), a `value_capture_score` (nullable — a
  **component**, not the Alpha Score) + `value_capture_label`, a separate
  `data_completeness`, `rank`, and `evidence` JSON. Missing components are `NULL`,
  never `0`. Derived data.
- **`risk_runs` / `risk_assessments`** — the **separate** Risk output (§10, Sprint
  06). Per asset: distinct factors (`liquidity_risk`, `volatility_risk`,
  `dilution_risk`, `size_risk`, `concentration_risk`), a `risk_score` (nullable) +
  `risk_band`, a separate `data_quality`, `rank`, and `evidence` JSON.
  `concentration_risk` is always `NULL` (no on-chain data — a surfaced gap). Derived
  data.

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

---

## Opportunity Scanner (Sprint 04)

The Scanner is the cheap, broad screen at the top of the tiered pipeline (§9). It
reads each asset's latest `market.*` and `fundamental.*` observations and produces a
ranked, explainable candidate set — it decides *what deserves deeper analysis*, not
the final verdict.

**Inclusion gates** (an asset must pass all to be a candidate/watch): market-cap
floor (and optional ceiling), minimum 24h volume, and data freshness. Each gate
records the value and threshold it used, so exclusions are explainable. A missing
required input **fails its gate explicitly** — never scored as `0`.

**Preliminary Screen Score** (ordering only — **not** the Alpha Score): a
configurable weighted blend of a few cheap, single-snapshot signals — `activity`
(30d fees, log-scaled), `liquidity` (24h volume, log-scaled), and `momentum` (30d
price change). A missing signal contributes nothing and lowers `data_completeness`,
so it can never inflate a score. Weights are configurable and must sum to 1.0.

**Classifications:** `candidate` (passed gates, has fundamentals), `watch` (passed
gates, no fundamentals yet), `insufficient_data` (passed gates but fundamentals
required and absent), `excluded` (failed a gate). Only `candidate`/`watch` are
scored and ranked. There is no BUY language (§10).

---

## Economic Divergence Engine (Sprint 05)

The Divergence Engine answers the system's core question (§1): *are fundamentals
improving faster than price/valuation recognizes?* It runs on the Scanner's
candidates and, for each, compares a **fundamentals trend** to a **price/valuation
trend**, using whichever evidence the asset has:

- **Track A — provider growth windows (single snapshot).** From fees over 7d/30d it
  derives an *acceleration* (7d run-rate vs 30d run-rate) and compares it to the
  provider's 30d price change. Works immediately, no accumulated history needed.
- **Track B — cross-time from the append-only history (preferred).** When two
  observations of a metric exist at least `min_history_days` apart, it computes the
  change directly from their `observed_at` values — hindsight-free (§10) and
  preferred over Track A when available.

A coarse market-cap-to-annualized-fees multiple is one additional input (a
divergence signal, **not** a valuation verdict — real valuation is a later sprint).

**Measurement vs. interpretation are kept separate** (ADR-005). The signed
**divergence score** (in [-1, 1]) — a weighted blend of the fundamentals-vs-price gap
and, when available, the valuation-multiple change — is a *measurement* (a
**component**, never the Alpha Score). A positive gap does **not** by itself mean an
opportunity. The **classification** interprets the measurement by reading the price
regime:

- `potential_mispricing` — fundamentals improving materially, price declining/stagnant.
- `fundamental_divergence` — fundamentals improving faster than price, price **not**
  already strongly repriced.
- `fundamental_repricing` — fundamentals improving strongly **and** price also rising
  strongly (market may already recognize it).
- `momentum` — price rising strongly without material fundamental support.
- `thesis_weakening` — fundamentals deteriorating materially.
- `watch` / `insufficient_data`.

Classification uses configurable, documented heuristics (a materiality floor, a
stagnant/declining ceiling, and an "already repriced" marker) — not a single
hard-coded cutoff. Every signal carries `data_quality` (separate from signal
strength — never multiplied into the score) and evidence answering *what changed /
why now / what supports / contradicts / invalidates / the major risk*, plus an
`evidence_strength`. No BUY language (§10). Ranking is a preliminary
divergence-*measurement* ranking (largest measured gap), not an opportunity ranking.

---

## Tokenomics & Risk (Sprint 06)

Two distinct assessments run over the Scanner's candidates, both **components/outputs
feeding the Alpha Score** (Sprint 07) — never the Alpha Score themselves.

**Token Value Capture** answers "does protocol strength accrue to the token?": a
**dilution/float** measure (`market_cap / FDV`, or `circulating / max|total` supply)
and **value capture** (`revenue/fees`, `holders_revenue/revenue`, and a real-yield
proxy = annualized holders-revenue / market cap). Fees, Revenue, and Holders Revenue
are read as **distinct** inputs (§9). The `value_capture_score` blends dilution and
value capture over available inputs (renormalized), with a separate
`data_completeness`; missing inputs are explicit, never `0`.

**Risk** is a **separate output** (§10) — a strong divergence with unacceptable risk
is not a top candidate. Distinct factors (each 0..1, higher = riskier): **liquidity**
(low `volume/market_cap` turnover), **volatility** (price-change magnitude),
**dilution** (FDV overhang), **size** (small market cap). **Concentration** is
`NOT_AVAILABLE` (needs on-chain data). The `risk_score` blends available factors into
a `risk_band` (`low`/`moderate`/`elevated`/`high`), with `data_quality` kept separate
— poor data raises uncertainty, never a false low risk. Language is *risk elevated /
risk high*, never BUY (§10).

## Providers

Data is fetched behind provider interfaces; a provider's wire shape never leaves
its adapter — everything downstream sees a provider-agnostic snapshot, which
normalization maps into the metrics above.

- **Market data** — `MarketDataProvider`, first concrete provider **CoinGecko**
  (`/coins/markets`) → `RawMarketSnapshot` → `market.*` metrics.
- **Fundamentals** — `FundamentalDataProvider`, first concrete provider
  **DefiLlama** (`/protocols` + `/overview/fees`) → `RawFundamentalSnapshot` →
  `fundamental.*` metrics.
