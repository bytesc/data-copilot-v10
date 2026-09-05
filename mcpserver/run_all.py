import subprocess
import sys
import time
import signal
import os

SERVERS = [
    ("calculator", 8101, ["python", "-m", "mcpserver.calculator_server"]),
    ("text",        8102, ["python", "-m", "mcpserver.text_server"]),
    ("datetime",    8103, ["python", "-m", "mcpserver.datetime_server"]),
]


def main():
    processes = []
    try:
        for name, port, cmd in SERVERS:
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(p)
            print(f"[{name}] started on port {port} (pid={p.pid})")
            time.sleep(0.3)

        print("=" * 50)
        print("All MCP test servers running:")
        for name, port, _ in SERVERS:
            print(f"  {name:<15} http://localhost:{port}/sse")
        print("=" * 50)
        print("Press Ctrl+C to stop all servers.")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down all servers...")
        for p in processes:
            try:
                os.kill(p.pid, signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGTERM)
            except Exception:
                p.terminate()
        for p in processes:
            p.wait(timeout=5)


if __name__ == "__main__":
    main()