# SupportPilot Metrics Report

Generated from local SQLite results.

## Executive Summary

Few-shot changed category accuracy by -2.5 percentage points and average token usage by 388 tokens per ticket versus zero-shot.

Majority-class baseline accuracy is 20.0% by always predicting `Billing inquiry`.

Cost profile: `groq`.

## Variant Metrics

| variant   |   tickets | category_accuracy   | priority_accuracy   |   avg_confidence | escalation_rate   |   avg_latency_ms |   avg_tokens | total_estimated_cost_usd   |
|:----------|----------:|:--------------------|:--------------------|-----------------:|:------------------|-----------------:|-------------:|:---------------------------|
| few_shot  |       200 | 18.0%               | 22.5%               |             0.84 | 4.0%              |             7415 |          928 | $0.0000                    |
| zero_shot |       200 | 20.5%               | 22.0%               |             0.94 | 0.0%              |             3706 |          540 | $0.0000                    |

## Per-Category Accuracy

| true_category        | variant   |   tickets | category_accuracy   |   avg_confidence |
|:---------------------|:----------|----------:|:--------------------|-----------------:|
| Billing inquiry      | few_shot  |        40 | 0.0%                |             0.84 |
| Billing inquiry      | zero_shot |        40 | 0.0%                |             0.94 |
| Cancellation request | few_shot  |        40 | 0.0%                |             0.86 |
| Cancellation request | zero_shot |        40 | 0.0%                |             0.95 |
| Product inquiry      | few_shot  |        40 | 15.0%               |             0.85 |
| Product inquiry      | zero_shot |        40 | 10.0%               |             0.95 |
| Refund request       | few_shot  |        40 | 0.0%                |             0.83 |
| Refund request       | zero_shot |        40 | 0.0%                |             0.94 |
| Technical issue      | few_shot  |        40 | 75.0%               |             0.83 |
| Technical issue      | zero_shot |        40 | 92.5%               |             0.94 |

## Prediction Distribution

| variant   | pred_category   |   tickets | share   |
|:----------|:----------------|----------:|:--------|
| few_shot  | Technical issue |       168 | 84.0%   |
| few_shot  | Product inquiry |        32 | 16.0%   |
| zero_shot | Technical issue |       185 | 92.5%   |
| zero_shot | Product inquiry |        15 | 7.5%    |

## Confusion Matrix Rows

| variant   | true_category        | pred_category   |   tickets |
|:----------|:---------------------|:----------------|----------:|
| few_shot  | Billing inquiry      | Technical issue |        34 |
| few_shot  | Billing inquiry      | Product inquiry |         6 |
| few_shot  | Cancellation request | Technical issue |        37 |
| few_shot  | Cancellation request | Product inquiry |         3 |
| few_shot  | Product inquiry      | Technical issue |        34 |
| few_shot  | Product inquiry      | Product inquiry |         6 |
| few_shot  | Refund request       | Technical issue |        33 |
| few_shot  | Refund request       | Product inquiry |         7 |
| few_shot  | Technical issue      | Technical issue |        30 |
| few_shot  | Technical issue      | Product inquiry |        10 |
| zero_shot | Billing inquiry      | Technical issue |        35 |
| zero_shot | Billing inquiry      | Product inquiry |         5 |
| zero_shot | Cancellation request | Technical issue |        39 |
| zero_shot | Cancellation request | Product inquiry |         1 |
| zero_shot | Product inquiry      | Technical issue |        36 |
| zero_shot | Product inquiry      | Product inquiry |         4 |
| zero_shot | Refund request       | Technical issue |        38 |
| zero_shot | Refund request       | Product inquiry |         2 |
| zero_shot | Technical issue      | Technical issue |        37 |
| zero_shot | Technical issue      | Product inquiry |         3 |

## Notes

- Category and priority accuracy are measured against the source dataset's human labels.
- Escalation rate is the share of tickets with model confidence below the configured threshold.
- Cost is estimated from recorded prompt and completion tokens; Groq development runs are treated as $0 in this report.
- The source descriptions contain substantial generic support-ticket boilerplate, so description-only classification can collapse toward broad issue categories.
