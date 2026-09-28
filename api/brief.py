from http.server import BaseHTTPRequestHandler
from api._shared import fallback_brief, json_response, latest_brief

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try: json_response(self, latest_brief())
        except Exception as error:
            payload = fallback_brief(); payload["databaseStatus"] = str(error)
            json_response(self, payload)

app = handler
