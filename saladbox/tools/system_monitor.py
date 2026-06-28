"""System monitoring tool using psutil."""

from __future__ import annotations

import platform

import psutil

from saladbox.tools.base import BaseTool


class SystemMonitorTool(BaseTool):
    """Monitor system resources: CPU, memory, disk, processes, network."""

    @property
    def name(self) -> str:
        return "system_monitor"

    @property
    def description(self) -> str:
        return (
            "Get system information: CPU usage, memory usage, disk usage, "
            "running processes, network stats, and system info."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "cpu",
                        "memory",
                        "disk",
                        "processes",
                        "network",
                        "system",
                        "all",
                    ],
                    "description": "What system information to retrieve",
                },
                "top_n": {
                    "type": "integer",
                    "description": "Number of top processes to show (default: 10)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str = "all", top_n: int | str = 10) -> str:
        try:
            top_n = int(top_n) if top_n is not None else 10
        except (TypeError, ValueError):
            top_n = 10
        top_n = max(1, min(top_n, 100))
        match action:
            case "cpu":
                return self._cpu()
            case "memory":
                return self._memory()
            case "disk":
                return self._disk()
            case "processes":
                return self._processes(top_n)
            case "network":
                return self._network()
            case "system":
                return self._system()
            case "all":
                return "\n\n".join(
                    [
                        self._system(),
                        self._cpu(),
                        self._memory(),
                        self._disk(),
                        self._network(),
                    ]
                )
            case _:
                return f"Unknown action: {action}"

    def _cpu(self) -> str:
        percent = psutil.cpu_percent(interval=1)
        count = psutil.cpu_count()
        freq = psutil.cpu_freq()

        bar_len = 20
        filled = int(bar_len * percent / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        lines = [
            "## CPU",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Usage | {bar} **{percent}%** |",
            f"| Cores | {count} |",
        ]
        if freq:
            lines.append(f"| Frequency | {freq.current:.0f} MHz |")
        return "\n".join(lines)

    def _memory(self) -> str:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        bar_len = 20
        filled = int(bar_len * mem.percent / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        return (
            "## Memory\n"
            "\n"
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Usage | {bar} **{mem.percent}%** |\n"
            f"| Used | {mem.used / (1024**3):.1f} GB / {mem.total / (1024**3):.1f} GB |\n"
            f"| Available | {mem.available / (1024**3):.1f} GB |\n"
            f"| Swap | {swap.used / (1024**3):.1f} GB / {swap.total / (1024**3):.1f} GB ({swap.percent}%) |"
        )

    def _disk(self) -> str:
        lines = [
            "## Disk",
            "",
            "| Mount | Used | Total | Usage |",
            "|-------|------|-------|-------|",
        ]
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                bar_len = 10
                filled = int(bar_len * usage.percent / 100)
                bar = "█" * filled + "░" * (bar_len - filled)
                lines.append(
                    f"| {part.mountpoint} | {usage.used / (1024**3):.1f} GB | "
                    f"{usage.total / (1024**3):.1f} GB | {bar} {usage.percent}% |"
                )
            except PermissionError:
                continue
        return "\n".join(lines)

    def _processes(self, top_n: int) -> str:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
        lines = [
            f"## Top {top_n} Processes",
            "",
            "| PID | Process | CPU | Memory |",
            "|-----|---------|-----|--------|",
        ]
        for p in procs[:top_n]:
            cpu = p.get("cpu_percent") or 0
            mem = p.get("memory_percent") or 0
            lines.append(f"| {p['pid']} | {p['name'][:20]} | {cpu:.1f}% | {mem:.1f}% |")
        return "\n".join(lines)

    def _network(self) -> str:
        net = psutil.net_io_counters()
        return (
            "## Network\n"
            "\n"
            "| Direction | Data | Packets |\n"
            "|-----------|------|----------|\n"
            f"| Sent | {net.bytes_sent / (1024**2):.1f} MB | {net.packets_sent:,} |\n"
            f"| Received | {net.bytes_recv / (1024**2):.1f} MB | {net.packets_recv:,} |"
        )

    def _system(self) -> str:
        uname = platform.uname()
        return (
            "## System\n"
            "\n"
            f"| Property | Value |\n"
            f"|----------|-------|\n"
            f"| OS | {uname.system} {uname.release} |\n"
            f"| Architecture | {uname.machine} |\n"
            f"| Hostname | {uname.node} |\n"
            f"| Python | {platform.python_version()} |"
        )
