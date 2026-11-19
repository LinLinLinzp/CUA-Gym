"""Audit a GUI rollout against its native transcript and desktop evidence."""

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct


GUI = "mcp__desktop__computer"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
INLINE_IMAGE = re.compile(r'"media_type"\s*:\s*"image/png"\s*,\s*"data"\s*:\s*"([A-Za-z0-9+/=]+)"')
IMAGE_SOURCE = re.compile(r'\[Image: source: /logs/agent/([^\]\n]+)\]')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def native_events(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("{"):
            yield json.loads(line)


def image_from_observation(observation, agent):
    content = observation.get("content")
    text = content if isinstance(content, str) else json.dumps(content)
    embedded = INLINE_IMAGE.search(text)
    if embedded:
        return base64.b64decode(embedded[1], validate=True)
    ref = IMAGE_SOURCE.search(text)
    if ref:
        path = (agent / ref[1]).resolve()
        require(path.is_relative_to(agent), "Screenshot source is outside the agent directory")
        return path.read_bytes()
    raise ValueError("Tool observation has no recoverable screenshot")


def signature(arguments, png_sha):
    return json.dumps(arguments, sort_keys=True, ensure_ascii=False), png_sha


def verify(trial, evidence, provider_evidence=None):
    agent = (trial / "agent").resolve()
    trajectory_path = agent / "trajectory.json"
    trajectory = load(trajectory_path)
    steps = trajectory["steps"]
    require([step["step_id"] for step in steps] == list(range(1, len(steps) + 1)), "ATIF step IDs are not continuous")
    calls = [call for step in steps for call in step.get("tool_calls", [])]
    observations = [result for step in steps for result in (step.get("observation") or {}).get("results", [])]
    call_ids = [call["tool_call_id"] for call in calls]
    result_ids = [result["source_call_id"] for result in observations]
    require(calls and all(call["function_name"] == GUI for call in calls), "Unexpected or missing tool calls")
    require(len(set(call_ids)) == len(call_ids) and Counter(call_ids) == Counter(result_ids),
            "A tool invocation has missing or duplicate observations")
    native = list(native_events(agent / "claude-code.txt"))
    native_tools = {
        block["id"]: block["name"]
        for event in native if event["type"] == "assistant"
        for block in event["message"]["content"] if block["type"] == "tool_use"
    }
    require(native_tools == dict.fromkeys(call_ids, GUI),
            "ATIF tool IDs or names differ from the native Claude Code transcript")
    native_results = [event for event in native if event["type"] == "result"]
    require(len(native_results) == 1 and native_results[0]["subtype"] == "success"
            and not native_results[0]["is_error"], "Claude Code did not reach a successful native terminal event")
    by_id = {item["source_call_id"]: item for item in observations}
    screenshots = evidence / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    media_index = []
    for index, call in enumerate(calls, 1):
        source = call["tool_call_id"]
        png = image_from_observation(by_id[source], agent)
        require(png.startswith(PNG_MAGIC) and struct.unpack(">II", png[16:24]) == (1280, 800),
                f"{source} returned an unexpected image")
        dest = screenshots / f"{index:03}.png"
        dest.write_bytes(png)
        media_index.append({"source_call_id": source, "arguments": call["arguments"],
                            "png_sha256": hashlib.sha256(png).hexdigest(),
                            "path": str(dest.relative_to(evidence))})
    server_actions = lines(trial / "verifier/terminal-state/actions.jsonl")
    require(Counter(signature(row["arguments"], row["png_sha256"]) for row in server_actions)
            == Counter(signature(row["arguments"], row["png_sha256"]) for row in media_index),
            "ATIF observations differ from desktop actions")
    trial_result = load(trial / "result.json")
    require(not trial_result.get("exception_info"), "Harbor reported a trial exception")
    reward = float((trial / "verifier/reward.txt").read_text())
    summary = {
        "ATIF": trajectory["schema_version"],
        "steps": len(steps),
        "tool_calls": len(calls),
        "tool_call_ids_matching_native_transcript": len(native_tools),
        "screenshots_matching_desktop": len(media_index),
        "actions": dict(Counter(call["arguments"]["action"] for call in calls)),
        "reward": reward,
        "trial": trial.name,
    }
    if provider_evidence is not None:
        gate = lines(provider_evidence / "tool-gate.jsonl")
        model_turns = [row for row in gate if row["route"] == "/v1/messages"]
        require(model_turns and all(row["accepted"] and row["tools"] == [GUI] for row in model_turns),
                "The model-facing tool list differed from the GUI allowlist")
        provider_events = lines(provider_evidence / "provider-events.jsonl")
        require(sum(row["event"] == "response_terminal" for row in provider_events) == len(model_turns),
                "One or more provider turns did not end")
        summary["model_turns_with_only_gui"] = len(model_turns)
    (evidence / "screenshot-index.json").write_text(json.dumps(media_index, indent=2, ensure_ascii=False) + "\n")
    (evidence / "audit.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--provider-evidence", type=Path)
    args = parser.parse_args()
    verify(args.trial, args.evidence, args.provider_evidence)
