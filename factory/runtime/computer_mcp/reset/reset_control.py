#!/usr/bin/env python3
"""Request privileged reset evidence from the in-container PID 1 supervisor."""

import argparse
import json
import os
import socket
import sys

CONTROL = "/run/cua-reset-private/control.sock"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "reset", "manifest"))
    action = parser.parse_args().action
    if os.geteuid() != 0:
        parser.exit(1, "reset controls require container root\n")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(210)
            client.connect(CONTROL)
            client.sendall((action + "\n").encode("ascii"))
            with client.makefile("rb") as stream:
                reply = stream.readline(1024 * 1024 + 1)
        if len(reply) > 1024 * 1024:
            raise ValueError("oversized control reply")
        value = json.loads(reply)
    except (OSError, ValueError):
        parser.exit(1, "reset supervisor did not return a valid response\n")
    print(json.dumps(value, ensure_ascii=True, sort_keys=True))
    return int("error" in value)


if __name__ == "__main__":
    sys.exit(main())
