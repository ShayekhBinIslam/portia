#!/usr/bin/env python3
"""portia/scripts/deploy_fireworks.py: Muse Glimmer 30B on a Fireworks on-demand deployment for Portia.

    FIREWORKS_API_KEY=... FIREWORKS_ACCOUNT=<account-id> python scripts/deploy_fireworks.py create
    FIREWORKS_API_KEY=... FIREWORKS_ACCOUNT=<account-id> python scripts/deploy_fireworks.py delete <deployment-id>

Glimmer is not served per token on Fireworks, so this creates a deployment from the 1x H200 bf16 shape with 0 to 1
replicas that scales to zero after 5 idle minutes. Fireworks bills it per GPU-second while a replica runs ($8.00 per
hour for an H200; start-up is free). `create` prints the three settings that point Portia at it.
Tested: two investigations right in 78 s and 100 s, then deleted.
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from judge.config import load as config  # noqa: E402  (configs/models.yaml)

FW = config("models")["fireworks"]
API, MODEL = FW["api"], FW["model"]


def main():
    key, acct = os.environ.get("FIREWORKS_API_KEY", ""), os.environ.get("FIREWORKS_ACCOUNT", "")
    if not key or not acct or len(sys.argv) < 2 or sys.argv[1] not in ("create", "delete"):
        sys.exit(__doc__)
    h = {"Authorization": f"Bearer {key}"}
    if sys.argv[1] == "delete":
        name = sys.argv[2] if "/" in sys.argv[2] else f"accounts/{acct}/deployments/{sys.argv[2]}"
        # Fireworks refuses to delete a deployment that served requests in the last hour unless told to skip the check
        r = requests.delete(f"{API}/{name}", params={"ignoreChecks": "true"}, headers=h, timeout=60)
        print("deleted" if r.ok else f"HTTP {r.status_code}: {r.text[:300]}", name)
        return
    match = requests.post(f"{API}/accounts/{acct}/deploymentShapeVersions:match", headers=h, timeout=60,
                          json={"createDeploymentRequest": {"deployment": {"baseModel": MODEL}}}).json()
    shapes = [s for s in match.get("deploymentShapeVersions", [])
              if (s.get("snapshot") or {}).get("acceleratorType") == FW["shape"]["accelerator"] and (s.get("snapshot") or {}).get("precision") == FW["shape"]["precision"]]
    if not shapes:
        sys.exit(f"no {FW['shape']['accelerator']} {FW['shape']['precision']} shape offered for {MODEL}: {json.dumps(match)[:400]}")
    body = {"baseModel": MODEL, "deploymentShape": shapes[0]["name"], "displayName": "portia-glimmer",
            "minReplicaCount": FW["replicas"]["min"], "maxReplicaCount": FW["replicas"]["max"],
            "autoscalingPolicy": {"scaleToZeroWindow": f"{FW['scale_to_zero_seconds']}s"}}
    r = requests.post(f"{API}/accounts/{acct}/deployments", json=body, headers=h, timeout=120)
    if not r.ok:
        sys.exit(f"HTTP {r.status_code}: {r.text[:400]}")
    name = r.json()["name"]
    print("created", name, "from shape", shapes[0]["name"])
    for _ in range(90):                                   # usually ready in about 4 minutes
        state = requests.get(f"{API}/{name}", headers=h, timeout=60).json().get("state")
        if state in ("READY", "FAILED"):
            break
        time.sleep(20)
    print("state:", state)
    print(f"""export PORTIA_GLIMMER_SERVERS='[["https://api.fireworks.ai/inference/v1", "Fireworks"]]'
export PORTIA_GLIMMER_MODEL='{MODEL}#{name}'
export PORTIA_GLIMMER_KEY="$FIREWORKS_API_KEY\"""")


if __name__ == "__main__":
    main()
