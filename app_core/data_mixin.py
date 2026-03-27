from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, time as dt_time, timedelta, timezone

from app_core.common import FEED_STALE_AFTER_SECONDS, UTC_MINUS_5, format_currency, format_number, parse_number_token


class DataMixin:
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
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
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
        try:
            with open(self.app_settings_path, "w", encoding="utf-8") as file:
                json.dump(self.get_app_settings_payload(), file, indent=2)
        except OSError:
            # Non-fatal: settings autosave should never crash monitoring/UI flow.
            return

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
                        "timestamp_dt": self.parse_row_timestamp(row.get("timestamp", "")),
                        "session": "-",
                        "topstep": row.get("topstep", ""),
                        "tradovate": row.get("tradovate", ""),
                        "difference": diff_text,
                        "result": result_text,
                        "p_l_num": p_l_num,
                        "p_l_text": format_currency(p_l_num) if p_l_num is not None else "-",
                    }
                )
        for row in rows:
            ts = row.get("timestamp_dt")
            if isinstance(ts, datetime):
                row["session"] = self.get_session_name_for_clock(ts.timetz().replace(tzinfo=None))
            else:
                row["session"] = "-"
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

    def parse_row_timestamp(self, timestamp_text: str):
        text = str(timestamp_text or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            return parsed.replace(tzinfo=UTC_MINUS_5)
        except ValueError:
            return None

    def filter_rows_by_timeframe(self, rows):
        period = self.analytics_timeframe_value.get().strip().lower()
        if period == "all":
            return rows

        now_dt = self.get_utc_minus5_now()
        today_date = now_dt.date()
        start_dt = None
        end_dt = now_dt

        if period == "today":
            start_dt = datetime.combine(today_date, dt_time.min, tzinfo=UTC_MINUS_5)
        elif period == "yesterday":
            start_day = today_date - timedelta(days=1)
            start_dt = datetime.combine(start_day, dt_time.min, tzinfo=UTC_MINUS_5)
            end_dt = datetime.combine(start_day, dt_time.max, tzinfo=UTC_MINUS_5)
        elif period == "this week":
            start_day = today_date - timedelta(days=today_date.weekday())
            start_dt = datetime.combine(start_day, dt_time.min, tzinfo=UTC_MINUS_5)
        elif period == "last 7 days":
            start_dt = now_dt - timedelta(days=7)
        elif period == "this month":
            start_day = today_date.replace(day=1)
            start_dt = datetime.combine(start_day, dt_time.min, tzinfo=UTC_MINUS_5)
        elif period == "last 30 days":
            start_dt = now_dt - timedelta(days=30)
        else:
            return rows

        filtered = []
        for row in rows:
            ts = row.get("timestamp_dt")
            if ts is None:
                ts = self.parse_row_timestamp(row.get("timestamp", ""))
            if ts is None:
                continue
            if start_dt is not None and ts < start_dt:
                continue
            if end_dt is not None and ts > end_dt:
                continue
            filtered.append(row)
        return filtered

    def parse_history_date(self, value: str):
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def filter_rows_by_date_range(self, rows):
        start_date = self.parse_history_date(self.history_range_start_value.get())
        end_date = self.parse_history_date(self.history_range_end_value.get())
        if start_date is None and end_date is None:
            return rows

        filtered = []
        for row in rows:
            ts = row.get("timestamp_dt")
            if ts is None:
                ts = self.parse_row_timestamp(row.get("timestamp", ""))
            if ts is None:
                continue
            row_date = ts.date()
            if start_date is not None and row_date < start_date:
                continue
            if end_date is not None and row_date > end_date:
                continue
            filtered.append(row)
        return filtered

    def filter_rows_by_session(self, rows):
        selected = self.analytics_session_value.get().strip().lower()
        if selected in ("", "all"):
            return rows
        return [row for row in rows if str(row.get("session", "")).strip().lower() == selected]

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
        timeframe_rows = self.filter_rows_by_timeframe(rows)
        range_rows = self.filter_rows_by_date_range(timeframe_rows)
        session_rows = self.filter_rows_by_session(range_rows)
        self.refresh_analytics_summary(session_rows)
        self.history_tree.delete(*self.history_tree.get_children())
        filtered_rows = self.filter_history_rows(session_rows)
        self.difference_count = len(rows)
        for row in filtered_rows:
            values = (
                row["timestamp"],
                row.get("session", "-"),
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
