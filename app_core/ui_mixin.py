from __future__ import annotations

import tkinter as tk
from tkinter import ttk

try:
    from tkcalendar import DateEntry
except ImportError:
    DateEntry = None


class UIMixin:
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

        ttk.Label(metrics_card, text="Ses. Trades:", style="Card.TLabel").grid(row=7, column=0, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.session_entries_value, foreground="#ffa500").grid(row=7, column=1, sticky="w", padx=8)
        ttk.Label(metrics_card, text="Ses. P/L:", style="Card.TLabel").grid(row=7, column=2, sticky="w", padx=10, pady=3)
        ttk.Label(metrics_card, textvariable=self.session_pnl_value, foreground="#ffa500").grid(row=7, column=3, sticky="w", padx=8)

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
        session_frame.columnconfigure(0, weight=1)
        session_frame.rowconfigure(0, weight=1)
        
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
            self.session_stats_tree.column(col, width=90, anchor="e" if col != "session" else "w")
        
        self.session_stats_tree.grid(row=0, column=0, sticky="nsew")
        self.fit_treeview_columns(
            self.session_stats_tree,
            session_columns,
            {"session": 1.35, "trades": 1.0, "wins": 1.0, "losses": 1.0, "win_rate": 1.1, "thr_offset": 1.1, "cooldown_mult": 1.2, "tp_offset": 1.05, "sl_offset": 1.05},
            {"session": 90, "trades": 64, "wins": 58, "losses": 62, "win_rate": 72, "thr_offset": 74, "cooldown_mult": 82, "tp_offset": 70, "sl_offset": 70},
        )
        
        # Trade history
        history_card = self.create_card(scrollable, "Trade History")
        history_frame = ttk.Frame(history_card)
        history_frame.pack(fill="both", expand=True, padx=10, pady=10)
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(1, weight=0)
        history_frame.rowconfigure(2, weight=1)
        history_frame.rowconfigure(3, weight=0)
        
        toolbar = ttk.Frame(history_frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ttk.Button(toolbar, text="Clear History", command=self.clear_difference_history).pack(side="left")
        ttk.Label(toolbar, text="Period:").pack(side="left", padx=(12, 4))
        period_filter = ttk.Combobox(
            toolbar,
            textvariable=self.analytics_timeframe_value,
            values=("All", "Today", "Yesterday", "This Week", "Last 7 Days", "This Month", "Last 30 Days"),
            state="readonly",
            width=12,
        )
        period_filter.pack(side="left")
        ttk.Label(toolbar, text="Session:").pack(side="left", padx=(12, 4))
        session_filter = ttk.Combobox(
            toolbar,
            textvariable=self.analytics_session_value,
            values=("All", "New York", "London", "Asia", "Off Session"),
            state="readonly",
            width=11,
        )
        session_filter.pack(side="left")
        ttk.Label(toolbar, text="Start:").pack(side="left", padx=(12, 4))
        if DateEntry is not None:
            start_entry = DateEntry(toolbar, textvariable=self.history_range_start_value, width=12, date_pattern="yyyy-mm-dd")
        else:
            start_entry = ttk.Entry(toolbar, textvariable=self.history_range_start_value, width=12)
        start_entry.pack(side="left")
        ttk.Label(toolbar, text="End:").pack(side="left", padx=(8, 4))
        if DateEntry is not None:
            end_entry = DateEntry(toolbar, textvariable=self.history_range_end_value, width=12, date_pattern="yyyy-mm-dd")
        else:
            end_entry = ttk.Entry(toolbar, textvariable=self.history_range_end_value, width=12)
        end_entry.pack(side="left")
        self.history_start_picker = start_entry
        self.history_end_picker = end_entry
        ttk.Label(toolbar, text="Result:").pack(side="left", padx=(12, 4))
        result_filter = ttk.Combobox(toolbar, textvariable=self.history_filter_value, values=("All", "Closed", "Wins", "Losses", "Entries", "Unlabeled"), state="readonly", width=10)
        result_filter.pack(side="left")
        ttk.Label(toolbar, text="Rows:").pack(side="left", padx=(12, 4))
        row_limit = ttk.Combobox(toolbar, textvariable=self.history_limit_value, values=("50", "100", "250", "500", "1000", "All"), state="readonly", width=8)
        row_limit.pack(side="left")
        ttk.Button(toolbar, text="Apply", command=self.apply_history_filters).pack(side="left", padx=(12, 0))
        ttk.Button(toolbar, text="Clear", command=self.clear_history_filters).pack(side="left", padx=(6, 0))
        ttk.Label(toolbar, text="Dates use UTC-5").pack(side="left", padx=(10, 0))

        for widget in (start_entry, end_entry):
            widget.bind("<Return>", self.on_history_filter_changed)
            widget.bind("<FocusOut>", self.on_history_filter_changed)

        summary_label = ttk.Label(history_frame, textvariable=self.history_active_filters_value, foreground="#9fd3ff")
        summary_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6), padx=(2, 0))
        
        columns = ("timestamp", "session", "topstep", "tradovate", "difference", "result", "p_l")
        self.history_tree = ttk.Treeview(history_frame, columns=columns, show="headings", height=8)
        self.history_tree.heading("timestamp", text="Timestamp")
        self.history_tree.heading("session", text="Session")
        self.history_tree.heading("topstep", text="Topstep")
        self.history_tree.heading("tradovate", text="Tradovate")
        self.history_tree.heading("difference", text="Difference")
        self.history_tree.heading("result", text="Result")
        self.history_tree.heading("p_l", text="P/L")
        
        self.history_tree.column("timestamp", width=170, anchor="center")
        self.history_tree.column("session", width=95, anchor="center")
        self.history_tree.column("topstep", width=120, anchor="e")
        self.history_tree.column("tradovate", width=120, anchor="e")
        self.history_tree.column("difference", width=120, anchor="e")
        self.history_tree.column("result", width=90, anchor="center")
        self.history_tree.column("p_l", width=100, anchor="e")
        for col in columns:
            self.history_tree.column(col)
        
        self.history_tree.tag_configure("trade_win", foreground="#00d970", background="#0a3f1f")
        self.history_tree.tag_configure("trade_loss", foreground="#e94560", background="#3f0a0a")
        
        self.history_tree.grid(row=2, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        self.fit_treeview_columns(
            self.history_tree,
            columns,
            {"timestamp": 1.65, "session": 0.95, "topstep": 1.2, "tradovate": 1.2, "difference": 1.2, "result": 0.9, "p_l": 1.0},
            {"timestamp": 130, "session": 82, "topstep": 100, "tradovate": 100, "difference": 95, "result": 74, "p_l": 82},
        )

        period_filter.bind("<<ComboboxSelected>>", self.on_history_filter_changed)
        session_filter.bind("<<ComboboxSelected>>", self.on_history_filter_changed)
        result_filter.bind("<<ComboboxSelected>>", self.on_history_filter_changed)
        row_limit.bind("<<ComboboxSelected>>", self.on_history_filter_changed)
        if DateEntry is not None:
            start_entry.bind("<<DateEntrySelected>>", self.on_history_filter_changed)
            end_entry.bind("<<DateEntrySelected>>", self.on_history_filter_changed)
        
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
        def is_treeview_widget(widget):
            current = widget
            while current is not None:
                try:
                    if current.winfo_class() == "Treeview":
                        return True
                    parent_name = current.winfo_parent()
                    if not parent_name:
                        break
                    current = current.nametowidget(parent_name)
                except Exception:
                    break
            return False

        def on_mousewheel(event):
            # Let table widgets handle their own wheel behavior.
            if is_treeview_widget(getattr(event, "widget", None)):
                return
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

    def bind_treeview_horizontal_scroll(self, treeview):
        """Enable Shift+MouseWheel horizontal scrolling for wide tree views."""

        def on_shift_mousewheel(event):
            if getattr(event, "delta", 0):
                treeview.xview_scroll(int(-event.delta / 120), "units")
                return "break"
            if getattr(event, "num", None) == 4:
                treeview.xview_scroll(-1, "units")
                return "break"
            if getattr(event, "num", None) == 5:
                treeview.xview_scroll(1, "units")
                return "break"
            return None

        treeview.bind("<Shift-MouseWheel>", on_shift_mousewheel)
        treeview.bind("<Shift-Button-4>", on_shift_mousewheel)
        treeview.bind("<Shift-Button-5>", on_shift_mousewheel)

    def fit_treeview_columns(self, treeview, columns, weights, min_widths):
        """Resize treeview columns so all columns fit inside the visible widget width."""

        def apply_fit(_event=None):
            total_width = max(1, treeview.winfo_width() - 4)
            weight_sum = sum(float(weights.get(col, 1.0)) for col in columns)
            if weight_sum <= 0:
                return

            computed = {}
            used = 0
            for col in columns:
                weight = float(weights.get(col, 1.0))
                min_w = int(min_widths.get(col, 40))
                width = max(min_w, int(total_width * (weight / weight_sum)))
                computed[col] = width
                used += width

            if used > total_width:
                overflow = used - total_width
                ordered = sorted(columns, key=lambda name: float(weights.get(name, 1.0)), reverse=True)
                for col in ordered:
                    if overflow <= 0:
                        break
                    min_w = int(min_widths.get(col, 40))
                    can_take = max(0, computed[col] - min_w)
                    take = min(can_take, overflow)
                    computed[col] -= take
                    overflow -= take

            for col in columns:
                anchor = treeview.column(col, option="anchor") or "w"
                treeview.column(col, width=computed[col], minwidth=int(min_widths.get(col, 40)), anchor=anchor, stretch=True)

        treeview.bind("<Configure>", apply_fit)
        treeview.after(0, apply_fit)
