# Write-Up

## Approach

How did you approach the problem? What methods did you choose and why?

As you suggested, I started with EDA to understand the data and the relationships between the variables. After finding and resolving some issues with the data, I addressed the following research questions:

### Research questions
1. Should we use `vibration_peak_mean` along with `vibration_rms_mean`? Answer: no, we can leave `vibration_peak_mean` only. Interestingly, this step didn't expect to find a clue for the tool wear problem, but nevertheless it revealed 11 jobs that turned to be associated with tool wear.
2. How `power_kw_mean` and `vibration_peak_mean` are related from the linear regression perspective? Can we associate outliers with tool wear? Answer: yes, we can. According to the model, $peak = 0.1160 * power + 0.2293$, so if an observed `vibration_peak_mean` exceeds the expected value by more than 0.4527 (a threshold designed in SVM-style manner) we can consider the job to be associated with tool wear. the same 11 jobs from the previous question were indentified as outliers.
3. Does vibrarion depend on the `part_type` and `machine_id` factors? Answer: `machine_id` doesn't seem to be a strong factor while `part_type` indeed has an effect on the model.
4. Can we interpret outliers as tool wear? Answer: yes, we can, roughly. Despite the fact that we can't observe either culumativeness of the wear or extended periods of the surrounding jobs, we can assume that these factors weren't captured by the model that generated this apparently synthetic data.

## Data exploration

What did you find when you looked at the data? How did it shape your approach?

- 0.1 Reversed time. For a few jobs, `start_time` > `end_time` were observed. I simply dropped them.
- 0.2 Time synchronization. Timezones between the `production_log.csv` and `power.csv`/`vibration.csv` were different, so the data didn't join well at first.
- 0.3 Sensor desync. Normally, power sensors generate 2 resords per second while vibration sensors generate 1 record per second. Since it's important to be sure the sensors are synchronized, I checked the amount of unique seconds covered by each sensor in scope of each job and checked that the proportion 1:2 is solid. Few jobs were found that contained such a gap and were dropped from the dataset.
- 0.4 Extreme values. Few negative and None values were observed in `power.csv`. Dropped from the dataset as well.

The visualizations in RQ1 played a key role: they helped reveal the 11 outlying jobs.

## Validation

How did you check that your results are correct?

- Visual inspection (large margins look persuading).
- Consistency check of the RQ1 and RQ2 findings.

## Tool-wear findings

Which jobs show signs of tool wear? How confident are you?

| Job      | Mean power (kW) | Mean peak vibration (g) | Wear score    | Flagged?     |
|----------|-----------------|-------------------------|---------------|--------------|
| job_id   |   power_kw_mean |   vibration_peak_mean   | wear_residual | is_outlier   |
| JOB-104  |        14.4538  |                 4.64731 |      3.00772  | True         |
| JOB-007  |        10.9892  |                 3.55089 |      2.27374  | True         |
| JOB-024  |         9.55349 |                 2.92674 |      1.79979  | True         |
| JOB-206  |        10.9055  |                 3.04867 |      1.78029  | True         |
| JOB-040  |        10.9962  |                 3.01519 |      1.73732  | True         |
| JOB-032  |        11.0439  |                 2.88967 |      1.60681  | True         |
| JOB-120  |         5.63108 |                 2.11342 |      1.39681  | True         |
| JOB-224  |         5.81758 |                 1.86624 |      1.13012  | True         |
| JOB-106  |         4.16353 |                 1.5887  |      1.02562  | True         |
| JOB-018  |         4.49536 |                 1.43923 |      0.84143  | True         |
| JOB-210  |         4.0874  |                 1.362   |      0.806877 | True         |

I'm pretty much confident about these jobs (assumint that that RQ4 doesn't take place) due to the huge margins related to these jobs and due to the consistency of the RQ1 and RQ2 findings.

## What I'd do differently

With more time or more data, what would you change?

- Split the data into training and test sets to evaluate the model's performance.
- Try to use other models. Linear regression can capture linear relationships only.
