import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


root = Path(__file__).resolve().parent / "results" / "httpserver" / "stress"
rows = json.loads((root / "stress-summary.json").read_text())
clients = [row["clients"] for row in rows]

plt.rcParams.update({"font.size": 10})
fig, axes = plt.subplots(2, 2, figsize=(12, 8))

def line(axis, field, label, style="-"):
    axis.plot(
        clients, [row[field] for row in rows],
        style, marker="o", label=label
    )

line(axes[0, 0], "cpu_busy_percent_average", "Average")
line(axes[0, 0], "cpu_busy_percent_peak", "Peak", "--")
axes[0, 0].set_title("Server CPU busy time")
axes[0, 0].set_ylabel("Guest CPU busy (%)")

line(axes[0, 1], "memory_used_mib_average", "Average")
line(axes[0, 1], "memory_used_mib_peak", "Peak", "--")
axes[0, 1].set_title("Server memory usage")
axes[0, 1].set_ylabel("Used memory (MiB)")

line(axes[1, 0], "network_rx_mbps_average", "Receive average")
line(axes[1, 0], "network_rx_mbps_peak", "Receive peak", "--")
line(axes[1, 0], "network_tx_mbps_average", "Send average")
line(axes[1, 0], "network_tx_mbps_peak", "Send peak", "--")
axes[1, 0].set_title("Server network traffic")
axes[1, 0].set_ylabel("Traffic rate (Mbps)")

line(axes[1, 1], "responses_per_second", "All server-recorded responses")
axes[1, 1].plot(
    clients,
    [row["http_200"] / row["duration_seconds"] for row in rows],
    "--", marker="s", label="HTTP 200 responses"
)
axes[1, 1].set_title("Server-recorded response throughput")
axes[1, 1].set_ylabel("Responses per second")

for axis in axes.flat:
    axis.set_xlabel("Concurrent clients")
    axis.set_xticks(clients)
    axis.set_ylim(bottom=0)
    axis.grid(alpha=0.25)
    axis.legend(fontsize=9)

fig.suptitle("HW4: HTTPServer performance on f1-micro", fontsize=16)
fig.text(
    0.5, 0.025,
    "Each run: 180 seconds; resource sampling: approximately 1 second.\n"
    "Whole-VM measurements; expected HTTP 400 responses included in total throughput.",
    ha="center", fontsize=9
)
fig.tight_layout(rect=(0, 0.08, 1, 0.95))

for extension in ("png", "pdf"):
    path = root / f"performance-graph.{extension}"
    fig.savefig(path, dpi=200)
    print(f"Saved {path}")

plt.close(fig)
