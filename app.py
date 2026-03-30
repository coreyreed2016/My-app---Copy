from __future__ import annotations

import os
import threading
import tkinter as tk
from collections import deque

from app_core.common import format_currency
from app_core.data_mixin import DataMixin
from app_core.runtime_mixin import RuntimeMixin
from app_core.trading_mixin import TradingMixin
from app_core.ui_mixin import UIMixin


class NumberDiffApp(tk.Tk, UIMixin, DataMixin, TradingMixin, RuntimeMixin):
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
        self.analytics_timeframe_value = tk.StringVar(value="All")
        self.analytics_session_value = tk.StringVar(value="All")
        self.history_range_start_value = tk.StringVar(value="")
        self.history_range_end_value = tk.StringVar(value="")
        self.history_filter_value = tk.StringVar(value="All")
        self.history_limit_value = tk.StringVar(value="250")
        self.history_active_filters_value = tk.StringVar(value="Active filters: None (default rows: 250)")
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
        self.session_entries_value = tk.StringVar(value="0 / 30")
        self.session_pnl_value = tk.StringVar(value="$0.00 / $800.00")

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
        self.session_trade_limit = 30
        self.session_profit_goal = 800.0
        self.session_guardrails = {}
        self.active_session_guardrail_key = ""
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

    @staticmethod
    def _safe_float(value, default: float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


def main():
    app = NumberDiffApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
