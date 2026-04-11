import asyncio
import sys
sys.path.insert(0, 'f:/GitHub/Aiden')

from src.utils.system_context import SystemContextProvider

async def go():
    ctx = SystemContextProvider()
    res = await ctx.get_ai_context()
    procs = res['running_processes']
    print(f"Deduplicated + categorized list: {len(procs)} entries\n")
    for p in procs:
        print(f"  {p}")

asyncio.run(go())
