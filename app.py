import csv
import json
import os
import re
import threading
import time
import tkinter as tk
from datetime import datetime, time as dt_time, timedelta, timezone
from tkinter import messagebox, ttk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from collections import deque


NUMBER_PATTERN = re.compile(r"-?\d[\d.,]*")
TIME_INPUT_PATTERN = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$")
UTC_MINUS_5 = timezone(timedelta(hours=-5))
FEED_STALE_AFTER_SECONDS = 3.0


def parse_number_token(token: str):
    cleaned = token.strip().replace(" ", "")
    if not cleaned:
        return None

    sign = -1 if cleaned.startswith("-") else 1
    cleaned = cleaned.lstrip("+-")
    if not cleaned or not any(ch.isdigit() for ch in cleaned):
        return None

    if "," not in cleaned and "." not in cleaned:
        try:
            return sign * float(cleaned)
        except ValueError:
            return None

    if "," in cleaned and "." in cleaned:
        decimal_sep = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        normalized = cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")
        try:
            return sign * float(normalized)
        except ValueError:
            return None

    sep = "," if "," in cleaned else "."
    parts = cleaned.split(sep)
    if not all(part.isdigit() for part in parts):
        return None

    if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
        # 24,000 or 1.234.567 style grouping.
        normalized = "".join(parts)
    elif len(parts) == 2 and len(parts[1]) == 3:
        # Prefer thousand grouping when exactly 3 digits follow separator.
        normalized = "".join(parts)
    else:
        normalized = ".".join(parts)

    try:
        return sign * float(normalized)
    except ValueError:
        return None


def format_number(value):
    if value is None:
        return "-"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.6f}".rstrip("0").rstrip(".")


def format_currency(value):
    if value is None:
        return "-"
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


class NumberDiffApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Number Difference Monitor")
        self.geometry("1100x760")
        self.minsize(1000, 660)

        self.left_value = tk.StringVar(value="-")
        self.right_value = tk.StringVar(value="-")
        self.diff_value = tk.StringVar(value="-")
        self.profit_loss_value = tk.StringVar(value="-")
        self.total_profit_loss_value = tk.StringVar(value="$0.00")
        self.status_value = tk.StringVar(value="Idle")
        self.interval_value = tk.StringVar(value="0.3")
        self.contract_size_value = tk.StringVar(value="1")
        self.point_value_value = tk.StringVar(value="20")
        self.difference_count_value = tk.StringVar(value="0")
        self.extension_port_value = tk.StringVar(value="8765")
        self.extension_status_value = tk.StringVar(value="Stopped")
        self.topstep_feed_status_value = tk.StringVar(value="Idle")
        self.tradovate_feed_status_value = tk.StringVar(value="Idle")
        self.topstep_updated_value = tk.StringVar(value="-")
        self.tradovate_updated_value = tk.StringVar(value="-")
        self.analytics_total_events_value = tk.StringVar(value="0")
        self.analytics_closed_trades_value = tk.StringVar(value="0")
        self.analytics_win_rate_value = tk.StringVar(value="-")
        self.analytics_realized_pnl_value = tk.StringVar(value="$0.00")
        self.analytics_avg_win_value = tk.StringVar(value="-")
        self.analytics_avg_loss_value = tk.StringVar(value="-")
        self.history_filter_value = tk.StringVar(value="All")
        self.history_limit_value = tk.StringVar(value="250")
        self.auto_sim_threshold_value = tk.StringVar(value="1")
        self.auto_sim_cooldown_value = tk.StringVar(value="3")
        self.stop_loss_points_value = tk.StringVar(value="5")
        self.take_profit_points_value = tk.StringVar(value="5")
        self.trade_window_enabled_value = tk.BooleanVar(value=False)
        self.trade_window_start_value = tk.StringVar(value="08:30")
        self.trade_window_end_value = tk.StringVar(value="15:00")
        self.utc_minus5_time_value = tk.StringVar(value="-")
        self.current_session_value = tk.StringVar(value="-")
        self.data_tab_button_text = tk.StringVar(value="Open Data Tab")
        self.entry_time_value = tk.StringVar(value="-")
        self.entry_number_value = tk.StringVar(value="-")
        self.entry_side_value = tk.StringVar(value="-")
        self.time_in_trade_value = tk.StringVar(value="-")
        self.learning_enabled_value = tk.BooleanVar(value=True)
        self.learning_status_value = tk.StringVar(value="On | waiting for trades")
        self.auto_sim_status_value = tk.StringVar(value="Idle")
        self.order_count_value = tk.StringVar(value="0")
        self.live_trades_enabled_value = tk.BooleanVar(value=False)

        self.running = False
        self.worker = None
        self.difference_count = 0
        self.order_count = 0

        self.last_diff_logged_key = None
        self.history_tree = None
        self.order_history_tree = None
        self.tabs = None
        self.monitor_tab = None
        self.data_tab = None
        self.log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "difference_log.csv")
        self.order_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "order_action_log.csv")
        self.learning_state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learning_state.json")
        self.app_settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_settings.json")
        self.extension_server = None
        self.extension_server_thread = None
        self.extension_lock = threading.Lock()
        self.utc_clock_job = None
        self.extension_values = {"topstep": None, "tradovate": None}
        self.extension_texts = {"topstep": "", "tradovate": ""}
        self.extension_last_received_epoch = {"topstep": None, "tradovate": None}
        self.live_trade_commands = deque()
        self.live_trade_command_seq = 0
        self.last_auto_signal = 0
        self.last_auto_trade_at = 0.0
        self.auto_position_side = 0
        self.auto_entry_diff = None
        self.auto_entry_meta = None
        self.sl_rearm_required = False
        self.realized_total_profit_loss = 0.0
        self.session_profiles = {
            "New York": {"threshold_offset": 0.0, "cooldown_mult": 1.0, "tp_offset": 0.0, "sl_offset": 0.0, "trades": []},
            "London": {"threshold_offset": 0.0, "cooldown_mult": 1.0, "tp_offset": 0.0, "sl_offset": 0.0, "trades": []},
            "Asia": {"threshold_offset": 0.0, "cooldown_mult": 1.0, "tp_offset": 0.0, "sl_offset": 0.0, "trades": []},
        }
        self.session_stats_tree = None
        self.learning_trade_samples = []
        self._loading_settings = False

        self.load_app_settings()
        self.build_ui()
        self.setup_settings_autosave()
        self.load_difference_history()
        self.load_order_history()
        self.load_learning_state()

    def build_ui(self):
        """Build a professional dashboard-style UI with sidebar navigation."""
        bg_dark = "#1a1a2e"
        bg_card = "#16213e"
        accent_teal = "#0f3460"
        accent_green = "#00d9a3"
        accent_red = "#e94560"
        text_light = "#e0e0e0"
        
        self.configure(bg=bg_dark)
        
        # Configure styles
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("TFrame", background=bg_dark)
        style.configure("TLabel", background=bg_dark, foreground=text_light)
        style.configure("TLabelframe", background=bg_dark, foreground=text_light, borderwidth=1)
        style.configure("TLabelframe.Label", background=bg_dark, foreground=accent_green, font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", fieldbackground="#0f3460", foreground=text_light, borderwidth=1)
        style.configure("TButton", background=accent_teal, foreground=text_light, padding=6, borderwidth=0)
        style.map("TButton", background=[("active", accent_green)])
        style.configure("LiveOn.TButton", background=accent_green, foreground="#0b1f1a", padding=6, borderwidth=0)
        style.map("LiveOn.TButton", background=[("active", "#34e6b8")])
        style.configure("LiveOff.TButton", background=accent_red, foreground=text_light, padding=6, borderwidth=0)
        style.map("LiveOff.TButton", background=[("active", "#ff6b81")])
        style.configure("Treeview", background="#0f3460", foreground=text_light, fieldbackground="#0f3460", borderwidth=0)
        style.configure("Treeview.Heading", background="#16213e", foreground=accent_green, font=("Segoe UI", 9, "bold"))
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground=accent_green, background=bg_dark)
        style.configure("Card.TLabel", font=("Segoe UI", 11, "bold"), foreground=accent_green, background=bg_dark)
        style.configure("Value.TLabel", font=("Segoe UI", 20, "bold"), foreground=accent_green, background=bg_dark)
        style.configure("StatusOk.TLabel", foreground=accent_green, font=("Segoe UI", 11, "bold"), background=bg_dark)
        style.configure("StatusWarn.TLabel", foreground="#ffa500", font=("Segoe UI", 11, "bold"), background=bg_dark)
        style.configure("StatusErr.TLabel", foreground=accent_red, font=("Segoe UI", 11, "bold"), background=bg_dark)
        
        # Main container with sidebar
        main_container = ttk.Frame(self)
        main_container.pack(fill="both", expand=True)
        
        # SIDEBAR
        sidebar = tk.Frame(main_container, bg=accent_teal, width=80)
        sidebar.pack(side="left", fill="y", padx=0, pady=0)
        sidebar.pack_propagate(False)
        
        ttk.Label(sidebar, text="📊", font=("Segoe UI", 24), background=accent_teal, foreground=accent_green).pack(pady=(20, 40), padx=10)
        
        self.nav_monitor_btn = tk.Button(sidebar, text="Monitor", bg=accent_teal, fg=accent_green, font=("Segoe UI", 10, "bold"), 
                                         relief="flat", command=lambda: self.switch_view("monitor"), width=10)
        self.nav_monitor_btn.pack(pady=10, padx=5)
        
        self.nav_analytics_btn = tk.Button(sidebar, text="Analytics", bg=accent_teal, fg=text_light, font=("Segoe UI", 10), 
                                           relief="flat", command=lambda: self.switch_view("analytics"), width=10)
        self.nav_analytics_btn.pack(pady=10, padx=5)
        
        self.nav_settings_btn = tk.Button(sidebar, text="Settings", bg=accent_teal, fg=text_light, font=("Segoe UI", 10), 
                                          relief="flat", command=lambda: self.switch_view("settings"), width=10)
        self.nav_settings_btn.pack(pady=10, padx=5)
        
        # Main content area
        content = ttk.Frame(main_container)
        content.pack(side="left", fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        
        # Views container
        self.views_container = ttk.Frame(content)
        self.views_container.grid(row=0, column=0, sticky="nsew")
        self.views_container.columnconfigure(0, weight=1)
        self.views_container.rowconfigure(0, weight=1)
        
        # Build views
        self.monitor_view = self.build_monitor_view()
        self.analytics_view = self.build_analytics_view()
        self.settings_view = self.build_settings_view()
        
        # Start with monitor view
        self.switch_view("monitor")
        
        self.update_data_tab_button_text()
        self.refresh_session_stats_table()
        self.start_utc_minus5_clock()
    
    def switch_view(self, view_name):
        """Switch between different views."""
        # Hide all views
        for view in [self.monitor_view, self.analytics_view, self.settings_view]:
            view.grid_forget()
        
        # Update button colors
        for btn, name in [(self.nav_monitor_btn, "monitor"), (self.nav_analytics_btn, "analytics"), (self.nav_settings_btn, "settings")]:
            if name == view_name:
                btn.config(fg="#00d9a3")
            else:
                btn.config(fg="#e0e0e0")
        
        # Show selected view
        if view_name == "monitor":
            self.monitor_view.grid(row=0, column=0, sticky="nsew")
        elif view_name == "analytics":
            self.analytics_view.grid(row=0, column=0, sticky="nsew")
        elif view_name == "settings":
            self.settings_view.grid(row=0, column=0, sticky="nsew")
    
    def build_monitor_view(self):
        """Build the monitoring dashboard view - compact 2-column layout without scrolling."""
        view = ttk.Frame(self.views_container)
        view.columnconfigure(0, weight=1)
        view.rowconfigure(1, weight=1)
        
        # Header
        header = ttk.Frame(view)
        header.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="🚀 Trading Monitor", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        
        # Control buttons
        btn_frame = ttk.Frame(header)
        btn_frame.grid(row=0, column=2, sticky="e")
        ttk.Button(btn_frame, text="▶ Start", command=self.start_monitoring).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="⏹ Stop", command=self.stop_monitoring).pack(side="left", padx=3)
        live_toggle_btn = ttk.Button(btn_frame, command=self.toggle_live_trades)
        live_toggle_btn.pack(side="left", padx=3)

        def update_live_toggle_btn(*_args):
            is_live = self.live_trades_enabled_value.get()
            text = "🟢 Live ON" if is_live else "🔴 Live OFF"
            style_name = "LiveOn.TButton" if is_live else "LiveOff.TButton"
            live_toggle_btn.configure(text=text, style=style_name)

        self.live_trades_enabled_value.trace_add("write", update_live_toggle_btn)
        update_live_toggle_btn()
        
        # Main content frame with 2 columns (no scrolling)
        content = ttk.Frame(view)
        content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        
        # LEFT COLUMN
        left = ttk.Frame(content)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.columnconfigure(0, weight=1)
        
        # Extension Feed (compact)
        ext_card = self.create_card(left, "📡 Extension Feed")
        ext_card.columnconfigure(1, weight=1)
        ext_card.columnconfigure(3, weight=1)
        
        ttk.Label(ext_card, text="Port:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=10, pady=4)
        ttk.Entry(ext_card, textvariable=self.extension_port_value, width=8).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Button(ext_card, text="Test", command=self.test_extension_connection).grid(row=0, column=2, columnspan=2, sticky="w", padx=8, pady=2)
        
        ttk.Label(ext_card, text="Server:", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        ttk.Label(ext_card, textvariable=self.extension_status_value, foreground="#00d9a3").grid(row=1, column=1, columnspan=3, sticky="w", padx=8)

        ttk.Label(ext_card, text="Topstep:", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=10, pady=3)
        ttk.Label(ext_card, textvariable=self.topstep_feed_status_value, foreground="#00d9ff").grid(row=2, column=1, sticky="w", padx=8)
        ttk.Label(ext_card, text="Updated:", style="Card.TLabel").grid(row=2, column=2, sticky="w", padx=10)
        ttk.Label(ext_card, textvariable=self.topstep_updated_value, foreground="#e0e0e0").grid(row=2, column=3, sticky="w", padx=8)

        ttk.Label(ext_card, text="Tradovate:", style="Card.TLabel").grid(row=3, column=0, sticky="w", padx=10, pady=3)
        ttk.Label(ext_card, textvariable=self.tradovate_feed_status_value, foreground="#00d9ff").grid(row=3, column=1, sticky="w", padx=8)
        ttk.Label(ext_card, text="Updated:", style="Card.TLabel").grid(row=3, column=2, sticky="w", padx=10)
        ttk.Label(ext_card, textvariable=self.tradovate_updated_value, foreground="#e0e0e0").grid(row=3, column=3, sticky="w", padx=8)
        
        # Trading Config (compact)
        trade_card = self.create_card(left, "⚙️ Trading Config")
        trade_card.columnconfigure(1, weight=1)
        trade_card.columnconfigure(3, weight=1)
        
        ttk.Label(trade_card, text="Interval:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=10, pady=3)
        ttk.Entry(trade_card, textvariable=self.interval_value, width=6).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(trade_card, text="Min Diff:", style="Card.TLabel").grid(row=0, column=2, sticky="w", padx=10)
        ttk.Entry(trade_card, textvariable=self.auto_sim_threshold_value, width=6).grid(row=0, column=3, sticky="w", padx=8)
        
        ttk.Label(trade_card, text="Cooldown:", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=10, pady=3)
        ttk.Entry(trade_card, textvariable=self.auto_sim_cooldown_value, width=6).grid(row=1, column=1, sticky="w", padx=8)
        ttk.Label(trade_card, text="Contracts:", style="Card.TLabel").grid(row=1, column=2, sticky="w", padx=10)
        ttk.Entry(trade_card, textvariable=self.contract_size_value, width=6).grid(row=1, column=3, sticky="w", padx=8)
        
        ttk.Label(trade_card, text="SL (pts):", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=10, pady=3)
        ttk.Entry(trade_card, textvariable=self.stop_loss_points_value, width=6).grid(row=2, column=1, sticky="w", padx=8)
        ttk.Label(trade_card, text="TP (pts):", style="Card.TLabel").grid(row=2, column=2, sticky="w", padx=10)
        ttk.Entry(trade_card, textvariable=self.take_profit_points_value, width=6).grid(row=2, column=3, sticky="w", padx=8)
        
        # RIGHT COLUMN
        right = ttk.Frame(content)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.columnconfigure(0, weight=1)
        
        # Live Metrics
        metrics_card = self.create_card(right, "📊 Live Metrics")
        metrics_card.columnconfigure(1, weight=1)
        metrics_card.columnconfigure(3, weight=1)
        
        ttk.Label(metrics_card, text="Topstep:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.left_value, style="Value.TLabel").grid(row=0, column=1, sticky="w", padx=8)
        
        ttk.Label(metrics_card, text="Tradovate:", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.right_value, style="Value.TLabel").grid(row=1, column=1, sticky="w", padx=8)
        
        ttk.Label(metrics_card, text="Difference:", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.diff_value, style="Value.TLabel", foreground="#00d9ff").grid(row=2, column=1, sticky="w", padx=8)
        
        ttk.Label(metrics_card, text="P/L:", style="Card.TLabel").grid(row=3, column=0, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.profit_loss_value, style="Value.TLabel").grid(row=3, column=1, sticky="w", padx=8)
        
        ttk.Label(metrics_card, text="Total P/L:", style="Card.TLabel").grid(row=4, column=0, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.total_profit_loss_value, style="Value.TLabel").grid(row=4, column=1, sticky="w", padx=8)

        ttk.Label(metrics_card, text="Entry #:", style="Card.TLabel").grid(row=5, column=0, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.entry_number_value, style="Value.TLabel").grid(row=5, column=1, sticky="w", padx=8)
        ttk.Label(metrics_card, text="Side:", style="Card.TLabel").grid(row=5, column=2, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.entry_side_value, style="Value.TLabel").grid(row=5, column=3, sticky="w", padx=8)
        
        ttk.Label(metrics_card, text="Time In Trade:", style="Card.TLabel").grid(row=6, column=0, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.time_in_trade_value, style="Value.TLabel").grid(row=6, column=1, sticky="w", padx=8)
        ttk.Label(metrics_card, text="Session:", style="Card.TLabel").grid(row=6, column=2, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.current_session_value, style="Value.TLabel").grid(row=6, column=3, sticky="w", padx=8)
        
        # Live Trade Mirror
        mirror_card = self.create_card(right, "🔄 Live Trade Mirror")
        mirror_card.columnconfigure(1, weight=1)
        
        ttk.Label(mirror_card, text="Status:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=10, pady=3)
        self.status_label = ttk.Label(mirror_card, textvariable=self.status_value, style="StatusWarn.TLabel")
        self.status_label.grid(row=0, column=1, sticky="w", padx=8)
        
        ttk.Label(mirror_card, text="Live Trading:", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=10, pady=3)
        live_trades_mirror_label = ttk.Label(mirror_card, style="Value.TLabel")
        live_trades_mirror_label.grid(row=1, column=1, sticky="w", padx=8)
        
        def update_live_trades_mirror_label(*_args):
            status = "🟢 ENABLED" if self.live_trades_enabled_value.get() else "🔴 DISABLED"
            live_trades_mirror_label.configure(text=status, foreground="#00d9a3" if self.live_trades_enabled_value.get() else "#ff6b6b")
        
        self.live_trades_enabled_value.trace_add("write", update_live_trades_mirror_label)
        update_live_trades_mirror_label()
        
        return view
    
    def build_analytics_view(self):
        """Build the analytics and performance view."""
        view = ttk.Frame(self.views_container)
        view.columnconfigure(0, weight=1)
        view.rowconfigure(0, weight=0)
        view.rowconfigure(1, weight=1)
        
        # Header
        header = ttk.Frame(view)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        ttk.Label(header, text="📈 Analytics & Performance", style="Title.TLabel").pack(side="left")
        
        # Scroll area
        scroll_frame = ttk.Frame(view)
        scroll_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        scroll_frame.columnconfigure(0, weight=1)
        scroll_frame.rowconfigure(0, weight=1)
        
        canvas = tk.Canvas(scroll_frame, bg="#1a1a2e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        
        scrollable.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.bind_mousewheel_scroll(canvas, scrollable)

        # Performance summary
        summary_card = self.create_card(scrollable, "Performance Summary")
        summary_card.columnconfigure(1, weight=1)
        summary_card.columnconfigure(3, weight=1)

        ttk.Label(summary_card, text="Total Events:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=15, pady=8)
        ttk.Label(summary_card, textvariable=self.analytics_total_events_value, foreground="#00d9a3").grid(row=0, column=1, sticky="w", padx=10)
        ttk.Label(summary_card, text="Closed Trades:", style="Card.TLabel").grid(row=0, column=2, sticky="w", padx=15)
        ttk.Label(summary_card, textvariable=self.analytics_closed_trades_value, foreground="#00d9ff").grid(row=0, column=3, sticky="w", padx=10)

        ttk.Label(summary_card, text="Win Rate:", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=15, pady=8)
        ttk.Label(summary_card, textvariable=self.analytics_win_rate_value, foreground="#00d9a3").grid(row=1, column=1, sticky="w", padx=10)
        ttk.Label(summary_card, text="Realized P/L:", style="Card.TLabel").grid(row=1, column=2, sticky="w", padx=15)
        ttk.Label(summary_card, textvariable=self.analytics_realized_pnl_value, foreground="#00d9ff").grid(row=1, column=3, sticky="w", padx=10)

        ttk.Label(summary_card, text="Avg Win:", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=15, pady=8)
        ttk.Label(summary_card, textvariable=self.analytics_avg_win_value, foreground="#00d9a3").grid(row=2, column=1, sticky="w", padx=10)
        ttk.Label(summary_card, text="Avg Loss:", style="Card.TLabel").grid(row=2, column=2, sticky="w", padx=15)
        ttk.Label(summary_card, textvariable=self.analytics_avg_loss_value, foreground="#e94560").grid(row=2, column=3, sticky="w", padx=10)
        
        # Session performance
        session_card = self.create_card(scrollable, "Session Performance")
        session_frame = ttk.Frame(session_card)
        session_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        session_columns = ("session", "trades", "wins", "losses", "win_rate", "thr_offset", "cooldown_mult", "tp_offset", "sl_offset")
        self.session_stats_tree = ttk.Treeview(session_frame, columns=session_columns, show="headings", height=4)
        self.session_stats_tree.heading("session", text="Session")
        self.session_stats_tree.heading("trades", text="Trades")
        self.session_stats_tree.heading("wins", text="Wins")
        self.session_stats_tree.heading("losses", text="Losses")
        self.session_stats_tree.heading("win_rate", text="Win Rate")
        self.session_stats_tree.heading("thr_offset", text="Thr Offset")
        self.session_stats_tree.heading("cooldown_mult", text="Cooldown x")
        self.session_stats_tree.heading("tp_offset", text="TP Offset")
        self.session_stats_tree.heading("sl_offset", text="SL Offset")
        
        for col in session_columns:
            width = 100 if col == "session" else 70
            self.session_stats_tree.column(col, width=width, anchor="e" if col != "session" else "w")
        
        self.session_stats_tree.pack(fill="both", expand=True)
        
        # Trade history
        history_card = self.create_card(scrollable, "Trade History")
        history_frame = ttk.Frame(history_card)
        history_frame.pack(fill="both", expand=True, padx=10, pady=10)
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(1, weight=0)
        history_frame.rowconfigure(2, weight=1)
        
        toolbar = ttk.Frame(history_frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ttk.Button(toolbar, text="Clear History", command=self.clear_difference_history).pack(side="left")
        ttk.Label(toolbar, text="Result:").pack(side="left", padx=(12, 4))
        result_filter = ttk.Combobox(toolbar, textvariable=self.history_filter_value, values=("All", "Closed", "Wins", "Losses", "Entries", "Unlabeled"), state="readonly", width=10)
        result_filter.pack(side="left")
        ttk.Label(toolbar, text="Rows:").pack(side="left", padx=(12, 4))
        row_limit = ttk.Combobox(toolbar, textvariable=self.history_limit_value, values=("50", "100", "250", "500", "1000", "All"), state="readonly", width=8)
        row_limit.pack(side="left")
        ttk.Button(toolbar, text="Refresh", command=self.load_difference_history).pack(side="left", padx=(12, 0))
        
        columns = ("timestamp", "topstep", "tradovate", "difference", "result", "p_l")
        self.history_tree = ttk.Treeview(history_frame, columns=columns, show="headings", height=8)
        self.history_tree.heading("timestamp", text="Timestamp")
        self.history_tree.heading("topstep", text="Topstep")
        self.history_tree.heading("tradovate", text="Tradovate")
        self.history_tree.heading("difference", text="Difference")
        self.history_tree.heading("result", text="Result")
        self.history_tree.heading("p_l", text="P/L")
        
        self.history_tree.column("timestamp", width=200, anchor="center")
        self.history_tree.column("topstep", width=120, anchor="e")
        self.history_tree.column("tradovate", width=120, anchor="e")
        self.history_tree.column("difference", width=120, anchor="e")
        self.history_tree.column("result", width=90, anchor="center")
        self.history_tree.column("p_l", width=100, anchor="e")
        
        self.history_tree.tag_configure("trade_win", foreground="#00d970", background="#0a3f1f")
        self.history_tree.tag_configure("trade_loss", foreground="#e94560", background="#3f0a0a")
        
        self.history_tree.grid(row=2, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        self.history_filter_value.trace_add("write", self.on_history_filter_changed)
        self.history_limit_value.trace_add("write", self.on_history_filter_changed)
        
        return view
    
    def build_settings_view(self):
        """Build the settings view - compact 2-column layout."""
        view = ttk.Frame(self.views_container)
        view.columnconfigure(0, weight=1)
        view.rowconfigure(1, weight=1)
        
        # Header
        header = ttk.Frame(view)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 10))
        ttk.Label(header, text="⚙️ Settings", style="Title.TLabel").pack(side="left")
        
        # Main content frame with two columns
        content = ttk.Frame(view)
        content.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        
        # LEFT COLUMN
        left = ttk.Frame(content)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        left.columnconfigure(0, weight=1)
        
        # Time Window Card (compact)
        time_card = self.create_card(left, "🕐 Trading Time Window")
        time_card.columnconfigure(1, weight=1)
        time_card.columnconfigure(3, weight=1)
        
        ttk.Checkbutton(time_card, text="Enable Time Window", variable=self.trade_window_enabled_value).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=5)
        
        ttk.Label(time_card, text="Start:", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        ttk.Entry(time_card, textvariable=self.trade_window_start_value, width=10).grid(row=1, column=1, sticky="w", padx=8)
        
        ttk.Label(time_card, text="End:", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        ttk.Entry(time_card, textvariable=self.trade_window_end_value, width=10).grid(row=2, column=1, sticky="w", padx=8)
        
        ttk.Label(time_card, text="UTC-5:", style="Card.TLabel").grid(row=3, column=0, sticky="w", padx=12, pady=4)
        ttk.Label(time_card, textvariable=self.utc_minus5_time_value, foreground="#00d9a3").grid(row=3, column=1, sticky="w", padx=8)
        
        # Live Trades Card (compact)
        live_card = self.create_card(left, "🚀 Live Trading")
        live_card.columnconfigure(1, weight=1)
        
        ttk.Label(live_card, text="Status:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=4)
        live_trades_label = ttk.Label(live_card, style="Value.TLabel")
        live_trades_label.grid(row=0, column=1, sticky="w", padx=8)
        
        def update_live_trades_label(*_args):
            status = "🟢 ENABLED" if self.live_trades_enabled_value.get() else "🔴 DISABLED"
            live_trades_label.configure(text=status, foreground="#00d9a3" if self.live_trades_enabled_value.get() else "#ff6b6b")
        
        toggle_btn = ttk.Button(live_card, text="Toggle Live Trades", command=self.toggle_live_trades)
        toggle_btn.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
        
        self.live_trades_enabled_value.trace_add("write", update_live_trades_label)
        update_live_trades_label()
        
        # RIGHT COLUMN
        right = ttk.Frame(content)
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        right.columnconfigure(0, weight=1)
        
        # Trade Info Card (compact)
        info_card = self.create_card(right, "📋 Trade Information")
        info_card.columnconfigure(1, weight=1)
        
        ttk.Label(info_card, text="Trade Events:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=4)
        ttk.Label(info_card, textvariable=self.difference_count_value, style="Value.TLabel", foreground="#00d9a3").grid(row=0, column=1, sticky="w", padx=8)
        
        ttk.Label(info_card, text="Sim Trades:", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=12, pady=4)
        ttk.Label(info_card, textvariable=self.order_count_value, style="Value.TLabel", foreground="#00d9a3").grid(row=1, column=1, sticky="w", padx=8)
        
        ttk.Label(info_card, text="Entry Time:", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=12, pady=4)
        ttk.Label(info_card, textvariable=self.entry_time_value, foreground="#00d9ff").grid(row=2, column=1, sticky="w", padx=8)
        
        ttk.Label(info_card, text="Entry #:", style="Card.TLabel").grid(row=3, column=0, sticky="w", padx=12, pady=4)
        ttk.Label(info_card, textvariable=self.entry_number_value, foreground="#00d9ff").grid(row=3, column=1, sticky="w", padx=8)
        
        ttk.Label(info_card, text="Time In Trade:", style="Card.TLabel").grid(row=4, column=0, sticky="w", padx=12, pady=4)
        ttk.Label(info_card, textvariable=self.time_in_trade_value, foreground="#00d9a3").grid(row=4, column=1, sticky="w", padx=8)
        
        return view
    
    def create_card(self, parent, title):
        """Create a styled card widget."""
        card = tk.Frame(parent, bg="#16213e", relief="flat", bd=1, highlightbackground="#0f3460", highlightthickness=1)
        card.pack(fill="x", pady=10)
        
        # Card title
        title_label = tk.Label(card, text=title, bg="#16213e", fg="#00d9a3", font=("Segoe UI", 11, "bold"), anchor="w")
        title_label.pack(fill="x", padx=12, pady=(10, 8))
        
        # Separator
        sep = tk.Frame(card, bg="#0f3460", height=1)
        sep.pack(fill="x", padx=10)
        
        # Content frame
        content = ttk.Frame(card)
        content.pack(fill="both", expand=True, padx=0, pady=0)
        
        return content

    def bind_mousewheel_scroll(self, canvas, scrollable):
        """Enable mouse wheel scrolling for a canvas while pointer is over the view."""
        def on_mousewheel(event):
            if event.delta:
                canvas.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")

        def bind_wheel(_event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", on_mousewheel)
            canvas.bind_all("<Button-5>", on_mousewheel)

        def unbind_wheel(_event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", bind_wheel)
        canvas.bind("<Leave>", unbind_wheel)
        scrollable.bind("<Enter>", bind_wheel)
        scrollable.bind("<Leave>", unbind_wheel)

    def ensure_log_file(self):
        expected_header = ["timestamp", "topstep", "tradovate", "difference", "trade_result", "trade_p_l"]
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(expected_header)
            return

        with open(self.log_path, "r", newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            current_header = next(reader, [])

        if current_header == expected_header:
            return

        migrated_rows = []
        with open(self.log_path, "r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                migrated_rows.append(
                    (
                        row.get("timestamp", ""),
                        row.get("topstep", ""),
                        row.get("tradovate", ""),
                        row.get("difference", ""),
                        row.get("trade_result", ""),
                        row.get("trade_p_l", ""),
                    )
                )

        with open(self.log_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(expected_header)
            writer.writerows(migrated_rows)

    def get_app_settings_payload(self):
        return {
            "interval": self.interval_value.get().strip(),
            "contracts": self.contract_size_value.get().strip(),
            "dollars_per_point": self.point_value_value.get().strip(),
            "extension_port": self.extension_port_value.get().strip(),
            "auto_sim_threshold": self.auto_sim_threshold_value.get().strip(),
            "auto_sim_cooldown": self.auto_sim_cooldown_value.get().strip(),
            "stop_loss_points": self.stop_loss_points_value.get().strip(),
            "take_profit_points": self.take_profit_points_value.get().strip(),
            "trade_window_enabled": bool(self.trade_window_enabled_value.get()),
            "trade_window_start": self.trade_window_start_value.get().strip(),
            "trade_window_end": self.trade_window_end_value.get().strip(),
            "live_trades_enabled": bool(self.live_trades_enabled_value.get()),
        }

    def load_app_settings(self):
        if not os.path.exists(self.app_settings_path):
            return
        try:
            with open(self.app_settings_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except Exception:
            return

        if not isinstance(payload, dict):
            return

        self._loading_settings = True
        try:
            self.interval_value.set(str(payload.get("interval", self.interval_value.get())))
            self.contract_size_value.set(str(payload.get("contracts", self.contract_size_value.get())))
            self.point_value_value.set(str(payload.get("dollars_per_point", self.point_value_value.get())))
            self.extension_port_value.set(str(payload.get("extension_port", self.extension_port_value.get())))
            self.auto_sim_threshold_value.set(str(payload.get("auto_sim_threshold", self.auto_sim_threshold_value.get())))
            self.auto_sim_cooldown_value.set(str(payload.get("auto_sim_cooldown", self.auto_sim_cooldown_value.get())))
            self.stop_loss_points_value.set(str(payload.get("stop_loss_points", self.stop_loss_points_value.get())))
            self.take_profit_points_value.set(str(payload.get("take_profit_points", self.take_profit_points_value.get())))
            self.trade_window_enabled_value.set(bool(payload.get("trade_window_enabled", self.trade_window_enabled_value.get())))
            self.trade_window_start_value.set(str(payload.get("trade_window_start", self.trade_window_start_value.get())))
            self.trade_window_end_value.set(str(payload.get("trade_window_end", self.trade_window_end_value.get())))
            self.live_trades_enabled_value.set(bool(payload.get("live_trades_enabled", self.live_trades_enabled_value.get())))
        finally:
            self._loading_settings = False

    def save_app_settings(self):
        if self._loading_settings:
            return
        with open(self.app_settings_path, "w", encoding="utf-8") as file:
            json.dump(self.get_app_settings_payload(), file, indent=2)

    def setup_settings_autosave(self):
        tracked_vars = [
            self.interval_value,
            self.contract_size_value,
            self.point_value_value,
            self.extension_port_value,
            self.auto_sim_threshold_value,
            self.auto_sim_cooldown_value,
            self.stop_loss_points_value,
            self.take_profit_points_value,
            self.trade_window_enabled_value,
            self.trade_window_start_value,
            self.trade_window_end_value,
            self.live_trades_enabled_value,
        ]
        for variable in tracked_vars:
            variable.trace_add("write", self.on_persisted_setting_changed)

    def on_persisted_setting_changed(self, *_args):
        self.save_app_settings()

    def format_feed_updated_at(self, epoch_value):
        if not isinstance(epoch_value, (int, float)):
            return "-"
        dt_value = datetime.fromtimestamp(epoch_value, tz=timezone.utc).astimezone(UTC_MINUS_5)
        return dt_value.strftime("%H:%M:%S")

    def refresh_feed_health_display(self, now_epoch: float | None = None):
        if now_epoch is None:
            now_epoch = time.time()

        for slot, status_var, updated_var in (
            ("topstep", self.topstep_feed_status_value, self.topstep_updated_value),
            ("tradovate", self.tradovate_feed_status_value, self.tradovate_updated_value),
        ):
            last_seen = self.extension_last_received_epoch.get(slot)
            updated_var.set(self.format_feed_updated_at(last_seen))

            if not isinstance(last_seen, (int, float)):
                status_var.set("Waiting" if self.running else "Idle")
                continue

            age = max(0.0, now_epoch - float(last_seen))
            if age <= FEED_STALE_AFTER_SECONDS:
                status_var.set(f"Live ({age:.1f}s ago)")
            else:
                status_var.set(f"Stale ({age:.1f}s ago)")

    def read_difference_history_rows(self):
        self.ensure_log_file()
        rows = []
        with open(self.log_path, "r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                diff_text = row.get("difference", "")
                result_text = str(row.get("trade_result", "")).strip().upper()
                trade_p_l_num = parse_number_token(str(row.get("trade_p_l", "")).strip())
                diff_num = parse_number_token(diff_text)
                p_l_num = trade_p_l_num if trade_p_l_num is not None else (
                    self.calculate_profit_loss(diff_num) if diff_num is not None else None
                )
                rows.append(
                    {
                        "timestamp": row.get("timestamp", ""),
                        "topstep": row.get("topstep", ""),
                        "tradovate": row.get("tradovate", ""),
                        "difference": diff_text,
                        "result": result_text,
                        "p_l_num": p_l_num,
                        "p_l_text": format_currency(p_l_num) if p_l_num is not None else "-",
                    }
                )
        return rows

    def parse_history_limit(self):
        value = self.history_limit_value.get().strip()
        if value.lower() == "all":
            return None
        try:
            parsed = int(value)
            if parsed <= 0:
                return None
            return parsed
        except ValueError:
            return 250

    def filter_history_rows(self, rows):
        filter_name = self.history_filter_value.get().strip().lower()
        filtered = rows
        if filter_name == "closed":
            filtered = [row for row in rows if row["result"] in ("WIN", "LOSS")]
        elif filter_name == "wins":
            filtered = [row for row in rows if row["result"] == "WIN"]
        elif filter_name == "losses":
            filtered = [row for row in rows if row["result"] == "LOSS"]
        elif filter_name == "entries":
            filtered = [row for row in rows if row["result"] == "ENTRY"]
        elif filter_name == "unlabeled":
            filtered = [row for row in rows if not row["result"]]

        limit = self.parse_history_limit()
        if limit is not None:
            filtered = filtered[-limit:]
        return filtered

    def refresh_analytics_summary(self, rows):
        self.analytics_total_events_value.set(str(len(rows)))
        closed_rows = [row for row in rows if row["result"] in ("WIN", "LOSS") and isinstance(row["p_l_num"], (int, float))]
        wins = [row for row in closed_rows if row["result"] == "WIN"]
        losses = [row for row in closed_rows if row["result"] == "LOSS"]
        self.analytics_closed_trades_value.set(str(len(closed_rows)))
        if closed_rows:
            self.analytics_win_rate_value.set(f"{(len(wins) / len(closed_rows)) * 100.0:.1f}%")
            realized_total = sum(float(row["p_l_num"]) for row in closed_rows)
            self.analytics_realized_pnl_value.set(format_currency(realized_total))
        else:
            self.analytics_win_rate_value.set("-")
            self.analytics_realized_pnl_value.set("$0.00")

        if wins:
            avg_win = sum(float(row["p_l_num"]) for row in wins) / len(wins)
            self.analytics_avg_win_value.set(format_currency(avg_win))
        else:
            self.analytics_avg_win_value.set("-")

        if losses:
            avg_loss = sum(float(row["p_l_num"]) for row in losses) / len(losses)
            self.analytics_avg_loss_value.set(format_currency(avg_loss))
        else:
            self.analytics_avg_loss_value.set("-")

    def on_history_filter_changed(self, *_args):
        if self.history_tree is None:
            return
        self.load_difference_history()

    def load_difference_history(self):
        rows = self.read_difference_history_rows()
        self.refresh_analytics_summary(rows)
        self.history_tree.delete(*self.history_tree.get_children())
        filtered_rows = self.filter_history_rows(rows)
        self.difference_count = len(rows)
        for row in filtered_rows:
            values = (
                row["timestamp"],
                row["topstep"],
                row["tradovate"],
                row["difference"],
                row["result"] or "-",
                row["p_l_text"],
            )
            tags = ()
            if row["result"] == "WIN":
                tags = ("trade_win",)
            elif row["result"] == "LOSS":
                tags = ("trade_loss",)
            self.history_tree.insert("", "end", values=values, tags=tags)
        self.difference_count_value.set(str(self.difference_count))
        if filtered_rows:
            self.history_tree.yview_moveto(1.0)

    def clear_difference_history(self):
        self.history_tree.delete(*self.history_tree.get_children())
        self.difference_count = 0
        self.difference_count_value.set("0")
        self.last_diff_logged_key = None
        with open(self.log_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp", "topstep", "tradovate", "difference", "trade_result", "trade_p_l"])
        self.refresh_analytics_summary([])
        self.set_status("Trade history cleared", "ok")

    def record_difference(
        self,
        topstep_num: float,
        tradovate_num: float,
        diff: float,
        trade_result: str = "",
        trade_p_l: float | None = None,
    ):
        timestamp = self.get_utc_minus5_timestamp()
        topstep_text = format_number(topstep_num)
        tradovate_text = format_number(tradovate_num)
        diff_text = format_number(diff)
        p_l_num = trade_p_l if trade_p_l is not None else self.calculate_profit_loss(diff)
        p_l_text = format_currency(p_l_num) if p_l_num is not None else "-"
        normalized_result = trade_result.strip().upper()

        with open(self.log_path, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                (
                    timestamp,
                    topstep_text,
                    tradovate_text,
                    diff_text,
                    normalized_result,
                    "" if trade_p_l is None else f"{trade_p_l:.6f}",
                )
            )
        self.load_difference_history()

    def ensure_order_log_file(self):
        if os.path.exists(self.order_log_path):
            return
        with open(self.order_log_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp", "action", "trigger", "details", "mode"])

    def load_order_history(self):
        self.ensure_order_log_file()
        with open(self.order_log_path, "r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for _row in reader:
                self.order_count += 1
        self.order_count_value.set(str(self.order_count))

    def get_session_name_for_clock(self, clock_value: dt_time):
        def in_window(start: dt_time, end: dt_time):
            if start <= end:
                return start <= clock_value <= end
            return clock_value >= start or clock_value <= end

        if in_window(dt_time(2, 0), dt_time(6, 0)):
            return "London"
        if in_window(dt_time(8, 30), dt_time(15, 0)):
            return "New York"
        if in_window(dt_time(17, 0), dt_time(2, 0)):
            return "Asia"
        return "Off Session"

    def get_current_session_name(self):
        return self.get_session_name_for_clock(self.get_utc_minus5_clock())

    def refresh_session_stats_table(self):
        if self.session_stats_tree is None:
            return
        self.session_stats_tree.delete(*self.session_stats_tree.get_children())
        for session_name in ("New York", "London", "Asia"):
            profile = self.session_profiles.get(session_name, {})
            trades = profile.get("trades", [])
            trade_count = len(trades)
            wins = sum(1 for item in trades if item.get("is_win"))
            losses = trade_count - wins
            win_rate_text = "-" if trade_count == 0 else f"{(wins / trade_count) * 100.0:.1f}%"
            thr_offset = float(profile.get("threshold_offset", 0.0))
            cooldown_mult = float(profile.get("cooldown_mult", 1.0))
            tp_offset = float(profile.get("tp_offset", 0.0))
            sl_offset = float(profile.get("sl_offset", 0.0))
            self.session_stats_tree.insert(
                "",
                "end",
                values=(
                    session_name,
                    str(trade_count),
                    str(wins),
                    str(losses),
                    win_rate_text,
                    f"{thr_offset:+.2f}",
                    f"{cooldown_mult:.2f}",
                    f"{tp_offset:+.2f}",
                    f"{sl_offset:+.2f}",
                ),
            )

    def update_learning_status_text(self):
        if not self.learning_enabled_value.get():
            self.learning_status_value.set("Off")
            self.refresh_session_stats_table()
            return

        current_session = self.get_current_session_name()
        if current_session not in self.session_profiles:
            self.learning_status_value.set("On | Off session (no profile active)")
            self.refresh_session_stats_table()
            return

        profile = self.session_profiles[current_session]
        recent = profile.get("trades", [])[-40:]
        if len(recent) == 0:
            self.learning_status_value.set(f"On | {current_session} waiting for trades")
            self.refresh_session_stats_table()
            return

        wins = sum(1 for item in recent if item.get("is_win"))
        win_rate = (wins / len(recent)) * 100.0
        thr_offset = float(profile.get("threshold_offset", 0.0))
        cooldown_mult = float(profile.get("cooldown_mult", 1.0))
        tp_offset = float(profile.get("tp_offset", 0.0))
        sl_offset = float(profile.get("sl_offset", 0.0))
        self.learning_status_value.set(
            f"On | {current_session} WR {win_rate:.0f}% | Thr {thr_offset:+.2f} | Cd x{cooldown_mult:.2f} | TP {tp_offset:+.2f} | SL {sl_offset:+.2f}"
        )
        self.refresh_session_stats_table()

    def on_learning_toggle(self):
        self.update_learning_status_text()
        self.save_learning_state()

    def save_learning_state(self):
        session_profiles_payload = {}
        for session_name, profile in self.session_profiles.items():
            trades = profile.get("trades", [])
            if not isinstance(trades, list):
                trades = []
            session_profiles_payload[session_name] = {
                "threshold_offset": float(profile.get("threshold_offset", 0.0)),
                "cooldown_mult": float(profile.get("cooldown_mult", 1.0)),
                "tp_offset": float(profile.get("tp_offset", 0.0)),
                "sl_offset": float(profile.get("sl_offset", 0.0)),
                "trades": trades[-300:],
            }

        payload = {
            "enabled": bool(self.learning_enabled_value.get()),
            "session_profiles": session_profiles_payload,
            "samples": self.learning_trade_samples[-500:],
        }
        with open(self.learning_state_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

    def load_learning_state(self):
        if not os.path.exists(self.learning_state_path):
            self.update_learning_status_text()
            return
        try:
            with open(self.learning_state_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except Exception:
            self.update_learning_status_text()
            return

        self.learning_enabled_value.set(bool(payload.get("enabled", True)))
        for session_name in ("New York", "London", "Asia"):
            self.session_profiles[session_name] = {"threshold_offset": 0.0, "cooldown_mult": 1.0, "tp_offset": 0.0, "sl_offset": 0.0, "trades": []}

        loaded_profiles = payload.get("session_profiles", {})
        if isinstance(loaded_profiles, dict) and loaded_profiles:
            for session_name in ("New York", "London", "Asia"):
                profile = loaded_profiles.get(session_name, {})
                try:
                    threshold_offset = float(profile.get("threshold_offset", 0.0))
                except (TypeError, ValueError):
                    threshold_offset = 0.0
                try:
                    cooldown_mult = float(profile.get("cooldown_mult", 1.0))
                except (TypeError, ValueError):
                    cooldown_mult = 1.0
                try:
                    tp_offset = float(profile.get("tp_offset", 0.0))
                except (TypeError, ValueError):
                    tp_offset = 0.0
                try:
                    sl_offset = float(profile.get("sl_offset", 0.0))
                except (TypeError, ValueError):
                    sl_offset = 0.0
                trades = profile.get("trades", [])
                if not isinstance(trades, list):
                    trades = []
                self.session_profiles[session_name] = {
                    "threshold_offset": max(-0.8, min(3.0, threshold_offset)),
                    "cooldown_mult": max(0.5, min(3.0, cooldown_mult)),
                    "tp_offset": max(-2.0, min(5.0, tp_offset)),
                    "sl_offset": max(-2.0, min(5.0, sl_offset)),
                    "trades": trades[-300:],
                }
        else:
            # Backward compatibility with previous single-profile learning file.
            try:
                fallback_offset = float(payload.get("threshold_offset", 0.0))
            except (TypeError, ValueError):
                fallback_offset = 0.0
            try:
                fallback_mult = float(payload.get("cooldown_mult", 1.0))
            except (TypeError, ValueError):
                fallback_mult = 1.0
            for session_name in ("New York", "London", "Asia"):
                self.session_profiles[session_name]["threshold_offset"] = max(-0.8, min(3.0, fallback_offset))
                self.session_profiles[session_name]["cooldown_mult"] = max(0.5, min(3.0, fallback_mult))

        samples = payload.get("samples", [])
        if isinstance(samples, list):
            self.learning_trade_samples = samples[-500:]
        else:
            self.learning_trade_samples = []

        has_session_trades = any(self.session_profiles[name].get("trades") for name in ("New York", "London", "Asia"))
        if not has_session_trades and self.learning_trade_samples:
            for sample in self.learning_trade_samples:
                session_name = sample.get("entry_session")
                if session_name not in self.session_profiles:
                    entry_hour = sample.get("entry_hour_utc5")
                    if isinstance(entry_hour, (int, float)) and 0 <= int(entry_hour) <= 23:
                        session_name = self.get_session_name_for_clock(dt_time(int(entry_hour), 0))
                if session_name in self.session_profiles:
                    self.session_profiles[session_name]["trades"].append(sample)
            for session_name in ("New York", "London", "Asia"):
                self.session_profiles[session_name]["trades"] = self.session_profiles[session_name]["trades"][-300:]
        self.update_learning_status_text()

    def reset_learning_state(self):
        self.learning_trade_samples = []
        for session_name in ("New York", "London", "Asia"):
            self.session_profiles[session_name] = {"threshold_offset": 0.0, "cooldown_mult": 1.0, "tp_offset": 0.0, "sl_offset": 0.0, "trades": []}
        if os.path.exists(self.learning_state_path):
            try:
                os.remove(self.learning_state_path)
            except OSError:
                pass
        self.update_learning_status_text()
        self.set_status("Learning state reset", "ok")

    def get_effective_auto_settings(self, base_threshold: float, base_cooldown: float, session_name: str | None = None):
        if not self.learning_enabled_value.get():
            return base_threshold, base_cooldown
        if session_name is None:
            session_name = self.get_current_session_name()
        profile = self.session_profiles.get(session_name)
        if profile is None:
            return base_threshold, base_cooldown
        threshold_offset = float(profile.get("threshold_offset", 0.0))
        cooldown_mult = float(profile.get("cooldown_mult", 1.0))
        effective_threshold = max(0.05, base_threshold + threshold_offset)
        effective_cooldown = max(0.0, base_cooldown * cooldown_mult)
        return effective_threshold, effective_cooldown

    def get_effective_exit_settings(self, base_tp: float, base_sl: float, session_name: str | None = None):
        """Get adaptive TP/SL for a session based on learned offsets."""
        if not self.learning_enabled_value.get():
            return base_tp, base_sl
        if session_name is None:
            session_name = self.get_current_session_name()
        profile = self.session_profiles.get(session_name)
        if profile is None:
            return base_tp, base_sl
        tp_offset = float(profile.get("tp_offset", 0.0))
        sl_offset = float(profile.get("sl_offset", 0.0))
        # Adjust TP and SL by offsets, keeping minimum of 1.0
        effective_tp = max(1.0, base_tp + tp_offset)
        effective_sl = max(1.0, base_sl + sl_offset)
        return effective_tp, effective_sl

    def update_learning_from_closed_trade(self, exit_pnl: float, points_move: float, exit_reason: str):
        if self.auto_entry_meta is None:
            self.update_learning_status_text()
            return

        entry_session = str(self.auto_entry_meta.get("entry_session", "Off Session"))
        trade = {
            "ts": self.get_utc_minus5_timestamp(),
            "entry_hour_utc5": self.auto_entry_meta.get("entry_hour_utc5"),
            "entry_diff": self.auto_entry_meta.get("entry_diff"),
            "entry_side": self.auto_entry_meta.get("entry_side"),
            "entry_session": entry_session,
            "points_move": points_move,
            "pnl": exit_pnl,
            "is_win": bool(exit_pnl >= 0),
            "exit_reason": exit_reason,
        }
        self.learning_trade_samples.append(trade)
        self.learning_trade_samples = self.learning_trade_samples[-500:]

        if entry_session in self.session_profiles:
            profile = self.session_profiles[entry_session]
            trades = profile.get("trades", [])
            trades.append(trade)
            profile["trades"] = trades[-300:]

            if self.learning_enabled_value.get():
                recent = profile["trades"][-40:]
                if len(recent) >= 10:
                    wins = sum(1 for item in recent if item.get("is_win"))
                    win_rate = wins / len(recent)
                    avg_pnl = sum(float(item.get("pnl", 0.0)) for item in recent) / len(recent)

                    threshold_offset = float(profile.get("threshold_offset", 0.0))
                    cooldown_mult = float(profile.get("cooldown_mult", 1.0))
                    if win_rate < 0.45 or avg_pnl < 0:
                        threshold_offset += 0.05
                        cooldown_mult += 0.03
                    elif win_rate > 0.60 and avg_pnl > 0:
                        threshold_offset -= 0.03
                        cooldown_mult -= 0.02
                    else:
                        threshold_offset *= 0.995
                        cooldown_mult += (1.0 - cooldown_mult) * 0.01

                    profile["threshold_offset"] = max(-0.8, min(3.0, threshold_offset))
                    profile["cooldown_mult"] = max(0.5, min(3.0, cooldown_mult))

                    # Adaptive TP/SL learning
                    tp_offset = float(profile.get("tp_offset", 0.0))
                    sl_offset = float(profile.get("sl_offset", 0.0))
                    
                    tp_hits = sum(1 for item in recent if item.get("exit_reason") == "TP")
                    sl_hits = sum(1 for item in recent if item.get("exit_reason") == "SL")
                    tp_pnl = sum(float(item.get("pnl", 0.0)) for item in recent if item.get("exit_reason") == "TP") if tp_hits > 0 else 0.0
                    sl_pnl = sum(float(item.get("pnl", 0.0)) for item in recent if item.get("exit_reason") == "SL") if sl_hits > 0 else 0.0
                    
                    # If SL gets hit more than TP and losses pile up, widen SL (increase offset)
                    if sl_hits > tp_hits * 1.5 and sl_pnl < 0:
                        sl_offset += 0.1
                    # If SL rarely hit and TP working well, maintain/tighten
                    elif tp_hits > sl_hits and tp_pnl > 0:
                        sl_offset -= 0.05
                        tp_offset -= 0.03
                    # If TP rarely hit, relax TP target
                    elif sl_hits > 0 and tp_hits == 0:
                        tp_offset += 0.08
                    else:
                        # Gentle mean reversion
                        tp_offset *= 0.98
                        sl_offset *= 0.98

                    profile["tp_offset"] = max(-2.0, min(5.0, tp_offset))
                    profile["sl_offset"] = max(-2.0, min(5.0, sl_offset))

        self.save_learning_state()
        self.update_learning_status_text()

    def get_auto_sim_settings(self):
        try:
            threshold = abs(float(self.auto_sim_threshold_value.get().strip()))
        except ValueError:
            threshold = None

        try:
            cooldown = float(self.auto_sim_cooldown_value.get().strip())
            if cooldown < 0:
                raise ValueError
        except ValueError:
            cooldown = None
        return threshold, cooldown

    def get_utc_minus5_now(self):
        return datetime.now(timezone.utc).astimezone(UTC_MINUS_5)

    def get_utc_minus5_clock(self):
        now = self.get_utc_minus5_now()
        return dt_time(hour=now.hour, minute=now.minute, second=now.second)

    def get_utc_minus5_timestamp(self):
        return self.get_utc_minus5_now().strftime("%Y-%m-%d %H:%M:%S")

    def format_duration(self, total_seconds: int):
        total_seconds = max(0, int(total_seconds))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def refresh_trade_timing_display(self, now_epoch: float | None = None):
        if now_epoch is None:
            now_epoch = time.time()
        if self.auto_position_side != 0 and self.auto_entry_meta is not None:
            entry_timestamp = str(self.auto_entry_meta.get("entry_timestamp", "-"))
            entry_epoch = self.auto_entry_meta.get("entry_epoch")
            entry_topstep = self.auto_entry_meta.get("entry_topstep")
            self.entry_time_value.set(entry_timestamp)
            self.entry_number_value.set(format_number(entry_topstep) if entry_topstep is not None else "-")
            self.entry_side_value.set("BUY" if self.auto_position_side > 0 else "SELL")
            if isinstance(entry_epoch, (int, float)):
                elapsed = int(now_epoch - float(entry_epoch))
                self.time_in_trade_value.set(self.format_duration(elapsed))
                return
        self.entry_time_value.set("-")
        self.entry_number_value.set("-")
        self.entry_side_value.set("-")
        self.time_in_trade_value.set("-")

    def tick_utc_minus5_clock(self):
        now_text = self.get_utc_minus5_now().strftime("%Y-%m-%d %H:%M:%S")
        self.utc_minus5_time_value.set(now_text)
        self.current_session_value.set(self.get_current_session_name())
        self.refresh_trade_timing_display()
        self.refresh_feed_health_display()
        self.utc_clock_job = self.after(1000, self.tick_utc_minus5_clock)

    def start_utc_minus5_clock(self):
        if self.utc_clock_job is not None:
            self.after_cancel(self.utc_clock_job)
            self.utc_clock_job = None
        self.tick_utc_minus5_clock()

    def parse_time_input(self, value: str):
        match = TIME_INPUT_PATTERN.fullmatch(value or "")
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2))
        second = int(match.group(3) or 0)
        if hour > 23 or minute > 59 or second > 59:
            return None
        return dt_time(hour=hour, minute=minute, second=second)

    def get_trade_window_state(self):
        if not self.trade_window_enabled_value.get():
            return True, True, None, None

        start_value = self.trade_window_start_value.get().strip()
        end_value = self.trade_window_end_value.get().strip()
        start_clock = self.parse_time_input(start_value)
        end_clock = self.parse_time_input(end_value)
        if start_clock is None or end_clock is None:
            return False, False, None, None

        now_clock = self.get_utc_minus5_clock()
        if start_clock <= end_clock:
            is_open = start_clock <= now_clock <= end_clock
        else:
            # Overnight window, e.g. 22:00 -> 03:00.
            is_open = now_clock >= start_clock or now_clock <= end_clock
        return True, is_open, start_clock, end_clock

    def calculate_profit_loss(self, diff_points: float):
        try:
            contracts = float(self.contract_size_value.get().strip())
            dollars_per_point = float(self.point_value_value.get().strip())
            if contracts < 0 or dollars_per_point < 0:
                return None
            return diff_points * contracts * dollars_per_point
        except ValueError:
            return None

    def get_open_position_points_move(self, current_topstep: float):
        if self.auto_position_side == 0 or self.auto_entry_meta is None:
            return 0.0
        entry_topstep = self.auto_entry_meta.get("entry_topstep")
        if not isinstance(entry_topstep, (int, float)):
            return 0.0
        return current_topstep - float(entry_topstep)

    def refresh_total_profit_loss(self, current_topstep: float | None = None):
        open_pnl = 0.0
        if current_topstep is not None and self.auto_position_side != 0 and self.auto_entry_meta is not None:
            points_move = self.get_open_position_points_move(current_topstep)
            pnl_value = self.calculate_profit_loss(points_move)
            if pnl_value is not None:
                open_pnl = pnl_value

        total = self.realized_total_profit_loss + open_pnl
        self.total_profit_loss_value.set(format_currency(total))

    def maybe_trigger_auto_sim_trade(self, diff: float, topstep_num: float, tradovate_num: float):
        threshold, cooldown = self.get_auto_sim_settings()
        try:
            stop_loss_points = abs(float(self.stop_loss_points_value.get().strip()))
            take_profit_points = abs(float(self.take_profit_points_value.get().strip()))
        except ValueError:
            stop_loss_points = None
            take_profit_points = None

        if threshold is None or cooldown is None or stop_loss_points is None or take_profit_points is None:
            self.auto_sim_status_value.set("Config error")
            return
        current_session = self.get_current_session_name()
        threshold, cooldown = self.get_effective_auto_settings(threshold, cooldown, current_session)
        take_profit_points, stop_loss_points = self.get_effective_exit_settings(take_profit_points, stop_loss_points, current_session)

        now = time.time()
        if self.auto_position_side != 0 and self.auto_entry_diff is not None:
            points_move = self.get_open_position_points_move(topstep_num)
            if take_profit_points > 0 and points_move >= take_profit_points:
                close_action = "SELL" if self.auto_position_side > 0 else "BUY"
                realized_points = take_profit_points
                executed = self.execute_paper_trade(
                    close_action,
                    trigger_source="AUTO_TP",
                    diff=diff,
                    note=f"topstep_move={points_move:.2f} | fill_points={realized_points:.2f}",
                    set_main_status=False,
                )
                if executed:
                    exit_pnl = self.calculate_profit_loss(realized_points)
                    if exit_pnl is not None:
                        self.realized_total_profit_loss += exit_pnl
                        self.record_difference(
                            topstep_num,
                            tradovate_num,
                            diff,
                            trade_result="WIN" if exit_pnl >= 0 else "LOSS",
                            trade_p_l=exit_pnl,
                        )
                        self.update_learning_from_closed_trade(exit_pnl, realized_points, "TP")
                        self.last_diff_logged_key = (round(topstep_num, 6), round(tradovate_num, 6), round(diff, 6))
                    self.last_auto_trade_at = now
                    self.auto_sim_status_value.set(f"TP hit +{realized_points:.2f} pts")
                    self.auto_position_side = 0
                    self.auto_entry_diff = None
                    self.auto_entry_meta = None
                    self.sl_rearm_required = False
                    self.refresh_trade_timing_display(now)
                    self.last_auto_signal = 0
                return
            if stop_loss_points > 0 and points_move <= -(stop_loss_points - 1e-9):
                close_action = "SELL" if self.auto_position_side > 0 else "BUY"
                realized_points = -stop_loss_points
                executed = self.execute_paper_trade(
                    close_action,
                    trigger_source="AUTO_SL",
                    diff=diff,
                    note=f"topstep_move={points_move:.2f} | fill_points={realized_points:.2f}",
                    set_main_status=False,
                )
                if executed:
                    exit_pnl = self.calculate_profit_loss(realized_points)
                    if exit_pnl is not None:
                        self.realized_total_profit_loss += exit_pnl
                        self.record_difference(
                            topstep_num,
                            tradovate_num,
                            diff,
                            trade_result="WIN" if exit_pnl >= 0 else "LOSS",
                            trade_p_l=exit_pnl,
                        )
                        self.update_learning_from_closed_trade(exit_pnl, realized_points, "SL")
                        self.last_diff_logged_key = (round(topstep_num, 6), round(tradovate_num, 6), round(diff, 6))
                    self.last_auto_trade_at = now
                    self.auto_sim_status_value.set(f"SL hit {realized_points:.2f} pts")
                    self.auto_position_side = 0
                    self.auto_entry_diff = None
                    self.auto_entry_meta = None
                    self.sl_rearm_required = True
                    self.refresh_trade_timing_display(now)
                    self.last_auto_signal = 0
                return
            side_text = "BUY" if self.auto_position_side > 0 else "SELL"
            self.auto_sim_status_value.set(f"In {side_text} | topstep move {points_move:.2f} pts")
            self.refresh_trade_timing_display(now)
            return

        if self.sl_rearm_required:
            if abs(diff) < threshold:
                self.sl_rearm_required = False
            else:
                self.last_auto_signal = 0
                self.auto_sim_status_value.set("SL lockout: waiting for neutral diff")
                return

        window_valid, window_open, start_clock, end_clock = self.get_trade_window_state()
        if not window_valid:
            self.auto_sim_status_value.set("Time window error")
            return

        if not window_open:
            self.last_auto_signal = 0
            if start_clock is not None and end_clock is not None:
                self.auto_sim_status_value.set(
                    f"Outside window {start_clock.strftime('%H:%M')}-{end_clock.strftime('%H:%M')}"
                )
            else:
                self.auto_sim_status_value.set("Outside trade window")
            return

        signal = 0
        if diff <= -threshold:
            # Topstep is lower than Tradovate by threshold: BUY bias.
            signal = 1
        elif diff >= threshold:
            # Topstep is higher than Tradovate by threshold: SELL bias.
            signal = -1
        else:
            self.last_auto_signal = 0
            self.auto_sim_status_value.set("Waiting for threshold")
            return

        elapsed = now - self.last_auto_trade_at
        if elapsed < cooldown:
            self.auto_sim_status_value.set(f"Cooldown {cooldown - elapsed:.1f}s")
            return

        if signal == self.last_auto_signal:
            self.auto_sim_status_value.set("Signal unchanged")
            return

        action = "BUY" if signal > 0 else "SELL"
        executed = self.execute_paper_trade(action, trigger_source="AUTO_ENTRY", diff=diff, set_main_status=False)
        if executed:
            self.last_auto_trade_at = now
            self.last_auto_signal = signal
            self.auto_position_side = signal
            self.auto_entry_diff = diff
            self.record_difference(topstep_num, tradovate_num, diff, trade_result="ENTRY")
            self.last_diff_logged_key = (round(topstep_num, 6), round(tradovate_num, 6), round(diff, 6))
            entry_now = self.get_utc_minus5_now()
            self.auto_entry_meta = {
                "entry_diff": diff,
                "entry_topstep": topstep_num,
                "entry_tradovate": tradovate_num,
                "entry_side": action,
                "entry_hour_utc5": entry_now.hour,
                "entry_session": current_session,
                "effective_threshold": threshold,
                "effective_cooldown": cooldown,
                "entry_timestamp": entry_now.strftime("%Y-%m-%d %H:%M:%S"),
                "entry_epoch": now,
            }
            self.refresh_trade_timing_display(now)
            self.auto_sim_status_value.set(f"Entered {action} at diff {diff:.2f}")

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
            import json as json_lib
            payload = json_lib.dumps({"slot": "test", "text": "healthcheck", "timestamp": ""}).encode('utf-8')
            req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            response = urllib.request.urlopen(req, timeout=2)
            if response.status == 200:
                self.set_status("✓ Extension connection OK", "ok")
                self.extension_status_value.set("✓ Connection test passed!")
                print("[✓] Extension connection test successful")
            else:
                self.set_status("Server responded but with error", "warn")
        except Exception as e:
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
                    action_buttons_active = bool(app.running and live_enabled)
                    command = app.pop_live_trade_command() if action_buttons_active else None
                    response = json.dumps(
                        {
                            "enabled": live_enabled,
                            "monitoring": bool(app.running),
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
                    except Exception:
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
                except Exception as e:
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


def main():
    app = NumberDiffApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
