"""Supabase query layer using direct HTTP (workaround for local SSL issues)."""
import json
import os
import ssl
import urllib.request
import urllib.parse
from typing import Optional, List

# Support both local .env and Streamlit Cloud secrets
try:
    import streamlit as st
    _secrets = st.secrets
    SUPABASE_URL = _secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
    SUPABASE_KEY = _secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
except Exception:
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _build_qs(params: dict) -> str:
    """Build query string, supporting duplicate keys (e.g., multiple sale_date filters)."""
    parts = []
    for key, val in params.items():
        if isinstance(val, list):
            for v in val:
                parts.append(f"{urllib.parse.quote(str(key))}={urllib.parse.quote(str(v))}")
        else:
            parts.append(f"{urllib.parse.quote(str(key))}={urllib.parse.quote(str(val))}")
    return "&".join(parts)


def _supabase_get_all(path: str, params: Optional[dict] = None) -> List[dict]:
    """Fetch all rows by paginating with offset/limit."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set. "
            "Set them in .streamlit/secrets.toml (local) or Streamlit Cloud secrets."
        )
    params = dict(params) if params else {}
    params["limit"] = 1000
    all_rows = []
    for offset in range(0, 50000, 1000):
        p = dict(params)
        p["offset"] = offset
        url = f"{SUPABASE_URL}/rest/v1/{path}?{_build_qs(p)}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Accept", "application/json")
        try:
            resp = urllib.request.urlopen(req, context=_ctx)
            raw = resp.read().decode()
            rows = json.loads(raw) if raw else []
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < 1000:
                break
        except Exception:
            break
    return all_rows


def query_sales_analysis(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    match_status: Optional[str] = None,
    products: Optional[List[str]] = None,
    payment_channels: Optional[List[str]] = None,
) -> List[dict]:
    """Query sales_analysis view with filters via PostgREST."""
    params = {"select": "*"}
    if date_from:
        params.setdefault("sale_date", []).append(f"gte.{date_from}")
    if date_to:
        params.setdefault("sale_date", []).append(f"lte.{date_to}")
    if match_status and match_status != "全部":
        params["match_status"] = f"eq.{match_status}"
    if products:
        params["product_name"] = f"in.({','.join(products)})"
    return _supabase_get_all("sales_analysis", params)


def get_product_names() -> List[str]:
    """Get deduplicated product names from the view."""
    result = _supabase_get_all("sales_analysis", {"select": "product_name"})
    return sorted({r["product_name"] for r in result if r.get("product_name")})