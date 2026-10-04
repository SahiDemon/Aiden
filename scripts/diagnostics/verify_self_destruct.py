import asyncio
import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

# Configure logging
logging.basicConfig(level=logging.INFO)

from src.execution.command_executor import CommandExecutor
from src.speech.tts import get_tts_engine

async def test_self_termination():
    executor = CommandExecutor()
    tts = get_tts_engine()
    
    print("Testing 'self_termination' command...")
    print("This should print a dramatic message, PLAY AUDIO, and then exit the process after 12 seconds.")
    
    # Mock system controller to avoid actual shell commands if any
    # But self_termination is handled directly in executor
    
    result = await executor.execute({
        "type": "self_termination",
        "params": {}
    })
    
    print(f"Result: {result}")
    
    if result["success"] and result["response_data"]["type"] == "self_termination":
        print("PASS: Command executed successfully.")
        message = result['response_data']['message']
        print(f"Message: {message}")
        
        # Manually invoke TTS since we are bypassing the Assistant
        print("Speaking message...")
        await tts.speak(message)
        
        print("Waiting for exit (music should be playing)...")
        await asyncio.sleep(15) # Wait longer than the 12s timeout
        print("FAIL: Process did not exit!")
    else:
        print("FAIL: Command failed.")

if __name__ == "__main__":
    asyncio.run(test_self_termination())
