#!/usr/bin/env python3
"""Compatibility entry point for the canonical database-driven audit guide.

The guide is no longer maintained as hard-coded HTML.  This wrapper delegates
to the governed report builder so its logic, metrics, and versions stay aligned
with the SQLite authority and prediction-rule registry.
"""

from __future__ import annotations

from build_prediction_audit_reports import main


if __name__ == "__main__":
    raise SystemExit(main())
