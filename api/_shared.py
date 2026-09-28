"""Shared Supabase and HTTP helpers for the Vercel functions."""
from datetime import datetime
from http.server import BaseHTTPRequestHandler
import json, os, urllib.error, urllib.parse, urllib.request


def json_response(handler: BaseHTTPRequestHandler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    for key, value in (("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store"), ("Access-Control-Allow-Origin", "*"), ("Access-Control-Allow-Headers", "content-type"), ("Content-Length", str(len(body)))):
        handler.send_header(key, value)
    handler.end_headers(); handler.wfile.write(body)


def read_body(handler):
    return json.loads(handler.rfile.read(int(handler.headers.get("Content-Length", "0"))) or b"{}")


def fallback_brief():
    return {
        "date": datetime.now().strftime("%B %d, %Y").replace(" 0", " "),
        "updatedAt": None,
        "lead": "正在准备第一期真实新闻。",
        "items": [],
        "saved": [],
        "reviews": {},
    }


def supabase_request(path, method="GET", payload=None, prefer=None):
    url = os.environ.get("SUPABASE_URL", "").rstrip("/"); key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key: raise RuntimeError("Supabase environment variables are not configured")
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    if prefer: headers["Prefer"] = prefer
    request = urllib.request.Request(f"{url}/rest/v1/{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(); return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Supabase {error.code}: {error.read().decode('utf-8', 'replace')[:300]}") from error


def latest_brief():
    briefs = supabase_request("daily_briefs?select=*&order=brief_date.desc&limit=1")
    if not briefs: return fallback_brief()
    row = briefs[0]; day = row["brief_date"]
    items = supabase_request(f"signals?select=*&brief_date=eq.{urllib.parse.quote(day)}&order=rank.asc") or []
    saved = supabase_request("saved_signals?select=signal_id") or []
    review_rows = supabase_request("reviews?select=*&order=period_end.desc,created_at.desc&limit=20") or []
    reviews = {}
    for review in review_rows:
        kind = review.get("kind")
        if kind in ("weekly", "monthly") and kind not in reviews:
            reviews[kind] = {"note": review.get("note", ""), "items": review.get("items") or [], "start": review.get("period_start"), "end": review.get("period_end")}
    normalized = [{"id": x["id"], "rank": x.get("rank", 99), "category": x.get("category", ""), "title": x.get("title", ""), "url": x.get("url", ""), "source": x.get("source", ""), "summary": x.get("summary", ""), "why": x.get("why_it_matters", "")} for x in items]
    date_label = datetime.strptime(day, "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
    return {"date": date_label, "updatedAt": row.get("updated_at"), "lead": row.get("lead", ""), "items": normalized, "saved": [str(x["signal_id"]) for x in saved], "reviews": reviews}
