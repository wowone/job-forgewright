"""
Forgewright Manufacturing CNC Tool-Wear Analysis

Approach (see src/wear_analysis.ipynb for the exploratory work behind these choices):
1. Clean the inputs: drop jobs with an invalid start/end, drop invalid/implausible
   power readings, infer the log's UTC offset from the data, and drop jobs whose
   window overlaps a vibration-sensor dropout.
2. Join each job to its power/vibration readings and average them.
3. Fit a single `vibration_peak ~ power` model, using only mean_power_kw and
   peak_vibration_g:
   - Fit the line, then look at the *relative* residual (actual vs. predicted,
     as a fraction of predicted) -- relative, not absolute, because the residual
     scale naturally grows with power, which would otherwise mask low-power worn
     jobs behind a flat absolute threshold.
   - Classify jobs with an SVM-style margin threshold: the midpoint between the
     weakest candidate-worn job's relative residual and the strongest baseline
     job's. Refit the line on the baseline jobs only, recompute the margin, and
     repeat until the candidate set stops changing -- so the worn jobs don't
     bias their own baseline. (The very first round has no candidates yet to
     define a margin from, so it seeds on the sign of the residual: anything
     vibrating more than the all-data fit predicts.)
   - `wear_score` = the converged relative residual. `flagged` = wear_score
     clears the final margin threshold.

Usage:
    python src/analyze.py
"""

import os

import numpy as np
import pandas as pd


def load_data(data_dir="data"):
    power = pd.read_csv(f"{data_dir}/power.csv")
    vibration = pd.read_csv(f"{data_dir}/vibration.csv")
    log = pd.read_csv(f"{data_dir}/production_log.csv")

    power["timestamp"] = pd.to_datetime(power["timestamp"])
    vibration["timestamp"] = pd.to_datetime(vibration["timestamp"])
    log["start_time"] = pd.to_datetime(log["start_time"])
    log["end_time"] = pd.to_datetime(log["end_time"])
    return log, power, vibration


def clean_power_readings(power):
    """
    Drop physically-impossible (<= 0) power readings and implausible sentinel/
    error-code values. The implausibility check is a ratio to the median rather
    than an absolute kW ceiling, so it isn't tied to this shift's machine sizes.
    """
    before = len(power)
    valid = power["power_kw"].notnull() & (power["power_kw"] > 0)
    median = power.loc[valid, "power_kw"].median()
    plausible = valid & (power["power_kw"] < 50 * median)
    print(f"power.csv: dropped {before - int(plausible.sum())} invalid/implausible "
          f"power_kw readings out of {before}")
    return power[plausible].reset_index(drop=True)


def infer_utc_offset_hours(log, power, vibration, candidate_hours=range(-14, 15)):
    """
    log['start_time']/['end_time'] are naive local timestamps; power/vibration
    timestamps are tz-aware UTC. Instead of assuming a timezone, find the whole-hour
    offset that makes the most job windows actually overlap that machine's sensor
    coverage -- this is derived from the data so it also works on a held-out shift
    where the offset might differ.
    """
    sensor_ts = pd.concat([
        power[["machine_id", "timestamp"]],
        vibration[["machine_id", "timestamp"]],
    ])
    bounds = sensor_ts.groupby("machine_id")["timestamp"].agg(["min", "max"])
    lo = log["machine_id"].map(bounds["min"])
    hi = log["machine_id"].map(bounds["max"])

    best_hours, best_score = 0, -1
    for h in candidate_hours:
        shifted_start = (log["start_time"] + pd.Timedelta(hours=h)).dt.tz_localize("UTC")
        shifted_end = (log["end_time"] + pd.Timedelta(hours=h)).dt.tz_localize("UTC")
        score = ((shifted_start <= hi) & (shifted_end >= lo)).sum()
        if score > best_score:
            best_hours, best_score = h, score
    return best_hours, best_score


def sensor_gaps_by_machine(power, vibration):
    """
    power/vibration sample at different rates, so raw row counts aren't comparable.
    Compare the set of unique seconds each sensor has at least one reading for, per
    machine, and collapse missing seconds into contiguous runs -- a real dropout,
    not just boundary jitter.
    """
    p_sec = power.assign(sec=power["timestamp"].dt.floor("s"))
    v_sec = vibration.assign(sec=vibration["timestamp"].dt.floor("s"))

    gap_runs = []
    for m in sorted(set(p_sec["machine_id"]) | set(v_sec["machine_id"])):
        p_set = set(p_sec.loc[p_sec["machine_id"] == m, "sec"])
        v_set = set(v_sec.loc[v_sec["machine_id"] == m, "sec"])
        only_power = sorted(p_set - v_set)

        run_start = run_prev = None
        for sec in only_power:
            if run_prev is not None and sec == run_prev + pd.Timedelta(seconds=1):
                run_prev = sec
                continue
            if run_start is not None:
                gap_runs.append({"machine_id": m, "gap_start": run_start, "gap_end": run_prev,
                                  "duration_s": (run_prev - run_start).total_seconds() + 1})
            run_start = run_prev = sec
        if run_start is not None:
            gap_runs.append({"machine_id": m, "gap_start": run_start, "gap_end": run_prev,
                              "duration_s": (run_prev - run_start).total_seconds() + 1})

    return pd.DataFrame(gap_runs, columns=["machine_id", "gap_start", "gap_end", "duration_s"])


def jobs_overlapping_sensor_gaps(log, gap_runs):
    overlaps = pd.Series(False, index=log.index)
    for _, gap in gap_runs.iterrows():
        same_machine = log["machine_id"] == gap["machine_id"]
        overlap = (log["start_time"] <= gap["gap_end"]) & (log["end_time"] >= gap["gap_start"])
        overlaps |= same_machine & overlap
    return overlaps


def join_logs_to_sensors(log, vibration, power):
    """For each job, average the same-machine power/peak-vibration readings inside
    [start_time, end_time]."""
    result_rows = []
    for _, job in log.iterrows():
        v_subset = vibration[
            (vibration["machine_id"] == job["machine_id"]) &
            (vibration["timestamp"] >= job["start_time"]) &
            (vibration["timestamp"] <= job["end_time"])
        ]
        p_subset = power[
            (power["machine_id"] == job["machine_id"]) &
            (power["timestamp"] >= job["start_time"]) &
            (power["timestamp"] <= job["end_time"])
        ]
        result_rows.append({
            "job_id": job["job_id"],
            "vibration_peak_mean": v_subset["vibration_peak_g"].mean(),
            "power_kw_mean": p_subset["power_kw"].mean(),
        })
    return pd.DataFrame(result_rows)


def fit_wear_model(df, max_iter=20):
    """
    A single self-bootstrapping model on vibration_peak_mean and power_kw_mean only:
    1. Fit peak ~ power.
    2. Take the *relative* residual (actual vs. predicted, as a fraction of
       predicted) -- relative, not absolute, because the residual scale grows
       with power, which would otherwise mask worn jobs at low power behind a
       flat absolute threshold.
    3. SVM-style margin: classify with the threshold halfway between the
       weakest candidate-worn job's relative residual and the strongest
       baseline job's. The very first round has no candidates yet to define a
       margin from, so it seeds on the residual's sign (anything vibrating more
       than the all-data fit predicts).
    4. Refit the line on the baseline (non-candidate) jobs only, recompute the
       margin, and repeat until the candidate set stops changing, so worn jobs
       don't bias their own baseline.
    """
    outliers = None
    rel_resid = None
    wear_threshold = None
    for iteration in range(1, max_iter + 1):
        baseline_data = df if outliers is None else df[~df["job_id"].isin(outliers)]
        slope, intercept = np.polyfit(baseline_data["power_kw_mean"], baseline_data["vibration_peak_mean"], 1)

        predicted = slope * df["power_kw_mean"] + intercept
        rel_resid = (df["vibration_peak_mean"] - predicted) / predicted

        if outliers is None:
            wear_threshold = 0.0
        else:
            is_outlier = df["job_id"].isin(outliers)
            nearest_outlier = rel_resid[is_outlier].min()
            farthest_normal = rel_resid[~is_outlier].max()
            wear_threshold = (nearest_outlier + farthest_normal) / 2

        new_outliers = set(df.loc[rel_resid > wear_threshold, "job_id"])
        if new_outliers == outliers:
            break
        outliers = new_outliers
    else:
        print(f"warning: outlier set did not converge after {max_iter} iterations")

    return rel_resid, wear_threshold, slope, intercept, iteration


def main():
    log, power, vibration = load_data()

    invalid_window = log["start_time"] >= log["end_time"]
    print(f"{int(invalid_window.sum())} jobs have end_time <= start_time: "
          f"{log.loc[invalid_window, 'job_id'].tolist()}")
    log_clean = log[~invalid_window].reset_index(drop=True)

    power_clean = clean_power_readings(power)

    offset_hours, matched = infer_utc_offset_hours(log_clean, power_clean, vibration)
    print(f"inferred log -> UTC offset: {offset_hours:+d}h "
          f"({matched}/{len(log_clean)} jobs overlap sensor coverage)")
    log_clean["start_time"] = (log_clean["start_time"] + pd.Timedelta(hours=offset_hours)).dt.tz_localize("UTC")
    log_clean["end_time"] = (log_clean["end_time"] + pd.Timedelta(hours=offset_hours)).dt.tz_localize("UTC")

    gap_runs = sensor_gaps_by_machine(power_clean, vibration)
    gap_overlap = jobs_overlapping_sensor_gaps(log_clean, gap_runs)
    print(f"{int(gap_overlap.sum())} jobs overlap a vibration sensor dropout: "
          f"{log_clean.loc[gap_overlap, 'job_id'].tolist()}")
    log_scoreable = log_clean[~gap_overlap].reset_index(drop=True)

    sensor_means = join_logs_to_sensors(log_scoreable, vibration, power_clean)
    df = log_scoreable.merge(sensor_means, on="job_id", how="left")

    has_readings = df[["vibration_peak_mean", "power_kw_mean"]].notnull().all(axis=1)
    print(f"{int((~has_readings).sum())} jobs had no usable sensor readings in their window")
    no_readings_ids = set(df.loc[~has_readings, "job_id"])
    df_scoreable = df[has_readings].reset_index(drop=True)

    wear_score, wear_threshold, slope, intercept, n_iter = fit_wear_model(df_scoreable)
    print(f"baseline model (converged in {n_iter} iteration(s)): peak = {slope:.4f} * power + {intercept:.4f}")
    print(f"wear_score margin threshold: {wear_threshold:.4f}")

    df_scoreable = df_scoreable.assign(wear_score=wear_score, flagged=wear_score > wear_threshold)

    # One row per job in the original log, including jobs we couldn't score --
    # with a note explaining why, instead of silently dropping them.
    summary = log[["job_id", "machine_id", "part_type"]].copy()
    summary = summary.merge(
        df_scoreable[["job_id", "power_kw_mean", "vibration_peak_mean", "wear_score", "flagged"]],
        on="job_id", how="left",
    )
    summary = summary.rename(columns={"power_kw_mean": "mean_power_kw", "vibration_peak_mean": "peak_vibration_g"})
    summary["flagged"] = summary["flagged"].fillna(False)

    invalid_ids = set(log.loc[invalid_window, "job_id"])
    gap_ids = set(log_clean.loc[gap_overlap, "job_id"])
    notes = pd.Series("", index=summary.index)
    notes[summary["job_id"].isin(invalid_ids)] = "excluded: end_time <= start_time in production log"
    notes[summary["job_id"].isin(gap_ids)] = "excluded: job overlaps a vibration sensor dropout"
    notes[summary["job_id"].isin(no_readings_ids)] = "excluded: no usable sensor readings in job window"
    summary["notes"] = notes

    summary["rank"] = summary["wear_score"].where(summary["flagged"]).rank(ascending=False, method="min")
    summary = summary.sort_values("wear_score", ascending=False, na_position="last").reset_index(drop=True)

    os.makedirs("output", exist_ok=True)
    summary.to_csv("output/job_summary.csv", index=False)

    n_flagged = int(summary["flagged"].sum())
    print(f"\n{n_flagged} / {len(summary)} jobs flagged as showing tool wear")
    print("wrote output/job_summary.csv")


if __name__ == "__main__":
    main()
