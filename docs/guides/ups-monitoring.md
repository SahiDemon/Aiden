# 🔋 UPS Power Monitoring - Aiden Integration

## Overview

Aiden now includes **intelligent UPS power monitoring** that protects your system during power outages with cool voice alerts and automatic shutdown capabilities.

## Features

✅ **Real-time Power Mode Detection** - Instantly detects AC vs Battery mode  
✅ **Battery Level Monitoring** - Tracks battery percentage with smart thresholds  
✅ **Voice Alerts** - Cool, professional warnings from Aiden  
✅ **Smart Shutdown Coordination** - Asks for confirmation before shutdown  
✅ **Automatic Protection** - Force shutdown at critical battery levels  
✅ **Configurable Thresholds** - Customize when alerts trigger  

## How It Works

### Time-Based Alert System ⏱️

Aiden uses **time-based alerts** instead of unreliable battery percentage readings:

### 1. **AC Power Loss** 🔌➡️🔋
When power goes off, Aiden asks immediately:

> **Aiden:** "Sir, we've lost power. We're running on UPS battery. Should I shut down the system now to be safe, or do you need time to save your work?"

**Your Response Options:**
- **"Yes" / "Shutdown"** → Graceful shutdown begins immediately
- **"No" / "I need time"** → Continues monitoring, will check in at 2 minutes

### Power Restore Recovery ⚡
When mains power returns, Aiden immediately stands down:

> **Aiden:** "Power is back online, Sir. Abort sequence confirmed."

If the Windows 30-second shutdown countdown had already started, Aiden aborts it with `shutdown /a`.

### 2. **First Check-in** (2 minutes) ⚠️
After 2 minutes on battery:

> **Aiden:** "Sir, you've had 2 minutes on battery. I need to know - should I shut down now?"

**Your Response Options:**
- **"Yes" / "Shutdown"** → Graceful shutdown begins
- **"No" / "Cancel"** → Continues monitoring until 4-minute deadline

### 3. **Force Shutdown** (4 minutes) 💥
After 4 minutes total with no response:

> **Aiden:** "Sir, it's been 4 minutes on battery with no response. Forcing shutdown to protect your data. Goodbye, Sir."

### Emergency Protection 🛡️

If battery voltage drops below 22V (critical for 24V systems), immediate emergency shutdown regardless of time.

## Configuration

Edit your `.env` file to customize UPS monitoring:

```env
# ===== UPS Power Monitoring =====
UPS_ENABLED=true                                    # Enable/disable UPS monitoring
UPS_INFO_LOG_PATH=C:\ViewPower\log\info.log        # Path to ViewPower log
UPS_POLLING_INTERVAL=1.0                            # Seconds between log checks
```

### Alert Timings (Hard-coded for reliability)

- **Immediate** - Ask right when power is lost
- **2 minutes** - First check-in asking about shutdown
- **4 minutes** - Force shutdown if no response
- **22V battery** - Emergency shutdown (critical voltage)

### Why Time-Based?

Battery percentage calculations are unreliable:
- Voltage fluctuates with load
- Capacity varies with temperature
- Age affects discharge curves
- UPS reports can be inaccurate

**Time gives you predictable, consistent alerts** regardless of battery quirks.

## Voice Commands

When UPS asks about shutdown, you can respond naturally:

**Confirm Shutdown:**
- "Yes"
- "Shutdown"
- "Proceed"
- "Do it"

**Cancel Shutdown:**
- "No"
- "Cancel"
- "Abort"
- "Cancel shutdown"

**Check Status:**
- "What's the UPS status?"
- "Battery level?"
- "Show UPS status"

## Requirements

1. **ViewPower Software** - Must be installed and logging to:
   - Default: `C:\ViewPower\log\info.log`
   - Custom path can be configured via `UPS_INFO_LOG_PATH`

2. **Compatible UPS** - Any UPS that works with ViewPower
   - Tested with 24V lead-acid battery systems
   - Should work with other ViewPower-compatible UPS models

## Testing

### Simulate Power Loss (SAFE METHOD)

**DO NOT unplug your UPS!** Instead, test with the monitor script:

```powershell
# Monitor UPS status in real-time
python scripts/diagnostics/monitor_viewpower_logs.py
```

This shows:
- Current power mode (AC ⚡ or Battery 🔋)
- Battery voltage and percentage
- Load percentage
- Input/output voltage

### Test Without ViewPower

If you don't have ViewPower installed, UPS monitoring will automatically disable itself with a warning in the logs:

```
ViewPower log not found: C:\ViewPower\log\info.log
UPS monitoring disabled - ViewPower not installed or path incorrect
```

Aiden will continue to work normally without UPS features.

## Troubleshooting

### UPS Monitor Not Starting

**Check logs:**
```
logs/aiden.log
```

**Common issues:**

1. **ViewPower not installed:**
   - Install ViewPower from your UPS manufacturer
   - Ensure it's running and logging

2. **Custom log path:**
   - Check `UPS_INFO_LOG_PATH` in `.env`
   - Verify the file exists and is being updated

3. **Disabled in config:**
   - Ensure `UPS_ENABLED=true` in `.env`

### No Alerts During Power Loss

1. **Check if monitoring is running:**
   ```
   # Look for this line in logs:
   ✅ UPS monitoring started
   ```

2. **Verify ViewPower is logging:**
   ```powershell
   Get-Content "C:\ViewPower\log\info.log" -Tail 10
   ```

3. **Check battery thresholds:**
   - Maybe battery hasn't dropped to alert threshold yet
   - Lower `UPS_ALERT_THRESHOLD` for earlier warnings

## Safety Notes

⚠️ **IMPORTANT:**
- UPS monitoring is a **safety feature**, not a replacement for proper UPS maintenance
- Always keep your UPS batteries in good condition
- Test your UPS regularly (monthly recommended)
- Replace UPS batteries every 2-3 years
- Don't rely solely on software - be aware of your UPS status lights/beeps

🔒 **Shutdown Protection:**
- Forced shutdown uses Windows `shutdown /s` command
- Gives 30-second grace period for saving work
- If power returns during that 30-second countdown, Aiden aborts the pending shutdown automatically
- **Save your work regularly when on battery power!**

## Advanced Usage

### Disable UPS Monitoring Temporarily

```env
UPS_ENABLED=false
```

Or stop it at runtime (requires code modification - not exposed via voice commands).

### Custom Shutdown Messages

Edit `src/utils/ups_handler.py` to customize Aiden's voice messages:

```python
message = (
    f"Your custom message here, Sir! "
    f"Battery at {battery_pct}%. "
    f"Your custom instructions."
)
```

### Integration with Other Systems

The UPS monitor fires callbacks that you can hook into:

- `on_power_lost` - AC power lost
- `on_power_restored` - AC power restored
- `on_battery_alert` - Battery at alert threshold
- `on_battery_critical` - Battery at critical threshold
- `on_shutdown_request` - Shutdown requested

See `src/utils/ups_monitor.py` for implementation details.

## Future Enhancements

Planned features:
- [ ] Battery runtime estimation
- [ ] Historical power outage logging
- [ ] Email/SMS notifications on power loss
- [ ] Custom actions at each threshold
- [ ] Integration with smart home to pause tasks during power loss
- [ ] Battery health monitoring

## Support

**Questions or issues?**
- Check `logs/aiden.log` for detailed monitoring info
- File an issue on GitHub
- Test with `python scripts/diagnostics/monitor_viewpower_logs.py` first

---

**Stay powered, stay protected! 🔋⚡**
