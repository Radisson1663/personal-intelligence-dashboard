from http.server import BaseHTTPRequestHandler
import urllib.parse
from api._shared import json_response, read_body, supabase_request

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self): json_response(self, {})
    def do_POST(self):
        try:
            signal_id = str(read_body(self).get("id", "")).strip()
            if not signal_id: return json_response(self, {"error": "Missing signal id"}, 400)
            encoded = urllib.parse.quote(signal_id)
            existing = supabase_request(f"saved_signals?select=signal_id&signal_id=eq.{encoded}") or []
            if existing: supabase_request(f"saved_signals?signal_id=eq.{encoded}", method="DELETE")
            else: supabase_request("saved_signals", method="POST", payload={"signal_id": signal_id}, prefer="return=minimal")
            rows = supabase_request("saved_signals?select=signal_id") or []
            json_response(self, {"saved": [str(x["signal_id"]) for x in rows]})
        except Exception as error: json_response(self, {"error": str(error)}, 500)

app = handler
