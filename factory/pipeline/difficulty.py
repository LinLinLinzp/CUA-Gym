"""Verify the declared simple-score allowance against the packaged grader."""

import math


MAX_SIMPLE_SCORE = 0.35
WEAK_PATHS = {"bypass", "one_core", "false_completion"}
CONSTRAINT_TYPES = {
    "scope", "mapping", "calculation", "time", "authority", "duplicates",
    "exceptions", "delivery", "protection",
}


def _check_ids(ids, weights, label, *, allow_empty=False):
    if (not isinstance(ids, list) or not all(isinstance(key, str) for key in ids)
            or len(set(ids)) != len(ids) or not set(ids) <= weights.keys()
            or (not ids and not allow_empty)):
        raise ValueError(f"Invalid or unknown checkpoint IDs in {label}")


def _check_report(report, weights, name):
    points = []
    for check in report["checks"]:
        key, weight, score = check["id"], check["weight"], check["score"]
        if weight != weights[key] or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError(f"Difficulty fixture {name} has inconsistent checkpoint {key}")
        points.append(weight * score)
    score = math.fsum(points) / math.fsum(weights.values())
    if not math.isclose(report["reward"], score, abs_tol=0.00005):
        raise ValueError(f"Difficulty fixture {name} must use additive business-result scores")
    return score


def check_difficulty_review(rubric, reports):
    review = rubric.get("difficulty_review")
    if review is None:
        return None
    weights = {row["id"]: row["weight"] for row in rubric["checkpoints"]}
    if not all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in weights.values()):
        raise ValueError("Difficulty review requires finite positive checkpoint weights")
    for name, expected in (("golden", 1.0), ("nop", 0.0)):
        if name not in reports or _check_report(reports[name], weights, name) != expected:
            raise ValueError(f"Difficulty review needs {name} to score {expected}")
    simple = review["simple_checks"]
    _check_ids(simple, weights, "simple_checks", allow_empty=True)
    simple_score = math.fsum(weights[key] for key in simple) / math.fsum(weights.values())
    if simple_score > MAX_SIMPLE_SCORE:
        raise ValueError(f"Simple checkpoints total {simple_score:.4f}, above {MAX_SIMPLE_SCORE:.2f}")
    weak = review["weak_fixtures"]
    if weak.keys() != WEAK_PATHS or len(set(weak.values())) != len(WEAK_PATHS):
        raise ValueError("Supply distinct bypass, one_core and false_completion fixtures")
    missing = set(weak.values()) - reports.keys()
    if missing:
        raise ValueError(f"Missing executed difficulty fixtures: {', '.join(sorted(missing))}")
    scores = {}
    for path, name in weak.items():
        score = _check_report(reports[name], weights, name)
        # Reports store per-check and total scores at four decimal places.
        if round(score, 4) > MAX_SIMPLE_SCORE:
            raise ValueError(f"Difficulty path {path} scored {score:.4f}, above {MAX_SIMPLE_SCORE:.2f}")
        scores[path] = reports[name]["reward"]

    categories = review["constraints"]
    if len(categories) < 4 or not categories.keys() <= CONSTRAINT_TYPES:
        raise ValueError("Supply at least four distinct business constraint categories")
    counterexamples = set()
    for category, test in categories.items():
        ids, fixture = test["checks"], test["fixture"]
        _check_ids(ids, weights, category)
        if fixture not in reports or fixture in counterexamples:
            raise ValueError(f"Constraint {category} needs its own executed counterexample")
        counterexamples.add(fixture)
        report = reports[fixture]
        _check_report(report, weights, fixture)
        if not any(row["id"] in ids and row["score"] < 1 for row in report["checks"]):
            raise ValueError(f"Constraint {category} has no score change in fixture {fixture}")
        if not any(row["id"] not in ids and row["score"] == 1 for row in report["checks"]):
            raise ValueError(f"Constraint {category} must preserve an unrelated checkpoint in fixture {fixture}")
    return {"simple_score": simple_score, "weak_path_scores": scores,
            "constraint_categories": sorted(categories)}
