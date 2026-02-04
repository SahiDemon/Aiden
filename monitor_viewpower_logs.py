#!/usr/bin/env python3
"""
Monitor ViewPower's datalog in real-time
Watches C:\\ViewPower\\datalog\\ for events and decodes them
"""

import os
import time
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)

# ViewPower datalog path
DATALOG_DIR = r"C:\ViewPower\datalog"
INFO_LOG = r"C:\ViewPower\log\info.log"

# Event codes from observations
EVENT_CODES = {
    '000000': 'Normal operation',
    '000001': 'Communication established / System started',
    '000010': 'AC failure / On battery',
    '000100': 'Battery low',
    '001000': 'AVR active',
    '001010': 'AC failure + AVR',
    # Add more as we discover them
}

def get_today_log():
    """Get today's datalog file path."""
    today = datetime.now().strftime('%Y-%m-%d')
    return os.path.join(DATALOG_DIR, f"{today}.txt")

def parse_datalog_line(line):
    """Parse a line from the datalog."""
    if not line.strip() or 'Time|' in line:
        return None
    
    parts = [p.strip() for p in line.split('|')]
    if len(parts) < 10:
        return None
    
    try:
        return {
            'time': parts[0],
            'input_voltage': int(parts[1]) if parts[1].isdigit() else 0,
            'output_voltage': int(parts[2]) if parts[2].isdigit() else 0,
            'battery_capacity': int(parts[3]) if parts[3].isdigit() else 0,
            'backup_time': int(parts[4]) if parts[4].isdigit() else 0,
            'power_mode': parts[5],
            'threshold': parts[6],
            'shutdown': parts[7],
            'ups_turnoff': parts[8],
            'event': parts[9]
        }
    except:
        return None

def decode_event(event_code):
    """Decode event code to human-readable string."""
    return EVENT_CODES.get(event_code, f'Unknown event: {event_code}')

def monitor_info_log_realtime():
    """Monitor info.log in real-time for QS responses (actual UPS status)."""
    if not os.path.exists(INFO_LOG):
        print(f"{Fore.RED}Info log not found: {INFO_LOG}")
        print(f"{Fore.YELLOW}Make sure ViewPower is running!")
        return
    
    print(f"{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}Real-Time UPS Mode Monitor - ViewPower Live Data")
    print(f"{Fore.CYAN}{'='*80}")
    print(f"Watching: {INFO_LOG}")
    print(f"{Fore.YELLOW}Disconnect AC power to see mode change to BATTERY MODE")
    print(f"{Fore.YELLOW}Press Ctrl+C to stop\n")
    
    # Track state changes
    last_mode = None
    last_status_bits = None
    
    # Open file and seek to end
    with open(INFO_LOG, 'r', encoding='utf-8', errors='ignore') as f:
        # Go to end of file
        f.seek(0, 2)
        
        try:
            while True:
                line = f.readline()
                
                if line:
                    # Look for QS command responses
                    if 'command:QSvalue' in line:
                        try:
                            # Extract response: (244.3 244.3 244.3 030 50.0 27.2 --.- 00001001
                            start = line.index('(')
                            # Find end before Chinese characters
                            data_str = line[start:].split('å')[0].strip()
                            
                            # Parse the response
                            parts = data_str.strip('()').split()
                            
                            if len(parts) >= 8:
                                input_v = float(parts[0])
                                output_v = float(parts[2])
                                load = int(parts[3])
                                freq = float(parts[4])
                                batt_v = float(parts[5])
                                # Clean status bits - remove any trailing Chinese characters
                                status_bits = parts[7][:8] if len(parts[7]) >= 8 else parts[7]
                                
                                # Decode mode from status bits (reading from LEFT to RIGHT based on observations)
                                # First bit (leftmost): 1 = On Battery, 0 = On AC/Line
                                on_battery = status_bits[0] == '1'
                                
                                # Second bit: Battery Low warning
                                battery_low = len(status_bits) > 1 and status_bits[1] == '1'
                                
                                # Check battery voltage for additional low battery warning
                                # Typical 24V system (2x 12V batteries in series):
                                # 27.0V+ = 100% (float charge)
                                # 26.4V  = 90%
                                # 25.2V  = 50%
                                # 24.0V  = 20% (Warning)
                                # 22.0V  = 10% (Critical - shutdown!)
                                # 20.0V  = Empty (damage risk)
                                
                                # Calculate battery percentage
                                if batt_v > 0:
                                    # Linear approximation for lead-acid 24V
                                    if batt_v >= 27.0:
                                        batt_pct = 100
                                    elif batt_v <= 20.0:
                                        batt_pct = 0
                                    else:
                                        # Map 20V-27V to 0%-100%
                                        batt_pct = int(((batt_v - 20.0) / (27.0 - 20.0)) * 100)
                                else:
                                    batt_pct = 0
                                
                                voltage_critical = batt_v < 22.0 if batt_v > 0 else False
                                
                                current_mode = 'BATTERY' if on_battery else 'LINE'
                                
                                # Alert on any critical condition
                                critical_alert = battery_low or voltage_critical
                                
                                # Only print if mode changed OR status bits changed
                                if current_mode != last_mode or status_bits != last_status_bits:
                                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    
                                    # CRITICAL BATTERY LOW ALERT
                                    if critical_alert:
                                        print(f"\n{Fore.RED}{Style.BRIGHT}{'='*80}")
                                        print(f"{Fore.RED}{Style.BRIGHT}🚨🚨🚨 CRITICAL: BATTERY LOW - SHUTDOWN RECOMMENDED! 🚨🚨🚨")
                                        print(f"{Fore.RED}{Style.BRIGHT}{'='*80}\n")
                                    
                                    # Big alert on mode change
                                    elif current_mode != last_mode and last_mode is not None:
                                        print(f"\n{Fore.CYAN}{'='*80}")
                                        if on_battery:
                                            print(f"{Fore.RED}{Style.BRIGHT}⚠⚠⚠ MODE CHANGE: AC POWER LOST - SWITCHED TO BATTERY MODE ⚠⚠⚠")
                                        else:
                                            print(f"{Fore.GREEN}{Style.BRIGHT}✓✓✓ MODE CHANGE: AC POWER RESTORED - SWITCHED TO LINE MODE ✓✓✓")
                                        print(f"{Fore.CYAN}{'='*80}\n")
                                    
                                    # Show current status
                                    mode_color = Fore.RED if on_battery else Fore.GREEN
                                    mode_icon = "🔋 BATTERY MODE" if on_battery else "⚡ LINE MODE"
                                    
                                    print(f"{Fore.CYAN}[{timestamp}]")
                                    print(f"{mode_color}{Style.BRIGHT}  UPS Mode: {mode_icon}")
                                    
                                    # Battery warnings
                                    if battery_low:
                                        print(f"{Fore.RED}{Style.BRIGHT}  ⚠ BATTERY LOW WARNING (Status bit set)")
                                    if voltage_critical:
                                        print(f"{Fore.RED}{Style.BRIGHT}  ⚠ BATTERY VOLTAGE CRITICAL ({batt_v:.1f}V < 22V)")
                                    
                                    print(f"{Fore.WHITE}  Input:    {input_v:.1f}V")
                                    print(f"{Fore.WHITE}  Output:   {output_v:.1f}V")
                                    
                                    load_color = Fore.RED if load > 80 else (Fore.YELLOW if load > 50 else Fore.GREEN)
                                    print(f"{load_color}  Load:     {load}%")
                                    
                                    # Color-code battery voltage and percentage
                                    batt_color = Fore.RED if voltage_critical else (Fore.YELLOW if batt_v < 24.0 else Fore.GREEN)
                                    batt_pct_color = Fore.RED if batt_pct < 20 else (Fore.YELLOW if batt_pct < 50 else Fore.GREEN)
                                    print(f"{batt_color}  Battery:  {batt_v:.1f}V {batt_pct_color}({batt_pct}%)")
                                    
                                    print(f"{Fore.WHITE}  Frequency:{freq:.1f}Hz")
                                    print(f"{Fore.WHITE}  Status:   {status_bits}")
                                    print()
                                    
                                    last_mode = current_mode
                                    last_status_bits = status_bits
                                else:
                                    # Just show a heartbeat indicator
                                    mode_symbol = "🔋" if on_battery else "⚡"
                                    alert_icon = " 🚨LOW" if critical_alert else ""
                                    batt_color = "\033[91m" if voltage_critical else ""
                                    reset_color = "\033[0m" if voltage_critical else ""
                                    
                                    print(f"{mode_symbol}{alert_icon} {datetime.now().strftime('%H:%M:%S')} | "
                                          f"{input_v:.0f}V → {output_v:.0f}V | "
                                          f"Load: {load}% | "
                                          f"Batt: {batt_color}{batt_v:.1f}V ({batt_pct}%){reset_color}", 
                                          end='\r')
                        
                        except Exception as e:
                            # Silently skip parse errors
                            pass
                else:
                    time.sleep(0.2)  # Check frequently for real-time updates
        
        except KeyboardInterrupt:
            print(f"\n\n{Fore.YELLOW}Monitoring stopped")

def parse_info_log():
    """Parse recent QS commands from info.log to see real UPS data."""
    print(f"{Fore.CYAN}{'='*80}")
    print(f"{Fore.CYAN}Recent UPS Status from ViewPower Logs")
    print(f"{Fore.CYAN}{'='*80}\n")
    
    if not os.path.exists(INFO_LOG):
        print(f"{Fore.RED}Info log not found!")
        return
    
    # Read last 200 lines
    with open(INFO_LOG, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()[-200:]
    
    qs_responses = []
    
    for line in lines:
        if 'command:QSvalue' in line:
            # Extract the response data
            # Example: command:QSvalue(244.3 244.3 244.3 030 50.0 27.2 --.- 00001001
            try:
                start = line.index('(')
                data_str = line[start:].split('å')[0].strip()  # Remove Chinese chars
                qs_responses.append(data_str)
            except:
                pass
    
    if qs_responses:
        # Show last 5 unique responses
        unique = []
        for resp in reversed(qs_responses):
            if resp not in unique:
                unique.append(resp)
            if len(unique) >= 5:
                break
        
        print(f"{Fore.YELLOW}Last 5 UPS status queries (QS command):\n")
        
        for resp in reversed(unique):
            parse_qs_response(resp)
            print()
    else:
        print(f"{Fore.YELLOW}No recent QS responses found in log")

def parse_qs_response(response):
    """Parse a QS protocol response."""
    # Format: (InputV FaultV OutputV Load% Freq BattV Temp Status
    # Example: (244.3 244.3 244.3 030 50.0 27.2 --.- 00001001
    try:
        data = response.strip('()').split()
        
        if len(data) >= 8:
            input_v = float(data[0])
            output_v = float(data[2])
            load = int(data[3])
            freq = float(data[4])
            batt_v = float(data[5])
            temp = data[6]
            status = data[7]
            
            print(f"{Fore.CYAN}Status: {status}")
            print(f"  Input:  {Fore.WHITE}{input_v:.1f}V")
            print(f"  Output: {Fore.WHITE}{output_v:.1f}V")
            print(f"  Load:   {Fore.YELLOW if load > 50 else Fore.GREEN}{load}%")
            print(f"  Freq:   {Fore.WHITE}{freq:.1f}Hz")
            print(f"  Battery:{Fore.WHITE}{batt_v:.1f}V")
            
            # Decode status bits
            on_battery = status.endswith('0')
            print(f"  Mode:   {Fore.RED if on_battery else Fore.GREEN}{'ON BATTERY' if on_battery else 'AC ONLINE'}")
    
    except Exception as e:
        print(f"{Fore.RED}Parse error: {e}")
        print(f"  Raw: {response}")

def main():
    """Main entry."""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'status':
        parse_info_log()
    else:
        print(f"\n{Fore.CYAN}ViewPower Log Monitor")
        print(f"{Fore.WHITE}Real-time UPS mode monitoring (Line mode ⚡ vs Battery mode 🔋)")
        print(f"{Fore.WHITE}Options:")
        print(f"  python monitor_viewpower_logs.py        - Monitor UPS mode in real-time")
        print(f"  python monitor_viewpower_logs.py status - Show recent UPS status snapshot\n")
        
        monitor_info_log_realtime()

if __name__ == "__main__":
    main()
