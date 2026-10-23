"""Render the README chart from captured measurements (pip install matplotlib)."""

from collections import Counter
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
profile = json.loads((ROOT / "evidence/silk-queries.json").read_text())
queue = json.loads((ROOT / "evidence/queue-500-jobs.json").read_text())
timestamps = queue["admission_timestamps_ms"]
start = min(timestamps)
events = Counter()
for timestamp in timestamps:
    events[timestamp - start] += 1
    events[timestamp - start + queue["window_ms"]] -= 1
rolling = 0
xs, ys = [0], [0]
for timestamp, change in sorted(events.items()):
    rolling += change
    xs.append(timestamp / 1000)
    ys.append(rolling)
assert max(ys) == queue["max_attempts_in_rolling_window"] <= queue["capacity"]

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.titleweight": "bold",
        "axes.labelcolor": "#475569",
        "text.color": "#0f172a",
        "xtick.color": "#475569",
        "ytick.color": "#475569",
        "svg.fonttype": "none",
    }
)
fig, (left, right) = plt.subplots(
    1, 2, figsize=(11.8, 4.4), gridspec_kw={"width_ratios": [0.9, 1.6]}
)
fig.set_facecolor("white")
for axis in (left, right):
    axis.set_axisbelow(True)
    axis.grid(axis="y", color="#e2e8f0", linewidth=0.8)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color("#cbd5e1")
    axis.tick_params(length=0, pad=8)

counts = [profile["before"]["query_count"], profile["after"]["query_count"]]
left.bar([0, 1], counts, width=0.55, color=["#64748b", "#16a34a"], zorder=3)
for x, count in enumerate(counts):
    left.text(x, count + 10, str(count), ha="center", fontsize=16, fontweight="bold")
left.set_xticks([0, 1], ["Before", "After"])
left.set_ylim(0, 285)
left.set_yticks([0, 100, 200])
left.set_ylabel("SQL queries")
left.set_title(f"Order summary · {profile['order_count']} orders", loc="left", fontsize=13, pad=20)

right.step(xs, ys, where="post", color="#2563eb", linewidth=2)
right.fill_between(xs, ys, step="post", color="#2563eb", alpha=0.08)
right.axhline(queue["capacity"], color="#b91c1c", linewidth=1.2, linestyle=(0, (4, 3)))
right.text(184, 207, "200-attempt limit", color="#991b1b", ha="right", fontsize=10)
right.set_xlim(0, 185)
right.set_ylim(0, 225)
right.set_xticks([0, 30, 60, 90, 120, 150, 180])
right.set_yticks([0, 50, 100, 150, 200])
right.set_xlabel("Seconds since first admission")
right.set_ylabel("Attempts in the previous 60 seconds")
right.set_title("Global rate limit · real-time run", loc="left", fontsize=13, pad=20)
fig.subplots_adjust(left=0.07, right=0.98, top=0.83, bottom=0.23, wspace=0.38)
fig.text(
    0.07,
    0.055,
    f"{queue['jobs_sent']} jobs sent  ·  {queue['provider_attempts']} attempts  ·  {queue['intentional_failures_retried']} intentional retry",
    fontsize=11,
    color="#334155",
)
output = ROOT / "evidence/assets"
output.mkdir(exist_ok=True)
fig.savefig(output / "measured-results.png", dpi=180, facecolor="white")
fig.savefig(output / "measured-results.svg", facecolor="white")
print("Rendered chart from Silk counts and the 60-second-window admission trace")
