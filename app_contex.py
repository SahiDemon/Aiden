import psutil
import json
import os

def list_processes():
    """
    Returns a JSON-friendly list of all running processes.
    Each entry includes name, PID, path, CPU %, memory %, and status.
    """
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'exe', 'status', 'cpu_percent', 'memory_percent']):
        try:
            info = proc.info
            processes.append({
                "pid": info['pid'],
                "name": info['name'] or "Unknown",
                "path": info['exe'] or "N/A",
                "status": info['status'],
                "cpu_percent": round(info['cpu_percent'], 2),
                "memory_percent": round(info['memory_percent'], 2)
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes


def show_processes():
    """
    Print all running processes in a readable format
    """
    processes = list_processes()
    print(f"🧠 Active Processes: {len(processes)} running\n")
    for p in sorted(processes, key=lambda x: x['name'].lower()):
        print(f"{p['name']} (PID: {p['pid']}) - CPU: {p['cpu_percent']}% | RAM: {p['memory_percent']}% | {p['status']}")
    print("\n💡 You can send this data to your AI as JSON.")


def get_process_context_json(save=False):
    """
    Returns or saves all running process data as JSON
    """
    processes = list_processes()
    data = {
        "total_processes": len(processes),
        "process_list": processes
    }
    json_str = json.dumps(data, indent=2)
    if save:
        with open("process_context.json", "w", encoding="utf-8") as f:
            f.write(json_str)
        print("✅ Saved process context to process_context.json")
    return json_str


def kill_process(identifier):
    """
    Kills a process by PID or (partial) name.
    """
    killed = []
    identifier = str(identifier).lower()

    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if identifier in str(proc.info['pid']) or identifier in (proc.info['name'] or "").lower():
                proc.terminate()
                killed.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if killed:
        print(f"💀 Killed {len(killed)} process(es):")
        for p in killed:
            print(f" - {p['name']} (PID {p['pid']})")
    else:
        print("⚠️ No matching processes found.")


def main():
    print("🧩 Process Context Tool (for AI integration)")
    print("-------------------------------------------")

    while True:
        cmd = input("\nCommands: list | json | save | kill <name/pid> | exit\n> ").strip().lower()

        if cmd == "exit":
            print("👋 Exiting.")
            break

        elif cmd == "list":
            show_processes()

        elif cmd == "json":
            print(get_process_context_json())

        elif cmd == "save":
            get_process_context_json(save=True)

        elif cmd.startswith("kill "):
            target = cmd.split("kill ", 1)[1].strip()
            if target:
                kill_process(target)
            else:
                print("⚠️ Please specify a process name or PID.")

        else:
            print("❌ Unknown command.")


if __name__ == "__main__":
    main()
