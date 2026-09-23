import subprocess
import sys
import time
import signal
import os

SERVERS = [
    ("calculator", 8101, [sys.executable, "-m", "mcpserver.calculator_server"]),
    ("datetime",    8103, [sys.executable, "-m", "mcpserver.datetime_server"]),
]


def start_server(name: int, port: int, cmd: list) -> subprocess.Popen | None:
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(0.3)
        ret = p.poll()
        if ret is not None:
            stderr_out = p.stderr.read().decode(errors="replace") if p.stderr else ""
            print(f"[{name}] FAILED (exit={ret}): {stderr_out[:200]}")
            return None
        return p
    except FileNotFoundError:
        print(f"[{name}] FAILED: interpreter not found: {cmd[0]}")
        return None
    except PermissionError:
        print(f"[{name}] FAILED: permission denied for: {cmd[0]}")
        return None
    except OSError as e:
        print(f"[{name}] FAILED: {e}")
        return None


def stop_processes(processes: list[subprocess.Popen]):
    for p in processes:
        if p.poll() is not None:
            continue
        try:
            sig = signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGTERM
            os.kill(p.pid, sig)
        except (OSError, PermissionError):
            p.terminate()
    for p in processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"  Force kill pid={p.pid}")
            p.kill()
            p.wait(timeout=3)
        except OSError:
            pass


def main():
    processes = []
    try:
        for name, port, cmd in SERVERS:
            p = start_server(name, port, cmd)
            if p:
                processes.append(p)
                print(f"[{name}] started on port {port} (pid={p.pid})")

        if not processes:
            print("=" * 50)
            print("All servers failed to start. Exiting.")
            return

        print("=" * 50)
        print("MCP servers running:")
        for name, port, _ in SERVERS:
            running = any(p.poll() is None for p in processes)
            status = "running" if running else "stopped"
            print(f"  {name:<15} http://localhost:{port}/sse  [{status}]")
        print("=" * 50)
        print("Press Ctrl+C to stop all servers.")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down all servers...")
        stop_processes(processes)


if __name__ == "__main__":
    main()