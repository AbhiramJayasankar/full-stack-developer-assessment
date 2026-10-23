"""Local-only email adapter for the recorded walkthrough; sends no mail."""

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.db import close_old_connections
from mailqueue.models import Delivery, EmailJob


class DemoProvider(BaseHTTPRequestHandler):
    failed_once = False

    def do_POST(self):
        close_old_connections()
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 100_000:
                self.send_error(413)
                return
            json.loads(self.rfile.read(length))
            key = self.headers.get("Idempotency-Key")
            job = EmailJob.objects.get(pk=key)
            if not DemoProvider.failed_once:
                DemoProvider.failed_once = True
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"Intentional one-time failure")
                print(f"INTENTIONAL HTTP 503 job={key}; next attempt will succeed", flush=True)
                return
            _, created = Delivery.objects.get_or_create(job=job)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Accepted" if created else b"Already accepted")
        except (ValueError, EmailJob.DoesNotExist):
            self.send_error(400)
        finally:
            close_old_connections()

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print(f"Demo provider on 127.0.0.1:{args.port}; first request returns HTTP 503", flush=True)
    HTTPServer(("127.0.0.1", args.port), DemoProvider).serve_forever()
