import asyncio
from src.utils.system_context import SystemContextProvider
async def go():
    ctx = SystemContextProvider()
    res = await ctx.get_ai_context()
    print('TOTAL PROCESSES:', res['total_processes'])
    spot = [p for p in res['running_processes'] if 'spotify' in p.lower()]
    print('SPOTIFY BUNCH:', spot)
asyncio.run(go())
