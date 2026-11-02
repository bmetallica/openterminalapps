#!/usr/bin/env python3
"""Ein Fake-Modell mit OpenAI-Schnittstelle für scripts/test-opencode.sh.

Läuft im Arbeitsplatz auf 127.0.0.1:9100. Sagt immer „fertig“, ausser:

* „SPEICHERN“ in der letzten Nachricht des Menschen: ruft *_memory_save auf,
  mit einer gefälschten Sitzungskennung (die das Plugin überschreiben muss);
* „UNTER“: startet einen Unteragenten, der seinerseits speichert.

Jede Anfrage landet in der Standardausgabe (Systemprompt und Werkzeuge), damit
der Test sieht, was beim Modell ankommt.
"""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Modell(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        b = json.dumps({"data": [{"id": "fake", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = req.get("messages", [])
        werkzeuge = req.get("tools", [])
        print(json.dumps({"system": [m.get("content") for m in msgs if m.get("role") == "system"],
                          "tools": werkzeuge}), flush=True)
        namen = [w["function"]["name"] for w in werkzeuge]
        letzte = msgs[-1] if msgs else {}
        inhalt = letzte.get("content")
        if isinstance(inhalt, list):
            inhalt = " ".join(p.get("text", "") for p in inhalt if isinstance(p, dict))
        inhalt = inhalt or ""
        speichern = next((n for n in namen if n.endswith("memory_save")), None)
        aufruf = None
        if letzte.get("role") == "user" and "UNTER" in inhalt and "subagent" in namen:
            aufruf = ("subagent", {"agent": "general", "description": "Merken im Unteragent",
                                   "prompt": "Bitte SPEICHERN aus dem Unteragent"})
        elif letzte.get("role") == "user" and "SPEICHERN" in inhalt and speichern:
            text = "Pruef-Eintrag aus dem Unteragent" if "Unteragent" in inhalt else "Pruef-Eintrag aus opencode"
            aufruf = (speichern, {"content": text, "kind": "fakt", "ota_sitzung": "GEFAELSCHT"})
        if aufruf:
            delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": f"call_{time.time_ns()}", "type": "function",
                     "function": {"name": aufruf[0], "arguments": json.dumps(aufruf[1])}}]}
            ende = "tool_calls"
        else:
            delta, ende = {"role": "assistant", "content": "fertig"}, "stop"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for teil in ({"delta": delta, "index": 0, "finish_reason": None},
                     {"delta": {}, "index": 0, "finish_reason": ende}):
            self.wfile.write(b"data: " + json.dumps({"id": "x", "object": "chat.completion.chunk",
                             "created": int(time.time()), "model": "fake", "choices": [teil]}).encode() + b"\n\n")
        self.wfile.write(b'data: {"id":"x","object":"chat.completion.chunk","created":0,"model":"fake",'
                         b'"choices":[],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n\n'
                         b"data: [DONE]\n\n")


ThreadingHTTPServer(("127.0.0.1", 9100), Modell).serve_forever()
