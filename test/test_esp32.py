import requests
import time
import keyboard  # Added for keyboard input detection

# ==============================================================================
# Configuration
# ==============================================================================
# IMPORTANT: Replace this with the IP address of your ESP32
# You can find this in the Arduino Serial Monitor when the ESP32 starts up.
ESP32_IP_ADDRESS = "192.168.1.180" # e.g., "192.168.1.123"
# ==============================================================================


# --- Base URL for the ESP32 server ---
BASE_URL = f"http://{ESP32_IP_ADDRESS}"


def _send_command(command_path):
    """
    Internal helper function to send a command to the ESP32 server.
    Handles the HTTP request and provides clear error messages.
    """
    try:
        url = f"{BASE_URL}/{command_path}"
        print(f"Sending command to {url} ...")
        # Set a timeout to prevent the script from hanging indefinitely
        response = requests.get(url, timeout=5)
        
        # Check if the request was successful
        if response.status_code == 200:
            print(f"Success! ESP32 says: {response.text}")
        else:
            print(f"Error: Received status code {response.status_code} from ESP32.")
            
    except requests.exceptions.RequestException as e:
        print(f"--- CONNECTION ERROR ---")
        print(f"An error occurred: {e}")
        print("\nCould not connect to the ESP32. Please check the following:")
        print("1. Is the ESP32 powered on and connected to the same Wi-Fi network?")
        print(f"2. Is the IP address '{ESP32_IP_ADDRESS}' correct?")
        print("3. Is the ESP32 Web Server running (check the Serial Monitor)?")


# --- Functions to control your device ---

def turn_on_any_speed():
    """Turns the device ON with a single unified command."""
    _send_command("on")  # Using a single command for all speeds

# Keeping these for backward compatibility but they all do the same thing now
def turn_on_speed_1():
    """Turns the device ON and sets it to Speed 1."""
    turn_on_any_speed()

def set_speed_2():
    """Sets the device to Speed 2."""
    turn_on_any_speed()

def set_speed_3():
    """Sets the device to Speed 3."""
    turn_on_any_speed()

def change_mode():
    """Sends the mode change command."""
    _send_command("mode")

def turn_off():
    """Turns the device OFF."""
    _send_command("off")

def listen_for_key_presses():
    """Listen for key presses and execute corresponding commands."""
    print("--- ESP32 Control Using Number Keys ---")
    print("Press the following keys to control your device:")
    print("1, 2, 3: Turn ON/Change Speed (all do the same thing)")
    print("M: Change Mode")
    print("0: Turn OFF")
    print("ESC: Exit the program")
    print("\nWaiting for key presses...")
    
    try:
        while True:
            if keyboard.is_pressed('1') or keyboard.is_pressed('2') or keyboard.is_pressed('3'):
                key = '1' if keyboard.is_pressed('1') else ('2' if keyboard.is_pressed('2') else '3')
                print(f"\nKey '{key}' pressed!")
                turn_on_any_speed()
                time.sleep(0.5)  # Prevent multiple detections
                
            elif keyboard.is_pressed('m') or keyboard.is_pressed('M'):
                print("\nKey 'M' pressed!")
                change_mode()
                time.sleep(0.5)
                
            elif keyboard.is_pressed('0'):
                print("\nKey '0' pressed!")
                turn_off()
                time.sleep(0.5)
                
            elif keyboard.is_pressed('esc'):
                print("\nExiting the program...")
                break
                
            time.sleep(0.1)  # Small delay to reduce CPU usage
                
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        print("Program ended.")

# --- Example Usage ---
if __name__ == "__main__":
    # Use the keyboard control function instead of the sequence
    listen_for_key_presses()
    
    # You can uncomment the below code if you want to run the test sequence instead
    """
    print("--- Running Full Remote Test Sequence ---")

    # Step 1: Turn the device ON to Speed 1
    turn_on_speed_1()
    time.sleep(4)  # Wait 4 seconds

    # Step 2: Change to Speed 2
    set_speed_2()
    time.sleep(4)

    # Step 3: Change to Speed 3
    set_speed_3()
    time.sleep(4)

    # Step 4: Change the Mode
    change_mode()
    time.sleep(4)
    
    # Step 5: Turn the device OFF
    turn_off()

    print("\n--- Test Sequence Complete ---")
    """
