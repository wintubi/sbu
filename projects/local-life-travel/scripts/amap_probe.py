"""Optional live probe for the Amap adapter.

Requires AMAP_API_KEY in the environment. It makes a small number of real
requests (POI search, weather, two routes) and prints status/quality only.
It never prints the key and never fabricates a successful result.

Usage:
  $env:AMAP_API_KEY = "<your Web Service key>"
  python scripts/amap_probe.py --city 北京
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.amap_tools import AmapAdapter, AmapClient  # noqa: E402
from app.domain import evaluate_timeline  # noqa: E402

CANDIDATES = ["故宫博物院", "景山公园", "天安门广场"]
STAY_SECONDS = 3600


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", default="北京")
    parser.add_argument("--transport", default="walking", choices=["walking", "driving"])
    args = parser.parse_args()

    key = os.environ.get("AMAP_API_KEY", "").strip()
    if not key:
        print("AMAP_API_KEY is not set. Create a Web Service key in the Amap console, then set the env var.")
        print("No network request was made.")
        return 2

    client = AmapClient(key=key)
    adapter = AmapAdapter(client, city=args.city, transport=args.transport)
    try:
        matched: dict[str, dict] = {}
        for name in CANDIDATES:
            result = adapter.poi_lookup(name)
            payload = result.payload or {}
            print(f"poi {name}: status={result.status.value} match={payload.get('match_status')}")
            if result.status.value != "valid":
                print(f"  error={result.error_code} message={result.message}")
                continue
            if payload.get("match_status") == "matched":
                matched[name] = payload["poi"]
            elif payload.get("match_status") == "ambiguous":
                print(f"  options={len(payload.get('options', []))} (not silently chosen)")

        target = (datetime.now() + timedelta(days=1)).date().isoformat()
        weather = adapter.weather(target)
        print(f"weather {target}: status={weather.status.value} error={weather.error_code}")
        if weather.status.value == "valid":
            print(f"  summary={weather.payload.get('summary')}")

        hours = adapter.hours()
        print(f"hours: status={hours.status.value} windows={len((hours.payload or {}).get('windows', {}))}")

        keys = list(matched)
        matrix = {}
        if len(keys) >= 2:
            for i, a in enumerate(keys):
                for b in keys[i + 1:]:
                    result = adapter.leg(a, b)
                    print(f"leg {a} -> {b}: status={result.status.value}")
                    if result.status.value == "valid":
                        from app.domain import leg_key
                        matrix[leg_key(a, b)] = {
                            "duration_seconds": result.payload["duration_seconds"],
                            "distance_meters": result.payload["distance_meters"],
                            "source_ref": result.source_ref,
                            "fetched_at": result.fetched_at,
                        }

        if len(matched) < 2:
            print("Not enough matched POIs for a timeline; no itinerary quality is claimed.")
            return 1

        start = datetime.fromisoformat(f"{target}T09:00:00+08:00")
        end = start.replace(hour=18)
        request = {
            "city": args.city,
            "date": target,
            "timezone": "Asia/Shanghai",
            "time_window": {"start": start.isoformat(), "end": end.isoformat()},
            "transport": args.transport,
            "candidates": [{"name": name, "stay_seconds": STAY_SECONDS} for name in keys],
        }
        candidate_by_key = {c["name"]: c for c in request["candidates"]}
        poi_by_key = {name: {"provider_poi_id": poi["provider_poi_id"], "name": poi["name"],
                             "evidence_refs": []} for name, poi in matched.items()}
        outcome = evaluate_timeline(
            request=request,
            order=list(matched),
            leg_durations=matrix,
            hours=(hours.payload or {}).get("windows", {}) if hours.status.value == "valid" else {},
            candidate_by_key=candidate_by_key,
            poi_by_key=poi_by_key,
            prior_issues=[],
            degraded=False,
        )
        print(f"quality_status={outcome['quality_status']}")
        print("issue_codes=" + ",".join(sorted({issue["code"] for issue in outcome["issues"]})) if outcome["issues"] else "issue_codes=")
        print("NOTE: live probe only proves these calls; it is not a benchmark or a real-trip guarantee.")
        return 0 if outcome["quality_status"] != "infeasible" else 3
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
