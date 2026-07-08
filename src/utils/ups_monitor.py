"""
UPS Power Monitor - Track AC/Battery mode and trigger smart shutdown
Integrates with ViewPower UPS monitoring and Aiden assistant
"""
import asyncio
import os
import re
import threading
from datetime import datetime
from typing import Optional, Callable
from enum import Enum

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PowerMode(Enum):
    """UPS Power modes"""
    UNKNOWN = "unknown"
    AC_ONLINE = "ac_online"
    BATTERY = "battery"


class UPSMonitor:
    """
    Monitors UPS power status and triggers intelligent shutdown sequence
    
    Features:
    - Real-time power mode detection (AC vs Battery)
    - Battery level monitoring with percentage calculation
    - Smart alert system at configurable thresholds
    - Automatic shutdown with user confirmation
    - Cool voice interactions via Aiden
    """
    
    def __init__(
        self,
        info_log_path: str = r"C:\ViewPower\log\info.log",
        alert_threshold: int = 80,
        critical_threshold: int = 50,
        shutdown_threshold: int = 50,
        polling_interval: float = 1.0,
        on_power_lost: Optional[Callable] = None,
        on_power_restored: Optional[Callable] = None,
        on_battery_alert: Optional[Callable] = None,
        on_battery_critical: Optional[Callable] = None,
        on_shutdown_request: Optional[Callable] = None,
        main_event_loop: Optional[asyncio.AbstractEventLoop] = None
    ):
        """
        Initialize UPS monitor
        
        Args:
            info_log_path: Path to ViewPower info.log
            alert_threshold: Battery % to trigger first alert (default: 80%)
            critical_threshold: Battery % to trigger critical alert (default: 50%)
            shutdown_threshold: Battery % to force shutdown (default: 50%)
            polling_interval: Seconds between log checks
            on_power_lost: Callback when switching to battery
            on_power_restored: Callback when mains power returns
            on_battery_alert: Callback at alert threshold
            on_battery_critical: Callback at critical threshold
            on_shutdown_request: Callback to perform shutdown
        """
        self.info_log_path = info_log_path
        self.alert_threshold = alert_threshold
        self.critical_threshold = critical_threshold
        self.shutdown_threshold = shutdown_threshold
        self.polling_interval = polling_interval
        
        # Callbacks
        self.on_power_lost = on_power_lost
        self.on_power_restored = on_power_restored
        self.on_battery_alert = on_battery_alert
        self.on_battery_critical = on_battery_critical
        self.on_shutdown_request = on_shutdown_request
        self.main_event_loop = main_event_loop
        
        # State tracking
        self.current_mode = PowerMode.UNKNOWN
        self.battery_voltage = 0.0
        self.battery_percentage = 0
        self.load_percentage = 0
        self.input_voltage = 0.0
        self.output_voltage = 0.0
        
        # Time-based alert tracking
        self.power_lost_time = None
        self.first_alert_sent = False
        self.shutdown_confirmed = False
        
        # Alert timings (in seconds)
        self.first_alert_delay = 120  # 2 minutes
        self.absolute_deadline = 240  # 4 minutes (absolute max - force shutdown)
        
        # Monitoring thread
        self.running = False
        self.monitor_thread = None
        
        logger.info("UPS Monitor initialized")
        logger.info(f"  Alert threshold: {alert_threshold}%")
        logger.info(f"  Critical threshold: {critical_threshold}%")
        logger.info(f"  Shutdown threshold: {shutdown_threshold}%")
    
    def start(self):
        """Start monitoring UPS status"""
        if self.running:
            logger.warning("UPS monitor already running")
            return
        
        if not os.path.exists(self.info_log_path):
            logger.error(f"ViewPower log not found: {self.info_log_path}")
            logger.warning("UPS monitoring disabled - ViewPower not installed or path incorrect")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("✅ UPS monitoring started")
    
    def stop(self):
        """Stop monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("UPS monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop (runs in background thread)"""
        try:
            with open(self.info_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Seek to end of file
                f.seek(0, 2)
                
                while self.running:
                    line = f.readline()
                    
                    if line:
                        # Look for QS command responses
                        if 'command:QSvalue' in line:
                            self._parse_qs_response(line)
                    else:
                        # No new data, sleep briefly
                        threading.Event().wait(self.polling_interval)
        
        except Exception as e:
            logger.error(f"UPS monitor error: {e}", exc_info=True)
            self.running = False
    
    def _parse_qs_response(self, line: str):
        """Parse QS command response and update state"""
        try:
            # Extract response: (244.3 244.3 244.3 030 50.0 27.2 --.- 00001001
            start = line.index('(')
            data_str = line[start:].split('å')[0].strip()
            
            # Parse the response
            parts = data_str.strip('()').split()
            
            if len(parts) >= 8:
                input_v = float(parts[0])
                output_v = float(parts[2])
                load = int(parts[3])
                batt_v = float(parts[5])
                status_bits = parts[7][:8] if len(parts[7]) >= 8 else parts[7]
                
                # Update state
                self.input_voltage = input_v
                self.output_voltage = output_v
                self.load_percentage = load
                self.battery_voltage = batt_v
                
                # Calculate battery percentage (24V lead-acid system)
                # 27.0V = 100%, 20.0V = 0%
                if batt_v >= 27.0:
                    self.battery_percentage = 100
                elif batt_v <= 20.0:
                    self.battery_percentage = 0
                else:
                    self.battery_percentage = int(((batt_v - 20.0) / (27.0 - 20.0)) * 100)
                
                # Detect power mode from status bits
                # First bit: 1 = On Battery, 0 = On AC
                on_battery = status_bits[0] == '1'
                new_mode = PowerMode.BATTERY if on_battery else PowerMode.AC_ONLINE
                               # Check for power mode change
                if new_mode != self.current_mode and self.current_mode != PowerMode.UNKNOWN:
                    self._handle_power_mode_change(new_mode)
                
                self.current_mode = new_mode
                
                # Check battery levels (only if on battery)
                if self.current_mode == PowerMode.BATTERY:
                    self._check_battery_levels()
        
        except Exception as e:
            logger.debug(f"Failed to parse UPS data: {e}")
    
    def _handle_power_mode_change(self, new_mode: PowerMode):
        """Handle power mode transitions"""
        old_mode = self.current_mode
        
        if new_mode == PowerMode.BATTERY and old_mode == PowerMode.AC_ONLINE:
            # AC POWER LOST - Switched to battery
            import time
            self.power_lost_time = time.time()
            
            logger.warning("⚠️ Power lost - UPS running on battery!")
            logger.info(f"Battery: {self.battery_voltage:.1f}V ({self.battery_percentage}%)")
            logger.info(f"Load: {self.load_percentage}%")
            logger.info(f"Time-based alerts: Immediate ask, 2min check-in, 4min force shutdown")
            
            # Reset alert flags
            self.first_alert_sent = False
            # Trigger callback
            if self.on_power_lost:
                self._call_async_callback(self.on_power_lost)
        
        elif new_mode == PowerMode.AC_ONLINE and old_mode == PowerMode.BATTERY:
            # Power restored
            logger.info("✅ Power restored - UPS back on line mode")
            
            # Reset time tracking
            self.power_lost_time = None
            
            # Reset flags
            self.first_alert_sent = False
            self.shutdown_confirmed = False

            if self.on_power_restored:
                self._call_async_callback(self.on_power_restored)

    def _check_battery_levels(self):
        """Check time-based alerts and critical battery voltage"""
        if not self.power_lost_time or self.shutdown_confirmed:
            return
        
        import time
        elapsed = time.time() - self.power_lost_time
        
        # Critical battery voltage check (independent of time)
        if self.battery_voltage > 0 and self.battery_voltage < 22.0:
            logger.error(f"🚨 CRITICAL BATTERY VOLTAGE: {self.battery_voltage:.1f}V - Forcing emergency shutdown!")
            
            if self.on_shutdown_request:
                self._call_async_callback(
                    self.on_shutdown_request,
                    force=True,
                    reason="critical_voltage"
                )
            return
        
        # Time-based alerts
        if elapsed >= self.absolute_deadline:
            logger.error(f"🚨 4 MINUTES ON BATTERY - No response from user, forcing shutdown!")
            
            if self.on_shutdown_request:
                self._call_async_callback(
                    self.on_shutdown_request,
                    force=True,
                    reason="timeout"
                )
        
        # 2 minutes: Second attempt - execute mandatory shutdown without asking again
        elif elapsed >= self.first_alert_delay and not self.first_alert_sent:
            logger.warning(f"⚠️ 2 MINUTES ON BATTERY - Second attempt reached! Triggering sure shutdown without re-asking.")
            self.first_alert_sent = True
            
            if self.on_battery_alert:
                self._call_async_callback(
                    self.on_battery_alert,
                    elapsed_minutes=int(elapsed / 60)
                )

    def _call_async_callback(self, callback: Callable, **kwargs):
        """Call async callback from sync thread"""
        try:
            if not self.main_event_loop:
                logger.error("Main event loop not set - cannot call async callbacks")
                return
            
            # Schedule callback in the main loop
            if asyncio.iscoroutinefunction(callback):
                future = asyncio.run_coroutine_threadsafe(callback(**kwargs), self.main_event_loop)
                future.result(timeout=30)
            else:
                callback(**kwargs)
        
        except Exception as e:
            logger.error(f"Error calling UPS callback: {e}", exc_info=True)

    def confirm_shutdown(self, confirmed: bool):
        """
        User confirmation for shutdown
        
        Args:
            confirmed: True to proceed with shutdown, False to cancel
        """
        self.shutdown_confirmed = confirmed
        
        if confirmed:
            logger.info("User confirmed shutdown")
            
            # Cancel timeout task
            if self.shutdown_timeout_task:
                self.shutdown_timeout_task.cancel()
            
            # Trigger shutdown
            if self.on_shutdown_request:
                self._call_async_callback(
                    self.on_shutdown_request,
                    force=False,
                    reason="user_confirmed"
                )
        else:
            logger.info("User cancelled shutdown - will wait for critical battery level")

    def get_status(self) -> dict:
        """Get current UPS status"""
        time_on_battery = None
        if self.power_lost_time:
            elapsed = (datetime.now() - self.power_lost_time).total_seconds()
            time_on_battery = int(elapsed / 60)
        
        return {
            "mode": self.current_mode.value,
            "battery_voltage": self.battery_voltage,
            "battery_percentage": self.battery_percentage,
            "load_percentage": self.load_percentage,
            "input_voltage": self.input_voltage,
            "output_voltage": self.output_voltage,
            "time_on_battery_minutes": time_on_battery,
            "first_alert_sent": self.first_alert_sent
        }


# Global instance
_ups_monitor: Optional[UPSMonitor] = None


def get_ups_monitor(**kwargs) -> UPSMonitor:
    """Get or create global UPS monitor instance"""
    global _ups_monitor
    if _ups_monitor is None:
        _ups_monitor = UPSMonitor(**kwargs)
    return _ups_monitor
