"""
Event Loop Policy Configuration
Sets the correct event loop policy for Windows to fix psycopg compatibility
"""
import asyncio
import platform

# CRITICAL: Set event loop policy for Windows BEFORE any async operations
# This fixes the psycopg "ProactorEventLoop" error on Windows
if platform.system() == 'Windows':
    import selectors
    
    class SelectEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
        """Custom event loop policy that uses SelectorEventLoop on Windows"""
        def new_event_loop(self):
            selector = selectors.SelectSelector()
            return asyncio.SelectorEventLoop(selector)
    
    # Set policy globally - this affects all event loops created after this point
    asyncio.set_event_loop_policy(SelectEventLoopPolicy())
    print("[OK] Windows event loop policy set for psycopg compatibility")

def ensure_selector_event_loop():
    """Ensure the current event loop is a SelectorEventLoop on Windows"""
    if platform.system() == 'Windows':
        try:
            loop = asyncio.get_running_loop()
            if not isinstance(loop, asyncio.SelectorEventLoop):
                print("[WARNING] Current event loop is not SelectorEventLoop")
                return False
            return True
        except RuntimeError:
            # No running loop
            return True
    return True
