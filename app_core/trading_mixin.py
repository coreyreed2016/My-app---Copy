from __future__ import annotations

import json
import os
import time
from datetime import datetime, time as dt_time, timezone

from app_core.common import TIME_INPUT_PATTERN, UTC_MINUS_5, format_currency, format_number


class TradingMixin:
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
            thr_offset = self._safe_float(profile.get("threshold_offset", 0.0), 0.0)
            cooldown_mult = self._safe_float(profile.get("cooldown_mult", 1.0), 1.0)
            tp_offset = self._safe_float(profile.get("tp_offset", 0.0), 0.0)
            sl_offset = self._safe_float(profile.get("sl_offset", 0.0), 0.0)
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
        thr_offset = self._safe_float(profile.get("threshold_offset", 0.0), 0.0)
        cooldown_mult = self._safe_float(profile.get("cooldown_mult", 1.0), 1.0)
        tp_offset = self._safe_float(profile.get("tp_offset", 0.0), 0.0)
        sl_offset = self._safe_float(profile.get("sl_offset", 0.0), 0.0)
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
                "threshold_offset": self._safe_float(profile.get("threshold_offset", 0.0), 0.0),
                "cooldown_mult": self._safe_float(profile.get("cooldown_mult", 1.0), 1.0),
                "tp_offset": self._safe_float(profile.get("tp_offset", 0.0), 0.0),
                "sl_offset": self._safe_float(profile.get("sl_offset", 0.0), 0.0),
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
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            self.update_learning_status_text()
            return

        self.learning_enabled_value.set(bool(payload.get("enabled", True)))
        for session_name in ("New York", "London", "Asia"):
            self.session_profiles[session_name] = {"threshold_offset": 0.0, "cooldown_mult": 1.0, "tp_offset": 0.0, "sl_offset": 0.0, "trades": []}

        loaded_profiles = payload.get("session_profiles", {})
        if isinstance(loaded_profiles, dict) and loaded_profiles:
            for session_name in ("New York", "London", "Asia"):
                profile = loaded_profiles.get(session_name, {})
                threshold_offset = self._safe_float(profile.get("threshold_offset", 0.0), 0.0)
                cooldown_mult = self._safe_float(profile.get("cooldown_mult", 1.0), 1.0)
                tp_offset = self._safe_float(profile.get("tp_offset", 0.0), 0.0)
                sl_offset = self._safe_float(profile.get("sl_offset", 0.0), 0.0)
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
        threshold_offset = self._safe_float(profile.get("threshold_offset", 0.0), 0.0)
        cooldown_mult = self._safe_float(profile.get("cooldown_mult", 1.0), 1.0)
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
        tp_offset = self._safe_float(profile.get("tp_offset", 0.0), 0.0)
        sl_offset = self._safe_float(profile.get("sl_offset", 0.0), 0.0)
        # In learning mode, never let adaptive exits tighten below 10 points.
        effective_tp = max(10.0, base_tp + tp_offset)
        effective_sl = max(10.0, base_sl + sl_offset)
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

                    threshold_offset = self._safe_float(profile.get("threshold_offset", 0.0), 0.0)
                    cooldown_mult = self._safe_float(profile.get("cooldown_mult", 1.0), 1.0)
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
                    tp_offset = self._safe_float(profile.get("tp_offset", 0.0), 0.0)
                    sl_offset = self._safe_float(profile.get("sl_offset", 0.0), 0.0)
                    
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
            # Convert raw topstep move into direction-aware move so BUY/SELL exits are symmetric.
            directional_move = points_move * float(self.auto_position_side)

            if take_profit_points > 0 and directional_move >= take_profit_points:
                close_action = "SELL" if self.auto_position_side > 0 else "BUY"
                realized_points = take_profit_points
                executed = self.execute_paper_trade(
                    close_action,
                    trigger_source="AUTO_TP",
                    diff=diff,
                    note=f"topstep_move={points_move:.2f} | dir_move={directional_move:.2f} | fill_points={realized_points:.2f}",
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
            if stop_loss_points > 0 and directional_move <= -(stop_loss_points - 1e-9):
                close_action = "SELL" if self.auto_position_side > 0 else "BUY"
                realized_points = -stop_loss_points
                executed = self.execute_paper_trade(
                    close_action,
                    trigger_source="AUTO_SL",
                    diff=diff,
                    note=f"topstep_move={points_move:.2f} | dir_move={directional_move:.2f} | fill_points={realized_points:.2f}",
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
            self.auto_sim_status_value.set(f"In {side_text} | directional move {directional_move:.2f} pts")
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
