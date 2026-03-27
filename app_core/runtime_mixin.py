from __future__ import annotations

import csv
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from tkinter import messagebox, ttk

from app_core.common import NUMBER_PATTERN, format_currency, format_number, parse_number_token


class RuntimeMixin:
    def test_extension_connection(self):
        """Test if the extension endpoint is reachable."""
        try:
            port = int(self.extension_port_value.get().strip())
        except ValueError:
            self.set_status("Port must be a number", "err")
            return
        
        endpoint = f"http://127.0.0.1:{port}/extension-feed"
        try:
            import urllib.request
            payload = json.dumps({"slot": "test", "text": "healthcheck", "timestamp": ""}).encode("utf-8")
            req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            response = urllib.request.urlopen(req, timeout=2)
            if response.status == 200:
                self.set_status("✓ Extension connection OK", "ok")
                self.extension_status_value.set("✓ Connection test passed!")
                print("[✓] Extension connection test successful")
            else:
                self.set_status("Server responded but with error", "warn")
        except (OSError, ValueError) as e:
            self.set_status(f"Connection failed: {str(e)[:50]}", "err")
            self.extension_status_value.set(f"❌ Connection test failed")
            print(f"[ERROR] Could not connect to extension endpoint: {e}")

    def start_extension_server(self):
        if self.extension_server is not None:
            return True

        try:
            port = int(self.extension_port_value.get().strip())
        except ValueError:
            self.set_status("Extension port must be a number", "err")
            return False

        app = self

        class ExtensionHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/live-trades-status":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    live_enabled = bool(app.live_trades_enabled_value.get())
                    in_position = bool(app.auto_position_side != 0)
                    armed = bool(app.running and not in_position)
                    action_buttons_active = bool(app.running and live_enabled)
                    command = app.pop_live_trade_command() if action_buttons_active else None
                    response = json.dumps(
                        {
                            "enabled": live_enabled,
                            "monitoring": bool(app.running),
                            "armed": armed,
                            "inPosition": in_position,
                            "actionButtonsActive": action_buttons_active,
                            "command": command,
                        }
                    )
                    self.wfile.write(response.encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path == "/live-trade-command-ack":
                    content_length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(content_length)
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        payload = {}
                    app.after(0, app.handle_live_trade_command_ack, payload)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                    return

                if self.path != "/extension-feed":
                    self.send_response(404)
                    self.end_headers()
                    return

                content_length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_length)
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    print(f"[ERROR] Failed to parse JSON: {e}")
                    self.send_response(400)
                    self.end_headers()
                    return

                print(f"[✓ RECEIVED] Extension data: {payload}")
                app.after(0, app.handle_extension_payload, payload)

                slot = str(payload.get("slot", "")).strip().lower()
                command = None
                if slot in ("topstep", "tradovate") and app.running and app.live_trades_enabled_value.get():
                    command = app.pop_live_trade_command()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "command": command}).encode("utf-8"))

            def log_message(self, _format, *_args):
                return

        try:
            self.extension_server = ThreadingHTTPServer(("127.0.0.1", port), ExtensionHandler)
        except OSError as exc:
            self.extension_server = None
            self.set_status(f"Extension feed port error: {exc}", "err")
            return False

        self.extension_server_thread = threading.Thread(target=self.extension_server.serve_forever, daemon=True)
        self.extension_server_thread.start()
        msg = f"🟢 Listening on 127.0.0.1:{port}"
        self.extension_status_value.set(msg)
        self.refresh_feed_health_display()
        print(f"[✓ READY] {msg}")
        return True

    def stop_extension_server(self):
        if self.extension_server is None:
            self.extension_status_value.set("Stopped")
            self.refresh_feed_health_display()
            return
        self.extension_server.shutdown()
        self.extension_server.server_close()
        self.extension_server = None
        self.extension_server_thread = None
        self.extension_status_value.set("Stopped")
        self.refresh_feed_health_display()

    def toggle_live_trades(self):
        """Toggle live trades on/off."""
        current = self.live_trades_enabled_value.get()
        self.live_trades_enabled_value.set(not current)
        status = "🟢 Live trades ENABLED" if not current else "🔴 Live trades DISABLED"
        self.set_status(status, "ok" if not current else "warn")
        print(f"[TOGGLE] Live trades now: {not current}")

    def handle_extension_payload(self, payload):
        if not isinstance(payload, dict):
            return
        slot = str(payload.get("slot", "")).strip().lower()
        if slot in ("left", "a"):
            slot = "topstep"
        elif slot in ("right", "b"):
            slot = "tradovate"
        elif slot == "healthcheck":
            # Extension test ping - ignore
            return
        elif slot == "toggle-live-trades":
            # Extension toggle request
            self.toggle_live_trades()
            return

        if slot not in ("topstep", "tradovate"):
            return

        text = str(payload.get("text", "")).strip()
        value, _score = self.extract_number_from_text(text)
        received_epoch = time.time()
        with self.extension_lock:
            self.extension_texts[slot] = text
            self.extension_values[slot] = value
            self.extension_last_received_epoch[slot] = received_epoch
        self.refresh_feed_health_display(received_epoch)

    def record_order_action(self, action: str, trigger_label: str, details: str = "", mode: str = "IN_APP_SIM"):
        timestamp = self.get_utc_minus5_timestamp()
        row = (timestamp, action, trigger_label, details, mode)
        self.order_count += 1
        self.order_count_value.set(str(self.order_count))
        with open(self.order_log_path, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(row)

    def get_live_trade_command_slot(self, action: str, trigger_source: str):
        source = str(trigger_source or "").upper()
        if source == "AUTO_ENTRY":
            return "buy-button" if action == "BUY" else "sell-button"
        if source in ("AUTO_TP", "AUTO_SL"):
            return "close-button"
        return "buy-button" if action == "BUY" else "sell-button"

    def enqueue_live_trade_command(self, slot: str, action: str, trigger_source: str, diff: float | None, note: str):
        self.live_trade_command_seq += 1
        payload = {
            "id": self.live_trade_command_seq,
            "slot": slot,
            "action": action,
            "trigger": trigger_source,
            "diff": diff,
            "note": note,
            "timestamp": self.get_utc_minus5_timestamp(),
        }
        with self.extension_lock:
            self.live_trade_commands.append(payload)
        print(f"[LIVE QUEUE] queued command #{payload['id']} {slot} ({trigger_source})")

    def pop_live_trade_command(self):
        with self.extension_lock:
            if not self.live_trade_commands:
                return None
            return self.live_trade_commands.popleft()

    def handle_live_trade_command_ack(self, payload):
        if not isinstance(payload, dict):
            return
        command_id = payload.get("id")
        slot = str(payload.get("slot", "")).strip()
        ok = bool(payload.get("ok"))
        text = str(payload.get("text", "")).strip()
        error = str(payload.get("error", "")).strip()
        if ok:
            print(f"[LIVE ACK] command #{command_id} executed on {slot} ({text or 'ok'})")
        else:
            print(f"[LIVE ACK] command #{command_id} failed on {slot}: {error or 'unknown error'}")

    def execute_paper_trade(
        self,
        action: str,
        trigger_source: str = "MANUAL",
        diff: float | None = None,
        note: str = "",
        set_main_status: bool = True,
    ):
        if action not in ("BUY", "SELL"):
            return False

        parts = []
        if diff is not None:
            parts.append(f"diff={diff:.6f}")
        if note:
            parts.append(note)
        details = " | ".join(parts)
        self.record_order_action(action, trigger_source, details, "IN_APP_SIM")
        if self.live_trades_enabled_value.get() and self.running:
            command_slot = self.get_live_trade_command_slot(action, trigger_source)
            self.enqueue_live_trade_command(command_slot, action, trigger_source, diff, note)
        if set_main_status:
            self.set_status(f"{action} paper trade ({trigger_source})", "warn")
        return True

    def set_status(self, text: str, level: str = "warn"):
        style = {
            "ok": "StatusOk.TLabel",
            "warn": "StatusWarn.TLabel",
            "err": "StatusErr.TLabel",
        }.get(level, "StatusWarn.TLabel")
        self.status_label.configure(style=style)
        self.status_value.set(text)

    def update_data_tab_button_text(self):
        if self.tabs is None or self.data_tab is None:
            return
        current_tab = self.tabs.select()
        if current_tab == str(self.data_tab):
            self.data_tab_button_text.set("Close Data Tab")
        else:
            self.data_tab_button_text.set("Open Data Tab")

    def on_tab_changed(self, _event=None):
        self.update_data_tab_button_text()

    def toggle_data_tab(self):
        if self.tabs is None or self.data_tab is None or self.monitor_tab is None:
            return
        current_tab = self.tabs.select()
        if current_tab == str(self.data_tab):
            self.tabs.select(self.monitor_tab)
        else:
            self.tabs.select(self.data_tab)
        self.update_data_tab_button_text()

    def start_monitoring(self):
        if self.running:
            return

        try:
            interval = float(self.interval_value.get().strip())
            if interval < 0.2:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid interval", "Please enter a valid number (>= 0.2 seconds).")
            return

        if not self.start_extension_server():
            messagebox.showerror(
                "Extension Feed Error",
                "Could not start the local extension feed server. Check the port and try again.",
            )
            return

        self.running = True
        self.last_auto_signal = 0
        self.auto_position_side = 0
        self.auto_entry_diff = None
        self.auto_entry_meta = None
        self.sl_rearm_required = False
        self.refresh_trade_timing_display()
        self.refresh_total_profit_loss()
        self.auto_sim_status_value.set("Armed")
        self.update_learning_status_text()
        self.set_status("Monitoring...", "ok")
        self.save_app_settings()
        self.refresh_feed_health_display()
        self.worker = threading.Thread(target=self.monitor_extension_loop, args=(interval,), daemon=True)
        self.worker.start()

    def stop_monitoring(self):
        self.running = False
        self.last_auto_signal = 0
        self.auto_position_side = 0
        self.auto_entry_diff = None
        self.auto_entry_meta = None
        self.sl_rearm_required = False
        self.refresh_trade_timing_display()
        self.refresh_total_profit_loss()
        self.auto_sim_status_value.set("Paused")
        self.update_learning_status_text()
        self.stop_extension_server()
        self.set_status("Stopped", "warn")
        self.save_app_settings()

    def extract_number_from_text(self, text: str):
        best_value = None
        best_score = -1
        for token in NUMBER_PATTERN.findall(text or ""):
            value = parse_number_token(token)
            if value is None:
                continue
            score = sum(ch.isdigit() for ch in token)
            if score > best_score:
                best_score = score
                best_value = value
        return best_value, best_score

    def update_preview(self, label: ttk.Label, placeholder: str):
        label.configure(text=placeholder)

    def publish_state(self, left_num, right_num):
        """Update all display values from extension data."""
        self.refresh_feed_health_display()
        self.left_value.set(format_number(left_num))
        self.right_value.set(format_number(right_num))

        if left_num is None or right_num is None:
            self.diff_value.set("-")
            self.profit_loss_value.set("-")
            self.last_auto_signal = 0
            self.last_diff_logged_key = None
            self.refresh_total_profit_loss()
            if self.running:
                self.auto_sim_status_value.set("Waiting for data")
            else:
                self.auto_sim_status_value.set("Idle")
            self.set_status("Could not read one or both numbers", "warn")
            return

        diff = left_num - right_num
        self.diff_value.set(format_number(diff))
        profit_loss = self.calculate_profit_loss(diff)
        self.profit_loss_value.set("Config error" if profit_loss is None else format_currency(profit_loss))
        self.maybe_trigger_auto_sim_trade(diff, left_num, right_num)
        self.refresh_total_profit_loss(left_num)
        if diff == 0:
            self.set_status("Numbers match", "ok")
        else:
            self.set_status("Difference detected", "err")

    def monitor_extension_loop(self, interval: float):
        while self.running:
            with self.extension_lock:
                topstep_num = self.extension_values.get("topstep")
                tradovate_num = self.extension_values.get("tradovate")
                topstep_text = self.extension_texts.get("topstep", "")
                tradovate_text = self.extension_texts.get("tradovate", "")

            # Notes removed - no longer using preview labels in new card layout
            # left_note = "Extension Topstep:\n" + topstep_text if topstep_text else "Waiting for Topstep extension feed..."
            # right_note = "Extension Tradovate:\n" + tradovate_text if tradovate_text else "Waiting for Tradovate extension feed..."

            self.after(
                0,
                self.publish_state,
                topstep_num,
                tradovate_num,
            )
            sleep_interval = interval
            if self.auto_position_side != 0:
                sleep_interval = min(interval, 0.1)
            time.sleep(sleep_interval)

    def on_close(self):
        self.running = False
        self.save_app_settings()
        self.save_learning_state()
        if self.utc_clock_job is not None:
            self.after_cancel(self.utc_clock_job)
            self.utc_clock_job = None
        self.stop_extension_server()
        self.destroy()
