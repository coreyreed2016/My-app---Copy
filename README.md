# Number Difference Monitor

A lightweight Windows desktop app that:

- Reads Topstep and Tradovate values from a Chrome extension element picker
- Continuously compares them
- Shows if there is a difference in real time

## 1) Install Python dependencies

From this project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) Run

```powershell
python app.py
```

## How to use

### Chrome extension mode (element picker)

1. In app, keep extension port as `8765` (or set your own port).
2. In Chrome, open `chrome://extensions`, enable Developer mode, then **Load unpacked**:
   - `chrome_extension/element_dropper`
3. Open the extension popup:
   - Set endpoint to `http://127.0.0.1:8765/extension-feed`
   - Click **Pick** for Topstep, then click the Topstep value on the page
   - Click **Pick** for Tradovate, then click the Tradovate value on the page
4. Click **Start** in the desktop app to begin monitoring.

### Output

- Topstep number
- Tradovate number
- Difference (`Topstep - Tradovate`)
- Profit/Loss (based on `Difference * Contracts * $ per Point`)
- Status (`Numbers match` or `Difference detected`)
- Feed health for Topstep and Tradovate (`Live`, `Stale`, `Idle/Waiting`) with last update time
- Running mismatch count
- History table with timestamp + values whenever numbers differ

### Settings persistence

- App settings are auto-saved to `app_settings.json`
- This includes interval, contracts, dollar value, extension port, auto-sim thresholds, SL/TP, and trade window settings
- Settings reload automatically the next time the app starts

### Contract and P/L settings

- `Contracts` default: `1`
- `$ per Point` default: `20`
- With default settings, `1` point difference = `$20` P/L.

### Sim trading mode

- Sim trading is now **in-app paper trading only** for testing.
- The app does not send keys or place orders in Topstep/Tradovate.
- Tradovate remains the reference feed; Topstep remains the compared feed.

### Auto trade on difference

- Auto trading is active whenever monitoring is running.
- Set:
  - `Min Diff` (minimum absolute difference required to trigger)
  - `Cooldown (s)` (minimum time between auto-triggered trades)
- Set exits in points:
  - `Stop Loss (pts)`
  - `Take Profit (pts)`
- Optional time filter:
  - Enable `Use Trade Time Window`
  - Set `Start (HH:MM)` and `End (HH:MM)`
  - Use the live `Current UTC-5` clock shown in the app to line up the window
  - New entries only happen inside that window (open positions can still exit on SL/TP)
- Trigger logic:
  - Entry: `Topstep - Tradovate <= -Min Diff` -> auto `BUY`
  - Entry: `Topstep - Tradovate >= Min Diff` -> auto `SELL`
  - Exit: SL/TP are checked from the Topstep entry number:
    - TP when `Topstep >= Entry Topstep + Take Profit`
    - SL when `Topstep <= Entry Topstep - Stop Loss`
- Auto sim executes paper entries/exits inside the app only.
- Optional `Adaptive Learning Mode`:
  - Learns from closed trades (TP/SL outcomes) by session:
    - New York: `08:30-15:00` CT
    - London: `02:00-06:00` CT
    - Asia: `17:00-02:00` CT
  - Auto-tunes effective threshold/cooldown per session with safety limits
  - Persists state in `learning_state.json`
  - Use `Reset Learning` to clear learned behavior
- Sim panel also shows:
  - `Entered At (UTC-5)` for current open position
  - `Entry Number` (Topstep entry value)
  - `Time In Trade` (live duration while position is open)
- `Total Profit/Loss` tracks cumulative realized auto-sim P/L plus any open position P/L.

## Difference record file

- Trade events are saved to `difference_log.csv` in the app folder.
- Columns: `timestamp`, `topstep`, `tradovate`, `difference`, `trade_result`, `trade_p_l`
- UI history now shows trade events (entries/exits), not every raw difference tick.
- Rows are color coded when a trade closes:
  - Green = win
  - Red = loss
- Data views are now in the **Data** tab (session performance + difference history).

### Analytics upgrades

- Analytics now includes a performance summary with:
  - Total events
  - Closed trades
  - Win rate
  - Realized P/L
  - Average win
  - Average loss
- Trade history can now be filtered by:
  - `All`
  - `Closed`
  - `Wins`
  - `Losses`
  - `Entries`
  - `Unlabeled`
- History row count can be limited to recent records for faster review

## Order action record file

- Every auto-sim paper trade action is saved to `order_action_log.csv`.
- Columns: `timestamp`, `action`, `trigger`, `details`, `mode`

## Chrome extension files

- Extension folder: `chrome_extension/element_dropper`
- Main files:
  - `manifest.json`
  - `background.js`
  - `picker.js`
  - `popup.html`, `popup.js`, `popup.css`

### Chrome extension popup improvements

- Each slot now shows:
  - Saved selector
  - Preview text captured at pick time
  - Latest live value
  - Last updated time
  - Source page title/URL
- Each slot has a `Test` button to poll just that element immediately
- Popup connection status now reflects whether the desktop app endpoint is reachable and when the last successful push occurred

## Troubleshooting

- If values stay `-`, re-run **Pick** for Topstep/Tradovate in the extension popup.
