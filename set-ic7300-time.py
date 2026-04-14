#!/usr/bin/python3
#
# Original script by IZ4UFQ
# Modifications for auto-detection and precision sync by M0SPN/OH3SPN
#
# Script to set time and date on the IC-7300 or other Icom radios via CI-V.
#

import time
import serial
import serial.tools.list_ports
import struct
import datetime
import sys
import argparse

# --- CONFIGURATION ---
CIV_ADDRESS = 0x94       # 0x94 is default for IC-7300
BAUDRATE = 19200         # Match your radio settings
# ---------------------

def bcd(value):
    """Converts an integer to BCD (Binary Coded Decimal)."""
    return int(f"{value:02d}", 16)

def send_command(ser, address, command_body):
    """Sends a CI-V command."""
    cmd = [0xFE, 0xFE, address, 0xE0] + command_body + [0xFD]
    ser.write(bytearray(cmd))
    ser.flush()

def is_radio_on(ser, address):
    """
    Checks if radio is responsive by requesting its ID (Cmd 19 00).
    Returns True if radio replies, False otherwise.
    """
    # Clear any stale input buffer
    ser.reset_input_buffer()
    
    # Send 'Read ID' command: 19 00
    # Expected reply: FE FE E0 [Address] 19 00 [ID] FD
    send_command(ser, address, [0x19, 0x00])
    
    # Wait briefly for a reply
    time.sleep(0.2)
    
    if ser.in_waiting > 0:
        # We received data back, so the radio is ON and listening
        # We don't strictly need to parse the ID, just knowing it replied is enough
        ser.reset_input_buffer()
        return True
    
    return False

def find_radio_port(baudrate, address):
    """
    Finds the correct serial port by searching for Silicon Labs CP210x devices 
    and pinging them with a CI-V 'Read ID' command.
    """
    ports = serial.tools.list_ports.comports()
    
    # Filter by common identifiers for the IC-7300's internal USB bridge (10c4:ea60)
    potential_ports = []
    for p in ports:
        if "CP210" in p.description or (p.vid == 0x10c4 and p.pid == 0xea60):
            potential_ports.append(p.device)
    
    if not potential_ports:
        # Fallback: Check for any ttyUSB device if no CP210x is explicitly matched
        potential_ports = [p.device for p in ports if "ttyUSB" in p.device]

    if not potential_ports:
        return None

    print(f"Scanning {len(potential_ports)} potential port(s)...")

    for port_name in potential_ports:
        try:
            # Short timeout for discovery
            with serial.Serial(port_name, baudrate, timeout=0.5) as ser:
                if is_radio_on(ser, address):
                    return port_name
        except (serial.SerialException, OSError):
            continue
            
    return None

def main():
    parser = argparse.ArgumentParser(description="Sync IC-7300 time via CI-V.")
    parser.add_argument("--now", action="store_true", help="Set time immediately (resets seconds to 00), skipping the wait for the top of the minute.")
    parser.add_argument("--port", help="Force a specific serial port (e.g. /dev/ttyUSB0). If omitted, the script will auto-detect.")
    args = parser.parse_args()

    target_port = args.port
    
    if not target_port:
        print("Auto-detecting radio port...")
        target_port = find_radio_port(BAUDRATE, CIV_ADDRESS)
        
    if not target_port:
        print("Error: Could not find IC-7300. Check connection and power.")
        sys.exit(1)

    print(f"Using {target_port}...")
    
    try:
        with serial.Serial(target_port, BAUDRATE, timeout=1) as ser:
            
            # 1. DOUBLE-CHECK RADIO STATUS (if port was specified manually)
            if args.port:
                print("Checking radio status...")
                if not is_radio_on(ser, CIV_ADDRESS):
                    print(f"Error: Radio is not responding on {target_port}.")
                    sys.exit(1)
            
            print("Radio ready!")

            # 2. SET DATE
            now = datetime.datetime.now(datetime.timezone.utc)
            year_str = f"{now.year:04d}"
            
            # Cmd 1A 05 00 94: Set Date (Year, Month, Day)
            body_date = [
                0x1A, 0x05, 0x00, 0x94,
                int(year_str[0:2], 16),
                int(year_str[2:4], 16),
                bcd(now.month),
                bcd(now.day)
            ]
            send_command(ser, CIV_ADDRESS, body_date)
            print(f"Date set to {now.strftime('%Y-%m-%d')}.")

            # 3. SET TIME
            if args.now:
                # Immediate Update
                target_time = now
                print(f"Force update requested (--now). Setting time to {target_time.strftime('%H:%M')} immediately.")
            else:
                # Wait for next minute
                target_time = now + datetime.timedelta(minutes=1)
                target_time = target_time.replace(second=0, microsecond=0)
                
                wait_seconds = (target_time - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
                
                print(f"Current Time: {now.strftime('%H:%M:%S')}")
                print(f"Waiting {wait_seconds:.2f} seconds to sync at {target_time.strftime('%H:%M:00')}...")
                
                if wait_seconds > 0:
                    time.sleep(wait_seconds)

            # Cmd 1A 05 00 95: Set Time (Hour, Minute)
            body_time = [
                0x1A, 0x05, 0x00, 0x95,
                bcd(target_time.hour),
                bcd(target_time.minute)
            ]
            send_command(ser, CIV_ADDRESS, body_time)
            print(f"Time {target_time.strftime('%H:%M')} sent successfully.")

    except serial.SerialException as e:
        print(f"\nError: Could not open serial port {target_port}.")
        print("Is the USB cable plugged in or in use by another program?")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
