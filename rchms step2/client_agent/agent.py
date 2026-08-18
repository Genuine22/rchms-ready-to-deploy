"""
RCHMS Client Agent - Main Program
Runs on a CLIENT (customer-facing) PC.

What it does:
  - Reads agent_config.json to know which computer it is and where
    the admin server lives.
  - Every few seconds, asks the server: "is there an active session
    for me, and how much time is left?"
  - Shows a small always-on-top window with the countdown.
  - When time runs out, LOCKS the Windows screen automatically.
  - When idle (no active session), shows a styled circle with 00:00,
    "No active session" and "Please see the attendant to start."

Run with: python agent.py
(Run setup_agent.py first if agent_config.json doesn't exist yet.)
"""

import json
import os
import sys
import time
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import tkinter as tk
import urllib.request
import urllib.error
import urllib.parse

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_config.json")
LOG_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_log.txt")
POLL_INTERVAL_SECONDS = 5

_log_handler = RotatingFileHandler(LOG_FILE, maxBytes=500_000, backupCount=2)
_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])


def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("No configuration found. Please run setup_agent.py first.")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)


def lock_windows():
    """Lock the Windows screen. Only works on Windows."""
    try:
        ctypes.windll.user32.LockWorkStation()
        logging.info("Screen locked - session expired.")
    except Exception as e:
        logging.error(f"Could not lock screen automatically: {e}")


def fetch_status(server_url, computer_name):
    """Ask the admin server for this computer's current session status."""
    url = f"{server_url}/sessions/agent-status/{urllib.parse.quote(computer_name)}"
    try:
        with urllib.request.urlopen(url, timeout=6) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        logging.warning(f"Connection failed: {e}")
        return {"error": "connection_failed", "message": str(e)}
    except Exception as e:
        logging.error(f"Unexpected error fetching status: {e}")
        return {"error": "unknown", "message": str(e)}


def format_time(total_seconds):
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


class AgentWindow:
    """
    Client countdown window whose design mirrors the admin web interface's
    countdown-ring exactly.

    Idle state (no active session):
      - Circle ring shown in gold
      - "00:00" displayed inside the ring
      - "No active session" as the primary message inside the ring
      - "Please see the attendant to start." as the subtext inside the ring

    Active state:
      - Circle ring shown in purple (or danger-red under 5 min)
      - Live countdown number centred inside
      - "Time remaining" subtext inside the ring
      - Customer name · service shown above the ring
      - Pulsing glow animation on the ring border

    Expired state:
      - Circle ring shown in danger-red
      - "00:00" displayed
      - Screen locks automatically
    """

    # ── Brand colours (identical to admin style.css :root tokens) ─────────
    COLOR_BG           = "#EEF0FB"
    COLOR_SURFACE      = "#FFFFFF"
    COLOR_FOREST       = "#6C5CE7"
    COLOR_FOREST_LIGHT = "#8B7CF6"
    COLOR_GOLD         = "#F5C542"
    COLOR_GOLD_DARK    = "#6152D9"
    COLOR_DANGER       = "#DC2626"
    COLOR_INK          = "#221F35"
    COLOR_MUTED        = "#55516F"
    COLOR_BORDER       = "#E4E1F8"

    # ── Ring geometry ──────────────────────────────────────────────────────
    RING_CANVAS = 240
    RING_OUTER  = 108
    RING_INNER  = 95
    RING_CX     = 120
    RING_CY     = 120

    # ── Pulse timing ──────────────────────────────────────────────────────
    PULSE_STEPS        = 30
    PULSE_DELAY        = 50    # ms  (~3 s/cycle, mirrors signalPulse)
    PULSE_URGENT_DELAY = 17    # ms  (~1 s/cycle, mirrors signalPulseUrgent)

    def __init__(self, config):
        self.config = config

        # ── Window ─────────────────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title("RuralConnect Hub")
        self.root.geometry("320x500+20+20")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.configure(bg=self.COLOR_BG)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        # ── Header bar ─────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=self.COLOR_FOREST, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header, text="📡", font=("Segoe UI", 18),
            bg=self.COLOR_FOREST, fg=self.COLOR_GOLD
        ).pack(side="left", padx=(18, 8), pady=14)

        htext = tk.Frame(header, bg=self.COLOR_FOREST)
        htext.pack(side="left", pady=10)
        tk.Label(
            htext, text="RuralConnect", font=("Segoe UI", 12, "bold"),
            bg=self.COLOR_FOREST, fg="white", anchor="w"
        ).pack(anchor="w")
        tk.Label(
            htext, text=config["computer_name"].upper(), font=("Segoe UI", 8),
            bg=self.COLOR_FOREST, fg="#D9D4FA", anchor="w"
        ).pack(anchor="w")

        # ── Body card ──────────────────────────────────────────────────────
        body = tk.Frame(
            self.root, bg=self.COLOR_SURFACE,
            highlightbackground=self.COLOR_BORDER, highlightthickness=1
        )
        body.pack(fill="both", expand=True, padx=16, pady=16)

        # Info label above the ring. During an active session this shows
        # the customer name and service. During idle state, this is now
        # where "No active session" appears - above the ring, inside its
        # own soft-tinted holder (matching the warm background tone used
        # elsewhere in the app) rather than drawn inside the canvas.
        self.info_label = tk.Label(
            body, text="",
            font=("Segoe UI", 9, "bold"), bg=self.COLOR_BG,
            fg=self.COLOR_INK, wraplength=260, justify="center",
            padx=14, pady=6
        )
        self.info_label.pack(pady=(16, 4))

        # ── Canvas (the ring lives here) ───────────────────────────────────
        self.canvas = tk.Canvas(
            body,
            width=self.RING_CANVAS, height=self.RING_CANVAS,
            bg=self.COLOR_SURFACE, highlightthickness=0
        )
        self.canvas.pack(pady=4)

        # Layer order (back → front):
        #  1. Radial gradient fill
        #  2. Glow ring  (animated pulse, behind the border)
        #  3. Border ring (the coloured circle outline)
        #  4. Idle: "No active session" line 1
        #  5. Idle: "Please see the attendant" line 2
        #  6. Active: large countdown number
        #  7. Active: "Time remaining" subtext  OR  idle "00:00" number

        self._draw_gradient_fill()

        # Glow ring
        self.glow_ring = self.canvas.create_oval(
            self.RING_CX - self.RING_OUTER - 6,
            self.RING_CY - self.RING_OUTER - 6,
            self.RING_CX + self.RING_OUTER + 6,
            self.RING_CY + self.RING_OUTER + 6,
            outline="", width=0
        )

        # Border ring
        self.ring_oval = self.canvas.create_oval(
            self.RING_CX - self.RING_OUTER,
            self.RING_CY - self.RING_OUTER,
            self.RING_CX + self.RING_OUTER,
            self.RING_CY + self.RING_OUTER,
            outline=self.COLOR_GOLD, width=3
        )

        # ── Idle-state text items (inside the ring) ────────────────────────
        # "00:00" — sits in the upper-centre of the ring during idle
        self.idle_time_item = self.canvas.create_text(
            self.RING_CX, self.RING_CY,
            text="00:00",
            font=("Segoe UI", 30, "bold"),
            fill=self.COLOR_GOLD_DARK,
            state="normal"
        )

        # ── Active-state text items (inside the ring) ──────────────────────
        # Large countdown number
        self.timer_text_item = self.canvas.create_text(
            self.RING_CX, self.RING_CY - 14,
            text="--:--",
            font=("Segoe UI", 38, "bold"),
            fill=self.COLOR_FOREST,
            state="hidden"
        )

        # "Time remaining" subtext
        self.subtext_item = self.canvas.create_text(
            self.RING_CX, self.RING_CY + 26,
            text="",
            font=("Segoe UI", 9),
            fill=self.COLOR_MUTED,
            state="hidden"
        )

        # ── Status label below ring ────────────────────────────────────────
        # Same soft-tinted holder as the info_label above the ring, so
        # idle messages ("Please see the attendant to start.") and active
        # status ("Time remaining" / warnings) both sit in a consistent
        # card-like zone below the ring rather than drawn on the canvas.
        self.status_label = tk.Label(
            body, text="",
            font=("Segoe UI", 9, "bold"),
            bg=self.COLOR_BG, fg=self.COLOR_GOLD,
            wraplength=260, justify="center",
            padx=14, pady=6
        )
        self.status_label.pack(pady=(4, 18))

        # ── Internal state ─────────────────────────────────────────────────
        self.already_locked   = False
        self.had_active       = False
        self.synced_remaining = None
        self.synced_at        = None
        self.synced_warning   = False
        self.ticker_running   = False
        self._pulse_step      = 0
        self._pulse_direction = 1
        self._pulse_job       = None
        self._pulse_active    = False
        self._pulse_urgent    = False

        # Start in idle state immediately
        self._enter_idle_state()

    # ── Gradient fill ──────────────────────────────────────────────────────
    def _draw_gradient_fill(self):
        steps = 18
        for i in range(steps, -1, -1):
            frac  = i / steps
            r_val = int(255 - frac * 26)
            g_val = int(255 - frac * 22)
            b_val = int(255 - frac * 6)
            color  = f"#{r_val:02x}{g_val:02x}{b_val:02x}"
            margin = i * (self.RING_OUTER / steps)
            self.canvas.create_oval(
                self.RING_CX - self.RING_INNER + margin,
                self.RING_CY - self.RING_INNER + margin,
                self.RING_CX + self.RING_INNER - margin,
                self.RING_CY + self.RING_INNER - margin,
                fill=color, outline=""
            )

    # ── Pulse animation ────────────────────────────────────────────────────
    def _hex_with_alpha(self, base_hex, alpha):
        r = int(base_hex[1:3], 16)
        g = int(base_hex[3:5], 16)
        b = int(base_hex[5:7], 16)
        r2 = int(r * alpha + 255 * (1 - alpha))
        g2 = int(g * alpha + 255 * (1 - alpha))
        b2 = int(b * alpha + 255 * (1 - alpha))
        return f"#{r2:02x}{g2:02x}{b2:02x}"

    def _start_pulse(self, urgent=False):
        if self._pulse_job:
            self.root.after_cancel(self._pulse_job)
            self._pulse_job = None
        self._pulse_active    = True
        self._pulse_urgent    = urgent
        self._pulse_step      = 0
        self._pulse_direction = 1
        self._animate_pulse()

    def _stop_pulse(self):
        self._pulse_active = False
        if self._pulse_job:
            self.root.after_cancel(self._pulse_job)
            self._pulse_job = None
        self.canvas.itemconfig(self.glow_ring, outline="")

    def _animate_pulse(self):
        if not self._pulse_active:
            return
        base_color = self.COLOR_DANGER if self._pulse_urgent else self.COLOR_FOREST
        delay      = self.PULSE_URGENT_DELAY if self._pulse_urgent else self.PULSE_DELAY
        alpha      = (self._pulse_step / self.PULSE_STEPS) * 0.40
        glow_color = self._hex_with_alpha(base_color, alpha)
        self.canvas.itemconfig(self.glow_ring, outline=glow_color, width=14)
        self._pulse_step += self._pulse_direction
        if self._pulse_step >= self.PULSE_STEPS:
            self._pulse_direction = -1
        elif self._pulse_step <= 0:
            self._pulse_direction = 1
        self._pulse_job = self.root.after(delay, self._animate_pulse)

    # ── State switching ────────────────────────────────────────────────────
    def _show_idle_items(self, visible):
        """Show or hide the idle-specific canvas items."""
        state = "normal" if visible else "hidden"
        self.canvas.itemconfig(self.idle_time_item, state=state)

    def _show_active_items(self, visible):
        """Show or hide the active-session canvas items."""
        state = "normal" if visible else "hidden"
        self.canvas.itemconfig(self.timer_text_item, state=state)
        self.canvas.itemconfig(self.subtext_item,    state=state)

    def _enter_idle_state(self):
        """
        Switch all visual elements to the idle look:
          - Gold ring border
          - 00:00 inside the ring
          - 'No active session' in the holder above the ring
          - 'Please see the attendant to start.' in the holder below the ring
        """
        self._stop_pulse()
        self.canvas.itemconfig(self.ring_oval, outline=self.COLOR_GOLD, width=3)
        self._show_idle_items(True)
        self._show_active_items(False)
        self.info_label.config(text="No active session", fg=self.COLOR_INK)
        self.status_label.config(text="Please see the attendant to start.", fg=self.COLOR_GOLD_DARK)

    def _enter_active_state(self):
        """Switch all visual elements to the active countdown look."""
        self._show_idle_items(False)
        self._show_active_items(True)

    # ── Server data handler ────────────────────────────────────────────────
    def update_display(self, data):

        # ── Connection error ───────────────────────────────────────────────
        if "error" in data:
            self._enter_idle_state()
            self.info_label.config(text="Cannot reach server...")
            self.status_label.config(
                text="Check network connection.", fg=self.COLOR_DANGER
            )
            return

        # ── No active session ──────────────────────────────────────────────
        if not data.get("has_session"):
            if data.get("expired") and not self.already_locked:
                # Session just ended — show 00:00 in red then lock
                self.already_locked = True
                self._stop_pulse()
                self._show_idle_items(False)
                self._show_active_items(True)
                self.canvas.itemconfig(
                    self.ring_oval, outline=self.COLOR_DANGER, width=3
                )
                self.canvas.itemconfig(
                    self.timer_text_item, text="00:00", fill=self.COLOR_DANGER
                )
                self.canvas.itemconfig(self.subtext_item, text="", state="hidden")
                self.info_label.config(text="Session ended")
                self.status_label.config(
                    text="Time's up — locking screen...", fg=self.COLOR_DANGER
                )
                self.root.update()
                self.root.after(1200, lock_windows)
            else:
                # Normal idle — no session running
                self._enter_idle_state()

            self.had_active       = False
            self.ticker_running   = False
            self.synced_remaining = None
            self.synced_at        = None
            return

        # ── Active session ─────────────────────────────────────────────────
        self.had_active       = True
        self.already_locked   = False
        self.synced_remaining = data["seconds_remaining"]
        self.synced_at        = time.time()
        self.synced_warning   = bool(data.get("warning"))
        self._enter_active_state()
        self.info_label.config(
            text=f"{data.get('customer_name', '')} · {data.get('service_name', '')}"
        )
        self._start_ticker()

    # ── Smooth ticker ──────────────────────────────────────────────────────
    def _start_ticker(self):
        if self.ticker_running:
            return
        self.ticker_running = True
        self._tick()

    def _tick(self):
        if not (self.ticker_running and self.synced_remaining is not None and self.had_active):
            self.ticker_running = False
            return

        elapsed   = time.time() - self.synced_at
        remaining = max(0, round(self.synced_remaining - elapsed))
        warning   = self.synced_warning or remaining <= 300

        ring_color = self.COLOR_DANGER if warning else self.COLOR_FOREST

        # Switch / start pulse
        if not self._pulse_active:
            self._start_pulse(urgent=warning)
        elif self._pulse_urgent != warning:
            self._start_pulse(urgent=warning)

        self.canvas.itemconfig(self.ring_oval, outline=ring_color, width=3)
        self.canvas.itemconfig(
            self.timer_text_item,
            text=format_time(remaining),
            fill=self.COLOR_DANGER if warning else self.COLOR_FOREST
        )
        self.canvas.itemconfig(
            self.subtext_item, text="Time remaining",
            fill=self.COLOR_MUTED, state="normal"
        )

        if warning:
            self.status_label.config(text="⚠ Session ending soon!", fg=self.COLOR_DANGER)
        else:
            self.status_label.config(text="Time remaining", fg=self.COLOR_MUTED)

        self.root.after(250, self._tick)

    # ── Poll loop ──────────────────────────────────────────────────────────
    def poll_loop(self):
        data = fetch_status(self.config["server_url"], self.config["computer_name"])
        self.update_display(data)
        self.root.after(POLL_INTERVAL_SECONDS * 1000, self.poll_loop)

    def run(self):
        self.root.after(500, self.poll_loop)
        self.root.mainloop()


if __name__ == "__main__":
    try:
        logging.info("Agent starting up.")
        cfg = load_config()
        app = AgentWindow(cfg)
        app.run()
    except Exception as e:
        logging.error(f"Agent crashed: {e}", exc_info=True)
        raise
