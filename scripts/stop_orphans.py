#!/usr/bin/env python3
"""Stop duplicate tradeops/legacy bot processes without matching this shell."""
import os
import signal
import time


ROOT = "/home/alfred/tradeops"
OLD = "/home/alfred/mtai"
TARGET_CWDS = (
    f"{ROOT}/trading/forex/src",
    f"{ROOT}/trading/crypto/src",
    f"{ROOT}/control/server",
    f"{OLD}/hedgefund-repo/client",
)
TARGET_ARGS = ("run.py --mode", "node server.js", "vite --host")


def iter_targets():
    self_pid = os.getpid()
    parent_pid = os.getppid()
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        if pid in (self_pid, parent_pid):
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\0", b" ").decode(errors="ignore").strip()
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except Exception:
            continue
        normalized_cwd = cwd.removesuffix(" (deleted)")
        if normalized_cwd not in TARGET_CWDS:
            continue
        if not any(arg in cmd for arg in TARGET_ARGS):
            continue
        yield pid, cwd, cmd


def main():
    killed = []
    for pid, cwd, cmd in iter_targets():
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append((pid, cwd, cmd))
        except ProcessLookupError:
            pass

    time.sleep(0.5)
    for pid, cwd, cmd in list(killed):
        if not os.path.exists(f"/proc/{pid}"):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    for pid, cwd, cmd in killed:
        print(f"stopped {pid} cwd={cwd} cmd={cmd[:120]}")
    print(f"orphan bot/control processes stopped: {len(killed)}")


if __name__ == "__main__":
    main()
