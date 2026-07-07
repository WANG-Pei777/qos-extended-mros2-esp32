#!/usr/bin/env python3
"""Generate publication figures from the RTPS packet captures.

Reads the raw .pcapng evidence in results/wireshark/ (kept out of version
control) via tshark and renders vector PDFs + preview PNGs into docs/figures/.

Figures:
  1. fig_discovery_timeline  - healthy post-reset discovery handshake sequence
  2. fig_discovery_deadlock  - stalled vs. passing run after a board reset
                               (SEDP ACKNACKs never answered vs. re-served)
  3. fig_heartbeat_period    - SF_WRITER_HB_PERIOD_MS wire effect (4 s vs 1 s)

All timelines are re-zeroed to the board reboot instant (detected as the first
>3 s gap in the board's SPDP announcements), the natural x-origin for
discovery plots.

Usage:  python3 scripts/figures/make_figures.py
Env:    PCAP_DIR, BOARD_IP, HOST_IP to override defaults.
"""

import os
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PCAP_DIR = os.environ.get("PCAP_DIR", os.path.join(ROOT, "results", "wireshark"))
OUT_DIR = os.path.join(ROOT, "docs", "figures")
BOARD = os.environ.get("BOARD_IP", "10.54.75.107")
HOST = os.environ.get("HOST_IP", "10.54.75.195")

PCAPS = {
    "baseline": "rtps_bidirectional_20260706_183830.pcapng",
    "expA": "expA_hb1000_20260706_184841.pcapng",
    "stalled": "restored_baseline_20260706_190021.pcapng",
    "passing": "restored_baseline2_20260706_190324.pcapng",
}

plt.rcParams.update({
    "font.size": 8,
    "axes.titlesize": 8.5,
    "axes.labelsize": 8,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "pdf.fonttype": 42,  # embed TrueType (required by IEEE/ACM)
})

C_BOARD = "#0072B2"   # colorblind-safe blue
C_HOST = "#D55E00"    # colorblind-safe vermillion
C_MARK = "#009E73"    # green
C_GRAY = "#777777"
C_CNT = "#555555"


def tshark_rows(pcap, yfilter, fields=("frame.time_relative",)):
    cmd = ["tshark", "-r", os.path.join(PCAP_DIR, pcap), "-Y", yfilter,
           "-T", "fields"]
    for f in fields:
        cmd += ["-e", f]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return [ln.split("\t") for ln in out.splitlines() if ln.split("\t")[0]]


def times(pcap, yfilter):
    return [float(r[0]) for r in tshark_rows(pcap, yfilter)]


def events(pcap):
    ev = {}
    ev["spdp_board"] = times(pcap, f'ip.src == {BOARD} && rtps.sm.wrEntityId == 0x000100c2')
    ev["sedp_host"] = times(pcap, f'ip.src == {HOST} && rtps.sm.id == 0x15 && '
                                  '(rtps.sm.wrEntityId == 0x000003c2 || rtps.sm.wrEntityId == 0x000004c2)')
    ev["sedp_board"] = times(pcap, f'ip.src == {BOARD} && rtps.sm.id == 0x15 && '
                                   '(rtps.sm.wrEntityId == 0x000003c2 || rtps.sm.wrEntityId == 0x000004c2)')
    ev["hb_host"] = times(pcap, f'ip.src == {HOST} && rtps.sm.id == 0x07')
    ev["an_board"] = times(pcap, f'ip.src == {BOARD} && rtps.sm.id == 0x06')
    userq = ('rtps.sm.id == 0x15 && (rtps.sm.wrEntityId.entityKind == 0x02 || '
             'rtps.sm.wrEntityId.entityKind == 0x03)')
    ev["user_board"] = times(pcap, f'ip.src == {BOARD} && ' + userq)
    ev["user_host"] = times(pcap, f'ip.src == {HOST} && ' + userq)
    return ev


def sedp_acknack_counts(pcap):
    """(time, max count) for the board's SEDP-builtin-reader ACKNACKs only."""
    rows = tshark_rows(
        pcap,
        f'ip.src == {BOARD} && rtps.sm.id == 0x06 && '
        '(rtps.sm.rdEntityId == 0x000003c7 || rtps.sm.rdEntityId == 0x000004c7)',
        ("frame.time_relative", "rtps.acknack.count"))
    pts = []
    for r in rows:
        if len(r) > 1 and r[1]:
            vals = [int(v) for v in r[1].split(",") if v]
            if vals:
                pts.append((float(r[0]), max(vals)))
    return pts


def reboot_time(ev):
    """Board reboot = first >3 s gap in SPDP announcements starting before 20 s."""
    t = sorted(ev["spdp_board"])
    for i in range(len(t) - 1):
        if t[i + 1] - t[i] > 3.0 and t[i] < 20.0:
            return t[i + 1]
    return t[0] if t else 0.0


def raster(ax, lanes, xlim):
    for i, (label, ts, color) in enumerate(lanes):
        y = len(lanes) - 1 - i
        ts = [t for t in ts if xlim[0] <= t <= xlim[1]]
        ax.plot(ts, [y] * len(ts), "|", markersize=7, markeredgewidth=1.1,
                color=color, zorder=3)
    ax.set_yticks(range(len(lanes)))
    ax.set_yticklabels([l[0] for l in reversed(lanes)])
    ax.set_ylim(-0.6, len(lanes) - 0.4)
    ax.set_xlim(*xlim)
    ax.grid(axis="x", linewidth=0.3, alpha=0.4)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def shift(ts, t0):
    return [t - t0 for t in ts]


# ---------------------------------------------------------------- figure 1
def fig_discovery():
    ev = events(PCAPS["passing"])
    t0 = reboot_time(ev)
    first_user = min([t for t in ev["user_board"] if t > t0], default=t0 + 12) - t0
    first_echo = min([t for t in ev["user_host"] if t > t0], default=t0 + 12) - t0
    xlim = (-2.0, max(first_user, first_echo) + 3.0)

    fig, ax = plt.subplots(figsize=(7.0, 2.4))
    lanes = [
        ("SPDP DATA(p) — board", shift(ev["spdp_board"], t0), C_BOARD),
        ("SEDP DATA(w/r) — host", shift(ev["sedp_host"], t0), C_HOST),
        ("SEDP DATA(w/r) — board", shift(ev["sedp_board"], t0), C_BOARD),
        ("HEARTBEAT — host", shift(ev["hb_host"], t0), C_HOST),
        ("ACKNACK — board", shift(ev["an_board"], t0), C_BOARD),
        ("user DATA — board", shift(ev["user_board"], t0), C_BOARD),
        ("echo DATA — host", shift(ev["user_host"], t0), C_HOST),
    ]
    raster(ax, lanes, xlim)
    ax.axvline(0, color=C_GRAY, linestyle="--", linewidth=0.9)
    ax.text(0.15, len(lanes) - 1.05, "board\nreboot", color=C_GRAY, va="top")
    ax.axvline(first_user, color=C_MARK, linestyle=":", linewidth=0.9)
    ax.text(first_user - 0.3, 0.75,
            f"first user sample\n+{first_user:.1f} s after reboot",
            color=C_MARK, va="bottom", ha="right")
    ax.set_xlabel("time after board reboot (s)")
    ax.set_title("Post-reset discovery handshake: ESP32 (embeddedRTPS) ↔ ROS 2 host (Fast DDS)",
                 pad=10)
    fig.tight_layout()
    save(fig, "fig_discovery_timeline")


# ---------------------------------------------------------------- figure 2
def fig_deadlock():
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 3.9))
    for ax, key, title in (
            (axes[0], "stalled",
             "(a) Stalled run: SEDP ACKNACKs never answered — endpoint matching deadlocks"),
            (axes[1], "passing",
             "(b) Passing run: SEDP data re-served, matching completes, user data flows")):
        ev = events(PCAPS[key])
        t0 = reboot_time(ev)
        xlim = (-4, 58)
        lanes = [
            ("HEARTBEAT — host", shift(ev["hb_host"], t0), C_HOST),
            ("ACKNACK — board", shift(ev["an_board"], t0), C_BOARD),
            ("SEDP DATA — host", shift(ev["sedp_host"], t0), C_HOST),
            ("user DATA", shift(sorted(ev["user_board"] + ev["user_host"]), t0), C_MARK),
        ]
        raster(ax, lanes, xlim)
        ax.axvline(0, color=C_GRAY, linestyle="--", linewidth=0.9)
        ax.set_title(title, loc="left", pad=4)

        pts = [(t - t0, c) for (t, c) in sedp_acknack_counts(PCAPS[key])]
        ax2 = ax.twinx()
        ax2.plot([p[0] for p in pts], [p[1] for p in pts], ".",
                 markersize=2.6, color=C_CNT, alpha=0.85)
        ax2.set_xlim(*xlim)
        ax2.set_ylabel("SEDP ACKNACK\ncount", fontsize=7, color=C_CNT)
        ax2.tick_params(axis="y", labelsize=6, colors=C_CNT)
        ax2.spines["top"].set_visible(False)

        if key == "stalled":
            ax2.text(30, 4, "SEDP ACKNACK count restarts at 1,\n"
                            "climbs for 60 s requesting data\nthat is never served",
                     color=C_CNT, ha="left", va="bottom")
            ax.text(5, 0.55, "no SEDP data re-served\nafter reboot → never matched",
                    color=C_HOST, va="top")
        else:
            first_user = min([t - t0 for t in ev["user_board"] + ev["user_host"]
                              if t > t0], default=None)
            if first_user:
                ax.annotate(f"user data +{first_user:.1f} s after reboot",
                            xy=(first_user + 1.5, 0.42), color=C_MARK)
            ax.text(1.0, 1.38, "SEDP re-served", color=C_HOST)
    axes[1].set_xlabel("time after board reboot (s)")
    fig.tight_layout(h_pad=1.6)
    save(fig, "fig_discovery_deadlock")


# ---------------------------------------------------------------- figure 3
def fig_heartbeat():
    fig, ax = plt.subplots(figsize=(3.5, 2.3))
    for key, label, color in (
            ("baseline", "HB period 4000 ms (default)", C_BOARD),
            ("expA", "HB period 1000 ms", C_HOST)):
        t0 = reboot_time(events(PCAPS[key]))
        t = sorted(times(PCAPS[key], f'ip.src == {BOARD} && rtps.sm.id == 0x07'))
        t = [x - t0 for x in t if 0 <= x - t0 <= 50]
        ax.step(t, range(1, len(t) + 1), color=color, linewidth=1.2,
                label=f"{label}: {len(t)} in 50 s")
    ax.set_xlabel("time after board reboot (s)")
    ax.set_ylabel("cumulative HEARTBEATs\nsent by ESP32")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(linewidth=0.3, alpha=0.4)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    save(fig, "fig_heartbeat_period")


def save(fig, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT_DIR, f"{name}.{ext}"), bbox_inches="tight")
    plt.close(fig)
    print(f"wrote docs/figures/{name}.pdf/.png")


def main():
    missing = [f for f in PCAPS.values()
               if not os.path.isfile(os.path.join(PCAP_DIR, f))]
    if missing:
        sys.exit(f"missing captures in {PCAP_DIR}: {missing}\n"
                 "These are local-only evidence files; see docs/benchmark/"
                 "RTPS_PARAMETER_EXPERIMENT.md for how they were recorded.")
    fig_discovery()
    fig_deadlock()
    fig_heartbeat()
    print("ALL_FIGURES_DONE")


if __name__ == "__main__":
    main()
