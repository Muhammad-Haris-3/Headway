-- Headway — retention, sampling and aggregation.
--
-- Measured: 197 MB/day against a 0.5 GB tier. Thirty days of full raw would be
-- 5.9 GB. The policy below is what actually fits, decided from the measurement
-- rather than from a guess about what would be convenient.
--
--   full raw            2 days
--   10% trip sample    30 days, with COMPLETE revision chains for sampled trips
--   daily aggregates   forever
--
-- Sampling is by TRIP, not by row. BQ-4 asks whether predictions converge
-- honestly or snap to reality at the last moment, which needs whole revision
-- chains; a sample of scattered rows would answer nothing. A 10% trip sample
-- answers it at reduced power instead of not at all.

-- `matches` was a table costing 73 MB/day and holding nothing that the register
-- and arrivals do not already contain. It becomes a view: same numbers, no bytes.
DROP TABLE IF EXISTS matches CASCADE;

CREATE OR REPLACE VIEW matches AS
SELECT DISTINCT ON (p.id)
       p.id AS prediction_id, p.trip_id, p.stop_id, p.route_id,
       p.observed_at, p.arrival_time, p.arrival_uncertainty,
       EXTRACT(EPOCH FROM (p.arrival_time - p.observed_at))::real AS horizon_s,
       EXTRACT(EPOCH FROM (a.arrival_at   - p.arrival_time))::real AS error_s,
       a.bracket_width
FROM predictions_register p
JOIN arrivals a ON a.trip_id = p.trip_id AND a.stop_id = p.stop_id
WHERE p.arrival_time IS NOT NULL
  AND p.observed_at < a.arrival_at;

-- Deterministic 10% sample. A function rather than a stored list so membership
-- is computable anywhere, by anyone, without carrying state — and so the sample
-- cannot be quietly redrawn later to include a trip whose data turned out to be
-- interesting.
CREATE OR REPLACE FUNCTION is_sampled(trip text) RETURNS boolean AS $$
  SELECT ('x' || substr(md5(trip), 1, 8))::bit(32)::bigint % 10 = 0;
$$ LANGUAGE sql IMMUTABLE;

-- The permanent record. Everything published lives here; everything else is
-- scaffolding that gets sealed and pruned.
CREATE TABLE IF NOT EXISTS daily_metrics (
    day             date    NOT NULL,
    route_id        text    NOT NULL,
    horizon_bucket  text    NOT NULL,   -- '5-10','10-20','20-30' only; §2 of the pre-registration
    n               integer NOT NULL,
    median_error_s  real    NOT NULL,
    mean_error_s    real    NOT NULL,
    p10_error_s     real,
    p90_error_s     real,
    n_with_uncert   integer NOT NULL DEFAULT 0,
    n_contained     integer NOT NULL DEFAULT 0,   -- |error| <= stated uncertainty
    match_rate      real,
    PRIMARY KEY (day, route_id, horizon_bucket)
);

-- Seals. A digest over the rows removed, so their integrity stays checkable by
-- someone with access to neither the database nor the author. The seal cannot
-- prove the rows were correct when written — only that they have not changed
-- since. That is what the append-only grant and the register are for.
CREATE TABLE IF NOT EXISTS seals (
    id            bigserial PRIMARY KEY,
    sealed_at     timestamptz NOT NULL DEFAULT now(),
    covers_day    date        NOT NULL,
    table_name    text        NOT NULL,
    row_count     integer     NOT NULL,
    digest        text        NOT NULL,   -- sha256 over the rows, fixed order
    UNIQUE (covers_day, table_name)
);
