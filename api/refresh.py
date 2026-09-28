"""Daily RSS collector. Vercel calls this at 08:00 Asia/Shanghai."""
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo
import html, re, urllib.parse, urllib.request, uuid
import xml.etree.ElementTree as ET
from api._shared import json_response, latest_brief, supabase_request

TZ = ZoneInfo("Asia/Shanghai")
SOURCES = {
    "Design": ["https://www.dezeen.com/feed/", "https://www.fastcompany.com/section/design/rss"],
    "AI Industry": ["https://openai.com/news/rss.xml", "https://www.technologyreview.com/topic/artificial-intelligence/feed/"],
    "New Products": ["https://www.producthunt.com/feed", "https://techcrunch.com/feed/"],
    "Big Tech": ["https://www.theverge.com/rss/index.xml"],
    "Social Media": ["https://www.socialmediatoday.com/feeds/news/"],
}
TARGETS = {"Design": 5, "AI Industry": 4, "New Products": 3, "Big Tech": 2, "Social Media": 1}

def clean(value): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()
def child_text(node, names):
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] in names and child.text: return clean(child.text)
    return ""
def fetch_feed(url):
    request = urllib.request.Request(url, headers={"User-Agent": "PersonalIntelligence/2.0"})
    with urllib.request.urlopen(request, timeout=18) as response: root = ET.fromstring(response.read())
    rows = []
    for item in root.findall(".//item") + root.findall(".//{*}entry"):
        title = child_text(item, {"title"}); link = child_text(item, {"link"})
        if not link: link = next((el.attrib.get("href") for el in item.iter() if el.tag.rsplit("}", 1)[-1] == "link" and el.attrib.get("href")), "")
        if title and link: rows.append({"title": title, "url": link, "summary": child_text(item, {"description", "summary", "content", "encoded"})})
    return rows
def source_name(url):
    host = urllib.parse.urlparse(url).netloc.removeprefix("www.")
    return host.split(".")[0].replace("-", " ").title()
def insight(category):
    return {"Design": "关注它对交互、视觉语言、品牌体验或设计方法的影响。", "AI Industry": "关注它如何改变设计师使用的工具、模型与工作流程。", "New Products": "观察它解决了什么用户问题，以及新的交互方式是否会持续。", "Big Tech": "这可能改变产品赖以运行的平台、规则和生态系统。", "Social Media": "关注用户行为、内容分发和创作者生态的变化。"}[category]
def create_review(kind, today):
    if kind == "weekly": end = today - timedelta(days=1); start = end - timedelta(days=6)
    else: end = today - timedelta(days=1); start = end.replace(day=1)
    rows = supabase_request(f"signals?select=*&brief_date=gte.{start.isoformat()}&brief_date=lte.{end.isoformat()}&order=brief_date.desc,rank.asc") or []
    rows.sort(key=lambda x: (x.get("category") != "Design", x.get("rank", 99)))
    items = [{"title": x["title"], "url": x["url"], "category": x["category"]} for x in rows[:5]]
    supabase_request("reviews", method="POST", payload={"kind": kind, "period_start": start.isoformat(), "period_end": end.isoformat(), "note": "A design-led selection of the period’s most useful signals.", "items": items}, prefer="return=minimal")
def refresh():
    now = datetime.now(TZ); today = now.date(); collected = []; seen = set()
    for category, feeds in SOURCES.items():
        bucket = []
        for feed in feeds:
            try:
                for item in fetch_feed(feed):
                    key = item["url"].split("?")[0]
                    if key not in seen: seen.add(key); item.update(category=category, source=source_name(item["url"])); bucket.append(item)
            except Exception: continue
        collected.extend(bucket[:TARGETS[category]])
    featured = []
    for category, count in (("Design", 3), ("AI Industry", 1), ("New Products", 1)): featured.extend([x for x in collected if x["category"] == category][:count])
    featured_urls = {x["url"] for x in featured}; collected = featured + [x for x in collected if x["url"] not in featured_urls]
    if not collected: raise RuntimeError("No news sources returned usable items")
    day = today.isoformat()
    supabase_request("daily_briefs", method="POST", payload={"brief_date": day, "lead": f"Today’s signal: {collected[0]['title']}", "updated_at": now.isoformat()}, prefer="resolution=merge-duplicates,return=minimal")
    supabase_request(f"signals?brief_date=eq.{day}", method="DELETE")
    signals = []
    for rank, item in enumerate(collected[:15], 1):
        signals.append({"id": str(uuid.uuid4()), "brief_date": day, "rank": rank, "category": item["category"], "title": item["title"], "url": item["url"], "source": item["source"], "summary": (item.get("summary") or "Open the original source for the full report.")[:360], "why_it_matters": insight(item["category"])})
    supabase_request("signals", method="POST", payload=signals, prefer="return=minimal")
    if today.weekday() == 0: create_review("weekly", today)
    if today.day == 1: create_review("monthly", today)
    return latest_brief()
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try: json_response(self, refresh())
        except Exception as error: json_response(self, {"error": str(error)}, 500)
    do_POST = do_GET

app = handler
