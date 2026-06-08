"""
Forgewright Manufacturing CNC Tool-Wear Analysis

Starter scaffold. Fill in the stages. You're free to restructure entirely —
this is just a starting point so the repo runs from a single command.

Usage:
    python src/analyze.py
"""

import pandas as pd


def load_data(data_dir: str = "data"):
    """Load the three source files."""
    power = pd.read_csv(f"{data_dir}/power.csv")
    vibration = pd.read_csv(f"{data_dir}/vibration.csv")
    production_log = pd.read_csv(f"{data_dir}/production_log.csv")
    return power, vibration, production_log


def explore(power, vibration, production_log):
    """
    Look at the data before doing anything else.
    """
    pass


def integrate(power, vibration, production_log):
    """
    Combine the three sources so you can compute per-job metrics.
    """
    pass


def compute_job_metrics(integrated):
    """
    For each job: average power draw, peak vibration, and whatever else you
    need to assess tool wear.
    """
    pass


def detect_tool_wear(job_metrics):
    """
    Identify jobs with elevated vibration relative to power.
    Return a ranked list.
    """
    pass


def main():
    power, vibration, production_log = load_data()
    explore(power, vibration, production_log)
    integrated = integrate(power, vibration, production_log)
    job_metrics = compute_job_metrics(integrated)
    wear = detect_tool_wear(job_metrics)
    print("Done. Remember to save your job summary and tool-wear findings to output/.")


if __name__ == "__main__":
    main()
