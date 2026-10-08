"""CloudWatch Embedded Metric Format: one JSON log line becomes a metric, no API calls."""
from __future__ import annotations

import json
import time

NAMESPACE = "Chhaon"


def emit(metrics: dict[str, float], dimensions: dict[str, str] | None = None, unit: str = "Count") -> None:
    dims = dimensions or {"Service": "chhaon"}
    doc = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": [list(dims.keys())],
                    "Metrics": [{"Name": k, "Unit": unit} for k in metrics],
                }
            ],
        },
        **dims,
        **metrics,
    }
    print(json.dumps(doc))
