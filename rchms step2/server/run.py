"""
RCHMS - Main entry point.
Run this file to start the server: python run.py

Once running, open a browser and go to:
  http://localhost:5000        (on this PC)
  http://<this-pc-ip>:5000     (from another PC on the same network)
"""

import os
from datetime import datetime
from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5000))

    # DEBUG_MODE is off by default now that the system is in real use -
    # debug mode shows full error details to anyone who hits a bug, which
    # is fine while building but risky day to day. To turn it back on
    # temporarily (e.g. while troubleshooting something with Claude),
    # add this line to your .env file:
    #   DEBUG_MODE=true
    debug_mode = os.getenv("DEBUG_MODE", "false").strip().lower() == "true"

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] RCHMS starting "
          f"(debug={debug_mode}) on {host}:{port}")

    app.run(host=host, port=port, debug=debug_mode)

