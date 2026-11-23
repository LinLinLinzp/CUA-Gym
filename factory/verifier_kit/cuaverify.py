"""Compatibility entry point for the earlier grading experiments."""

from cuaverify_additive import (  # noqa: F401
    LOG_DIR, OUTPUT_DIR, SETTLE_SECONDS, VAR_DIR, InfraError, amounts,
    changed_items, load_site, mentions, mentions_amount, money_eq, new_items,
    plain, read_csv, run_replay,
)
from cuaverify_additive import Grader as AdditiveGrader
from cuaverify_additive import run as run_additive


class Grader(AdditiveGrader):
    def __init__(self, task_id: str, version: str):
        super().__init__(task_id, version)
        self.caps = []

    def gate(self, cap: float = 0.3):
        """Apply the L01 rule to a legacy task."""
        failed = [check["id"] for check in self.checks if check["core"] and check["score"] < 1]
        if failed:
            self.cap(cap, f"core checks not all passed: {failed}")

    def cap(self, limit: float, reason: str):
        self.caps.append({"limit": limit, "reason": reason})

    def reward(self) -> float:
        return round(min([super().reward()] + [cap["limit"] for cap in self.caps]), 4)

    def report(self, reward: float) -> dict:
        return {**super().report(reward), "caps": self.caps}

    def finish(self):
        for cap in self.caps:
            print(f"CAP {cap['limit']}: {cap['reason']}")
        return super().finish()


def run(task_id: str, version: str, evaluate):
    return run_additive(task_id, version, evaluate, grader_type=Grader)
