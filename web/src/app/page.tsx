"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";

type Status = {
  counts: { predictions: number; vehicle_events: number; arrivals: number; matched_predictions: number };
  window: { first_seen: string | null; last_seen: string | null; days: number };
  threshold: { required_days: number; required_matches: number; days_done: number;
               matches_done: number; days_remaining: number; met: boolean };
  coverage: { windows: number; polls: number; expected: number; errors: number;
              poll_completion: number | null; minutes_covered: number;
              recent: { window_start: string; window_end: string; polls: number;
                        expected: number; errors: number; note: string }[] };
  arrival_precision_seconds: { n: number; median: number | null; p90: number | null;
                               max: number | null; share_within_60s: number | null; note: string };
  match_rate: { in_window: number; matched: number; rate: number | null; note: string };
  withheld: Record<string, string>;
  notices: Record<string, string>;
};

const num = (n: number) => n.toLocaleString();
const secs = (n: number | null) => (n === null ? "—" : `${n.toFixed(1)}s`);

export default function Page() {
  const [d, setD] = useState<Status | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 3500);
    fetch(`${API}/status`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(setD)
      .catch((e) => setErr(String(e)))
      .finally(() => clearTimeout(t));
    return () => clearTimeout(t);
  }, []);

  const pctDays = d ? Math.min(100, (d.threshold.days_done / d.threshold.required_days) * 100) : 0;
  const pctMatch = d ? Math.min(100, (d.threshold.matches_done / d.threshold.required_matches) * 100) : 0;

  return (
    <>
      <div className="eyebrow">01 — Status</div>
      <h1>Nothing is published yet, and that is the point.</h1>
      <p className="lede">
        Headway records the MBTA&rsquo;s arrival predictions before the outcome exists and grades
        them. It is collecting. No accuracy figure appears below, because the threshold for
        publishing one was fixed before any data existed and has not been reached.
      </p>

      {err && (
        <div className="err">
          Could not reach the API. {err}
          <br />
          <span className="small">The free-tier server may be waking up — it can take 30–50 seconds.</span>
        </div>
      )}
      {!d && !err && (
        <div className="load">
          <span className="mono" style={{ letterSpacing: ".18em", textTransform: "uppercase", fontSize: ".7rem" }}>
            loading…
          </span>
          {slow && <p className="small" style={{ marginTop: 14, maxWidth: "44ch" }}>
            The API sleeps when idle on its free tier. First request after a quiet period takes 30–50 seconds.
          </p>}
        </div>
      )}

      {d && (
        <>
          <div className="panel hold">
            <div className="mono" style={{ fontSize: ".6rem", letterSpacing: ".18em", textTransform: "uppercase", color: "var(--hold-text)", marginBottom: 16 }}>
              Withheld until the threshold is met
            </div>
            <p style={{ marginBottom: 10 }}>{d.withheld.error_by_horizon}</p>
            <p className="small" style={{ margin: 0 }}>
              {d.withheld.horizons_under_5_min}
            </p>
          </div>

          <div className="sechead"><span className="n">02</span><h2>Progress to the threshold</h2></div>
          <div className="panel stats">
            <div>
              <div className="v a">{d.threshold.days_done.toFixed(2)}</div>
              <div className="l">of {d.threshold.required_days} days ingesting</div>
              <div className="bar"><div style={{ width: `${pctDays}%` }} /></div>
            </div>
            <div>
              <div className="v a">{num(d.threshold.matches_done)}</div>
              <div className="l">of {num(d.threshold.required_matches)} matched predictions</div>
              <div className="bar"><div style={{ width: `${pctMatch}%` }} /></div>
            </div>
            <div style={{ boxShadow: "none" }}>
              <div className={`v ${d.threshold.met ? "a" : "h"}`}>{d.threshold.met ? "met" : "collecting"}</div>
              <div className="l">{d.threshold.days_remaining.toFixed(1)} days remaining</div>
            </div>
          </div>

          <div className="sechead"><span className="n">03</span><h2>What has been established</h2></div>
          <div className="panel stats">
            <div>
              <div className="v">{secs(d.arrival_precision_seconds.median)}</div>
              <div className="l">arrival precision, median</div>
            </div>
            <div>
              <div className="v">{secs(d.arrival_precision_seconds.p90)}</div>
              <div className="l">precision, 90th percentile</div>
            </div>
            <div style={{ boxShadow: "none" }}>
              <div className="v">{num(d.arrival_precision_seconds.n)}</div>
              <div className="l">arrivals bracketed</div>
            </div>
          </div>
          <p className="note">{d.arrival_precision_seconds.note}</p>

          <div className="sechead"><span className="n">04</span><h2>Coverage and match rate</h2></div>
          <div className="panel stats">
            <div>
              <div className="v">{d.match_rate.rate === null ? "—" : `${(d.match_rate.rate * 100).toFixed(1)}%`}</div>
              <div className="l">match rate ({num(d.match_rate.matched)} of {num(d.match_rate.in_window)})</div>
            </div>
            <div>
              <div className="v">{d.coverage.poll_completion === null ? "—" : `${(d.coverage.poll_completion * 100).toFixed(0)}%`}</div>
              <div className="l">polls completed of intended</div>
            </div>
            <div style={{ boxShadow: "none" }}>
              <div className="v">{num(d.coverage.windows)}</div>
              <div className="l">ingestion windows, {d.coverage.errors} errors</div>
            </div>
          </div>
          <p className="note">
            {d.match_rate.note} A low match rate here reflects gaps between ingestion runs rather
            than a failure to observe: predictions accumulate continuously, vehicle observations
            only while a run is active. Both numbers are published together so one cannot be read
            without the other.
          </p>

          <div className="panel scroll" style={{ marginTop: 8, padding: 0 }}>
            <table>
              <thead>
                <tr><th>Window start</th><th className="r">Polls</th><th className="r">Intended</th><th className="r">Errors</th><th>Source</th></tr>
              </thead>
              <tbody>
                {d.coverage.recent.map((c, i) => (
                  <tr key={i}>
                    <td className="m">{new Date(c.window_start).toISOString().replace("T", " ").slice(0, 19)}</td>
                    <td className="m r">{c.polls}</td>
                    <td className="m r">{c.expected}</td>
                    <td className="m r">{c.errors}</td>
                    <td className="m" style={{ color: "var(--faint)" }}>{c.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="sechead"><span className="n">05</span><h2>The record so far</h2></div>
          <div className="panel stats">
            <div><div className="v">{num(d.counts.predictions)}</div><div className="l">predictions recorded</div></div>
            <div><div className="v">{num(d.counts.vehicle_events)}</div><div className="l">vehicle observations</div></div>
            <div style={{ boxShadow: "none" }}><div className="v">{num(d.counts.arrivals)}</div><div className="l">arrivals observed</div></div>
          </div>
          <p className="note">
            Predictions are written to an append-only register: the ingesting role holds no{" "}
            <span className="mono">UPDATE</span> or <span className="mono">DELETE</span>, enforced by
            database grant and tested by attempting both. That is what makes &ldquo;recorded before
            the outcome existed&rdquo; a claim rather than a promise.
          </p>
        </>
      )}
    </>
  );
}
