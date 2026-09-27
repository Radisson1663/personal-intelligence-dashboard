#!/usr/bin/env python3
"""Personal Intelligence — a dependency-free daily news brief."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
import json, os, re, threading, time, urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "brief.json"
HISTORY = ROOT / "data" / "history"
TZ = ZoneInfo(os.environ.get("BRIEF_TIMEZONE", "Asia/Shanghai"))

# The sources are public RSS/Atom feeds. Add or remove feeds here without changing the UI.
SOURCES = {
    "AI Industry": ["https://openai.com/news/rss.xml", "https://www.technologyreview.com/topic/artificial-intelligence/feed/"],
    "New Products": ["https://www.producthunt.com/feed", "https://techcrunch.com/feed/"],
    "Design": ["https://www.dezeen.com/feed/", "https://www.fastcompany.com/section/design/rss"],
    "Big Tech": ["https://www.theverge.com/rss/index.xml", "https://techcrunch.com/feed/"],
    "Social Media": ["https://www.socialmediatoday.com/feeds/news/"],
}
TARGETS = {"AI Industry": 4, "New Products": 3, "Design": 5, "Big Tech": 2, "Social Media": 1}

def clean(value):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()

def text(node, names):
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] in names and child.text:
            return clean(child.text)
    return ""

def fetch_feed(url):
    request = urllib.request.Request(url, headers={"User-Agent": "PersonalIntelligence/1.0 (+personal daily brief)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read()
    root = ET.fromstring(raw)
    results = []
    for item in root.findall(".//item") + root.findall(".//{*}entry"):
        title = text(item, {"title"})
        link = text(item, {"link"})
        if not link:
            for el in item.iter():
                if el.tag.rsplit("}", 1)[-1] == "link" and el.attrib.get("href"):
                    link = el.attrib["href"]; break
        summary = text(item, {"description", "summary", "content", "encoded"})
        published = text(item, {"pubDate", "published", "updated", "date"})
        if title and link:
            results.append({"title": title, "url": link, "summary": summary, "published": published})
    return results

def source_name(url):
    host = re.sub(r"^www\.", "", url.split("/")[2])
    return host.split(".")[0].replace("-", " ").title()

def make_insight(item, category):
    summary = item["summary"] or "Open the original report for the full announcement and context."
    summary = summary[:320].rstrip(" .,;") + ("…" if len(summary) > 320 else "")
    category_context = {
        "AI Industry": "Watch how this changes the tools, models, or teams shaping AI.",
        "New Products": "Look for the user problem it solves and whether the behavior could last.",
        "Design": "Consider the interaction, visual language, and broader design signal behind it.",
        "Big Tech": "This may influence the platforms and ecosystems products are built on.",
        "Social Media": "Pay attention to the shift in audience behavior and distribution.",
    }[category]
    return summary, category_context

def read_history(day):
    path = HISTORY / f"{day.isoformat()}.json"
    if path.exists():
        try: return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError: return None
    return None

def build_review(kind, start, end):
    items, seen = [], set()
    cursor = start
    while cursor <= end:
        entry = read_history(cursor)
        for item in (entry or {}).get("items", []):
            key = item.get("url", "").split("?")[0]
            if key and key not in seen:
                seen.add(key); items.append(item)
        cursor += timedelta(days=1)
    # Design first: the review mirrors the new editorial direction rather than raw feed order.
    items.sort(key=lambda x: (x.get("category") != "Design", x.get("rank", 99)))
    selected = items[:5]
    label = "This week in review" if kind == "weekly" else "This month in perspective"
    return {"label": label, "start": start.isoformat(), "end": end.isoformat(), "items": selected,
            "note": "A design-led selection of the period’s most useful signals." if selected else "This review will appear after enough daily editions have been collected."}

def update_reviews(today):
    reviews_path = ROOT / "data" / "reviews.json"
    try: reviews = json.loads(reviews_path.read_text(encoding="utf-8")) if reviews_path.exists() else {}
    except json.JSONDecodeError: reviews = {}
    if today.weekday() == 0:  # Monday: review the preceding Monday–Sunday.
        end = today - timedelta(days=1); reviews["weekly"] = build_review("weekly", end - timedelta(days=6), end)
    if today.day == 1:  # First day of month: review the preceding calendar month.
        end = today - timedelta(days=1); reviews["monthly"] = build_review("monthly", end.replace(day=1), end)
    reviews_path.parent.mkdir(exist_ok=True)
    reviews_path.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
    return reviews

def refresh():
    collected, errors, seen = [], [], set()
    for category, feeds in SOURCES.items():
        bucket = []
        for feed in feeds:
            try:
                for item in fetch_feed(feed):
                    key = item["url"].split("?")[0]
                    if key not in seen:
                        seen.add(key); item["category"] = category; item["source"] = source_name(item["url"]); bucket.append(item)
            except Exception as error:
                errors.append(f"{source_name(feed)}: {str(error)[:90]}")
        collected.extend(bucket[:TARGETS[category]])
    # The first five are the daily push: intentionally design-led while still broad.
    featured = []
    for category, amount in (("Design", 3), ("AI Industry", 1), ("New Products", 1)):
        featured.extend([item for item in collected if item["category"] == category][:amount])
    featured_urls = {item["url"] for item in featured}
    collected = featured + [item for item in collected if item["url"] not in featured_urls]
    # Keep the intended daily editorial balance: Design 5 / AI 4 / Products 3 / Big Tech 2 / Social 1.
    for i, item in enumerate(collected, start=1):
        item["id"] = f"{date.today().isoformat()}-{i}"
        item["rank"] = i
        item["summary"], item["why"] = make_insight(item, item["category"])
    now = datetime.now(TZ)
    lead = "Today’s signal: " + (collected[0]["title"] if collected else "sources are being refreshed")
    payload = {"date": now.strftime("%B %-d, %Y"), "updatedAt": now.isoformat(), "lead": lead,
               "items": collected, "errors": errors, "saved": load().get("saved", [])}
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    HISTORY.mkdir(exist_ok=True)
    (HISTORY / f"{now.date().isoformat()}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["reviews"] = update_reviews(now.date())
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

def load():
    if DATA.exists():
        try: return json.loads(DATA.read_text(encoding="utf-8"))
        except json.JSONDecodeError: pass
    return {"items": [], "saved": [], "reviews": {}}

def schedule():
    while True:
        now = datetime.now(TZ)
        target = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now >= target: target += timedelta(days=1)
        time.sleep(max(1, (target - now).total_seconds()))
        try: refresh()
        except Exception as error: print("Scheduled refresh failed:", error)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT / "public"), **kwargs)
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/api/brief": return self.send_json(load())
        return super().do_GET()
    def do_POST(self):
        if self.path == "/api/refresh":
            try: return self.send_json(refresh())
            except Exception as error: return self.send_json({"error": str(error)}, 500)
        if self.path.startswith("/api/save/"):
            item_id = self.path.rsplit("/", 1)[-1]; data = load(); saved = set(data.get("saved", []))
            if item_id in saved: saved.remove(item_id)
            else: saved.add(item_id)
            data["saved"] = list(saved); DATA.parent.mkdir(exist_ok=True); DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return self.send_json({"saved": list(saved)})
        return self.send_json({"error": "Not found"}, 404)

if __name__ == "__main__":
    if not DATA.exists():
        try: refresh()
        except Exception as error: print("Initial refresh failed:", error)
    threading.Thread(target=schedule, daemon=True).start()
    port = int(os.environ.get("PORT", "8000"))
    print(f"Personal Intelligence running at http://localhost:{port}")
    ThreadingHTTPServer(("", port), Handler).serve_forever()
