"""Run CUA-Gym's same-instance checks and the template's image readiness probe."""
import ipaddress
import json
import secrets
import subprocess
import sys

sys.path.insert(0, sys.argv.pop(1))
import check_computer_mcp_reset as checker

start = checker.Compose.start
initialize = checker.Compose.__init__


def initialize_networks(self, *args, **kwargs):
    initialize(self, *args, **kwargs)
    ids = subprocess.check_output(["docker", "network", "ls", "-q"], text=True).split()
    networks = json.loads(subprocess.check_output(["docker", "network", "inspect", *ids], text=True))
    used = [ipaddress.ip_network(address["Subnet"], strict=False)
            for network in networks for address in network["IPAM"]["Config"] or []
            if address.get("Subnet")]
    document = json.loads(self.override.read_text())
    configured = {}
    for name in ("default", "gui"):
        while True:
            subnet = ipaddress.ip_network(f"10.253.{secrets.randbelow(256)}.{secrets.randbelow(16)*16}/28")
            if not any(subnet.overlaps(item) for item in used):
                break
        used.append(subnet)
        configured[name] = {"ipam": {"config": [{"subnet": str(subnet)}]}}
    document["networks"] = configured
    self.override.write_text(json.dumps(document) + "\n")


def start_and_verify(self, package):
    identity = start(self, package)
    if (package / "environment/verify-image.sh").is_file():
        self.main("agent", "/usr/local/bin/cua-verify-image",
                  log=self.evidence / "verify-image.log")
    return identity


checker.Compose.start = start_and_verify
checker.Compose.__init__ = initialize_networks
checker.main()
