"""
Feedback/evaluation metrics used for rollout visibility and debugging.
"""


feedback_metrics = {
    "evaluations_total": 0,
    "evaluations_v2": 0,
    "low_transcript_quality": 0,
    "retries_total": 0,
    "retry_delta_sum": 0.0,
    "retry_improved_count": 0,
    "score_sum_v1": 0.0,
    "score_count_v1": 0,
    "score_sum_v2": 0.0,
    "score_count_v2": 0,
}


def record_evaluation_metrics(evaluation: dict):
    """Track evaluation-version and transcript-quality metrics."""
    feedback_metrics["evaluations_total"] += 1
    score = 0.0
    try:
        score = float((evaluation or {}).get("score", 0) or 0)
    except Exception:
        score = 0.0

    if (evaluation or {}).get("evaluation_version") == "v2":
        feedback_metrics["evaluations_v2"] += 1
        feedback_metrics["score_sum_v2"] += score
        feedback_metrics["score_count_v2"] += 1
    else:
        feedback_metrics["score_sum_v1"] += score
        feedback_metrics["score_count_v1"] += 1
    if "low_transcript_quality" in ((evaluation or {}).get("quality_flags") or []):
        feedback_metrics["low_transcript_quality"] += 1


def record_retry_metrics(delta_score: float):
    """Track retry usage and whether retries improved scores."""
    feedback_metrics["retries_total"] += 1
    try:
        delta = float(delta_score)
        feedback_metrics["retry_delta_sum"] += delta
        if delta > 0:
            feedback_metrics["retry_improved_count"] += 1
    except Exception:
        pass
