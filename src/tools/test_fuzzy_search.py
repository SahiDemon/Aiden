import asyncio
import sys
from typing import List

from src.core.context_manager import get_context_manager
from src.utils.system_context import get_system_context


async def run_test(user_text: str, modes: List[str], do_launch: bool, force_steam: bool, show_steam: bool, debug_steam: bool, appid_override: str | None, resolve_only: bool) -> int:
    cm = get_context_manager()
    sys_ctx = get_system_context()

    # Minimal context for extraction
    context = cm._empty_context()

    # Extract query
    query = cm._extract_query_from_text(user_text, context)
    print(f"User text: {user_text}")
    print(f"Extracted query: {query or '(none)'}")

    # App match
    if "app" in modes or "both" in modes:
        if query:
            app_info = await sys_ctx.find_app(query)
        else:
            app_info = None
        print("\n[App Match]")
        if app_info:
            display_name = app_info.get("display_name") or app_info.get("name") or query
            exe_path = app_info.get("exe_path", "")
            install_path = app_info.get("install_path", "")
            print(f"  name: {display_name}")
            print(f"  exe:  {exe_path}")
            print(f"  path: {install_path}")
            # Steam resolution
            from src.execution.app_launcher import get_app_launcher
            launcher = get_app_launcher()
            steam_appid = await launcher._resolve_steam_appid(query.lower(), install_path)
            print("  Resolved Steam appid (robust):", steam_appid or "(none)")
            if steam_appid:
                print(f"  Steam launch URL: steam://run/{steam_appid}")
            if show_steam:
                libs = launcher._get_steam_library_steamapps()
                print("  steam libraries:")
                for p in libs:
                    print("   -", p)
                # Show hinted steamapps if derivable from install_path
                hinted = None
                if install_path and "steamapps" in install_path.lower():
                    from pathlib import Path
                    pp = Path(install_path)
                    for parent in pp.parents:
                        if parent.name.lower() == "steamapps":
                            hinted = str(parent)
                            break
                if hinted:
                    print("  hinted steamapps:", hinted)
            if debug_steam:
                cands = launcher._find_steam_candidates(query.lower(), install_path)
                print("  steam candidates:")
                if not cands:
                    print("   (none)")
                else:
                    for c in cands[:10]:
                        print(f"   - appid {c.get('appid')}: {c.get('name')} | installdir={c.get('installdir')} | steamapps={c.get('steamapps')}")
        else:
            print("  No installed app match found.")

    # Process matches
    if "proc" in modes or "both" in modes:
        print("\n[Process Matches]")
        if query:
            matches = await sys_ctx.find_process(query)
        else:
            matches = []
        if matches:
            for m in matches[:3]:
                print(f"  - {m.get('name','Unknown')} (PID {m.get('pid')}, {m.get('status','?')})")
        else:
            print("  No running process match found.")

    # Show prompt snippet that would be added by build_messages
    needs_context = []
    if "app" in modes or "both" in modes:
        needs_context.append("installed_apps")
    if "proc" in modes or "both" in modes:
        needs_context.append("running_processes")

    msgs = await cm.build_messages(user_text, context, needs_context=needs_context)
    if not resolve_only:
        # Print only the system messages for visibility
        system_msgs = [m for m in msgs if m.get("role") == "system"]
        print("\n[System Messages Sent to LLM]")
        for i, m in enumerate(system_msgs, 1):
            content = m.get("content", "")
            # Print full RELEVANT SYSTEM CONTEXT, otherwise truncate for readability
            if "## RELEVANT SYSTEM CONTEXT" in content:
                print(f"--- system #{i} (RELEVANT SYSTEM CONTEXT) ---\n{content}\n")
            else:
                snippet = content if len(content) < 800 else content[:797] + "..."
                print(f"--- system #{i} ---\n{snippet}\n")

    # Optionally attempt to launch using AppLauncher with the extracted query
    if do_launch and query:
        from src.execution.app_launcher import get_app_launcher
        launcher = get_app_launcher()
        print("[Launch Test]")
        if force_steam:
            # Attempt Steam launch explicitly
            # Need install_path for best resolution
            app_info = await sys_ctx.find_app(query)
            install_path = app_info.get("install_path") if app_info else None
            steam_appid = appid_override or await launcher._resolve_steam_appid(query.lower(), install_path)
            if steam_appid:
                ok = launcher._launch_steam_app(steam_appid)
                print(f"  Forced Steam launch (appid {steam_appid}): {'SUCCESS' if ok else 'FAILED'}")
            else:
                print("  No Steam appid found. Falling back to normal launch...")
                ok = await launcher.launch(query)
                print(f"  Launch result: {'SUCCESS' if ok else 'FAILED'}")
        else:
            ok = await launcher.launch(query)
            print(f"  Launch result: {'SUCCESS' if ok else 'FAILED'}")

    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m src.tools.test_fuzzy_search \"<user text>\" [mode] [--launch] [--steam] [--show-steam] [--debug-steam] [--appid=<id>] [--resolve]", file=sys.stderr)
        print("  mode: app | proc | both (default both)", file=sys.stderr)
        return 2

    user_text = sys.argv[1]
    mode = "both"
    do_launch = False
    force_steam = False
    show_steam = False
    debug_steam = False
    appid_override: str | None = None
    resolve_only = False
    if len(sys.argv) >= 3 and not sys.argv[2].startswith("--"):
        mode = sys.argv[2]
        rest = sys.argv[3:]
    else:
        rest = sys.argv[2:]
    for arg in rest:
        if arg == "--launch":
            do_launch = True
        elif arg == "--steam":
            force_steam = True
        elif arg == "--show-steam":
            show_steam = True
        elif arg == "--debug-steam":
            debug_steam = True
        elif arg.startswith("--appid="):
            appid_override = arg.split("=", 1)[1]
        elif arg == "--resolve":
            resolve_only = True
    if mode not in {"app", "proc", "both"}:
        print("Invalid mode. Use: app | proc | both", file=sys.stderr)
        return 2

    return asyncio.run(run_test(user_text, [mode], do_launch, force_steam, show_steam, debug_steam, appid_override, resolve_only))


if __name__ == "__main__":
    raise SystemExit(main())


