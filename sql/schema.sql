-- Headway M0-T3 — schema.
--
-- The register is the whole basis of the project's claim: a prediction was
-- recorded before its outcome existed. That claim is worth exactly as much as
-- the guarantee that nobody edited it afterwards, which is why the ingest role
-- is denied UPDATE and DELETE by grant (grants.sql) rather than by convention,
-- and why the milestone fails if an attempted violation succeeds.

DROP TABLE IF EXISTS matches, arrivals, vehicle_events, predictions_register, coverage CASCADE;

-- ---------------------------------------------------------------- the register
-- Append-only. One row per prediction observed, exactly as published.
-- `observed_at` is OUR clock: the moment we received it. It is what makes the
-- prediction provably prior to the outcome.
CREATE TABLE predictions_register (
    id                    bigserial PRIMARY KEY,
    observed_at           timestamptz NOT NULL,
    trip_id               text        NOT NULL,
    stop_id               text        NOT NULL,
    route_id              text        NOT NULL,
    arrival_time          timestamptz,          -- null at terminals: departures only
    arrival_uncertainty   integer,              -- the agency's own error bar, seconds
    stop_sequence         smallint,
    schedule_relationship text,
    -- A prediction whose arrival is not in the future when we saw it cannot be
    -- graded honestly. Recorded, but flagged by this constraint rather than
    -- silently averaged in.
    CONSTRAINT arrival_after_observation
        CHECK (arrival_time IS NULL OR arrival_time > observed_at - interval '60 seconds')
);
CREATE INDEX preds_trip_stop_idx ON predictions_register (trip_id, stop_id);
CREATE INDEX preds_observed_idx  ON predictions_register (observed_at);

-- ------------------------------------------------------------- vehicle events
-- The observation stream that establishes arrivals. Both clocks are kept:
-- `feed_updated_at` is the MBTA's, `observed_at` is ours. M0-T4 showed the
-- first is ~20s coarse and the second ~4s, and that the first is the binding
-- constraint — so discarding either would destroy the ability to say so.
CREATE TABLE vehicle_events (
    id              bigserial PRIMARY KEY,
    observed_at     timestamptz NOT NULL,
    feed_updated_at timestamptz,
    vehicle_id      text NOT NULL,
    trip_id         text,
    stop_id         text,
    route_id        text,
    status          text NOT NULL,
    stop_sequence   smallint
);
CREATE INDEX veh_trip_stop_idx ON vehicle_events (trip_id, stop_id);
CREATE INDEX veh_observed_idx  ON vehicle_events (observed_at);

-- ------------------------------------------------------------------- arrivals
-- Derived. Arrival is the MIDPOINT of the bracket, per PREREGISTRATION.md §1 —
-- never the first STOPPED_AT, which is the upper end of a ~20s bracket and
-- manufactures systematic lateness.
CREATE TABLE arrivals (
    trip_id        text        NOT NULL,
    stop_id        text        NOT NULL,
    bracket_lower  timestamptz NOT NULL,   -- last seen not yet stopped
    bracket_upper  timestamptz NOT NULL,   -- first seen stopped
    arrival_at     timestamptz NOT NULL,   -- midpoint
    bracket_width  real        NOT NULL,   -- seconds; the per-arrival precision
    PRIMARY KEY (trip_id, stop_id),
    CONSTRAINT bracket_ordered CHECK (bracket_upper >= bracket_lower)
);
CREATE INDEX arrivals_width_idx ON arrivals (bracket_width);

-- -------------------------------------------------------------------- matches
CREATE TABLE matches (
    prediction_id bigint  NOT NULL REFERENCES predictions_register(id),
    trip_id       text    NOT NULL,
    stop_id       text    NOT NULL,
    horizon_s     real    NOT NULL,   -- predicted arrival minus observed_at
    error_s       real    NOT NULL,   -- actual minus predicted; positive = late
    bracket_width real    NOT NULL,   -- carried so it can be filtered on
    PRIMARY KEY (prediction_id)
);
CREATE INDEX matches_horizon_idx ON matches (horizon_s);

-- ------------------------------------------------------------------- coverage
-- NFR-5. A gap in ingestion looks exactly like a period of punctual service.
-- Publishing coverage alongside every figure is what stops it being read as one.
CREATE TABLE coverage (
    id           bigserial PRIMARY KEY,
    window_start timestamptz NOT NULL,
    window_end   timestamptz NOT NULL,
    polls        integer     NOT NULL,
    expected     integer     NOT NULL,
    errors       integer     NOT NULL DEFAULT 0,
    note         text
);
