#!/usr/bin/env python3
"""
Dipole length sweep using the LibreVNA-GUI SCPI server.

Asks once for a target frequency, a sweep range and a frequency step
(default 1 MHz), then repeatedly asks for
the dipole length, takes a single S11 sweep, and saves to this script's folder:

  dipole_<len>_<time>_S11_mag.png    |S11| (dB) vs frequency
  dipole_<len>_<time>_S11_smith.png  S11 on a Smith chart
  dipole_<len>_<time>.csv            full sweep (freq, Re/Im, dB, phase, Z, VSWR)
  dipole_<len>_<time>.s1p            Touchstone file exported by the GUI
  dipole_summary.csv                 one row per measurement (resonance, S11 at target, ...)

Before running:
  1. Start LibreVNA-GUI and connect the LibreVNA.
  2. Make sure the SCPI server is enabled (Preferences > General, port 19542 by default).
  3. Calibrate port 1 (SOL) over your sweep range at the reference plane of the antenna feed.

Type "stop" (or q / quit / exit) at the length prompt, or press Ctrl+C, to end.
"""

import argparse
import csv
import os
import re
import socket
import sys
import time
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
STOP_WORDS = {"stop", "s", "q", "quit", "exit", "done"}
Z0 = 50.0


class LibreVNA:
    """Minimal SCPI client for the LibreVNA-GUI TCP server."""

    def __init__(self, host="localhost", port=19542, timeout=5.0):
        try:
            self.sock = socket.create_connection((host, port), timeout=timeout)
        except OSError:
            raise SystemExit(
                f"Could not connect to LibreVNA-GUI at {host}:{port}.\n"
                "Make sure the GUI is running and its SCPI server is enabled.")
        self.sock.settimeout(timeout)
        self.buf = b""

    def close(self):
        self.sock.close()

    def _readline(self, timeout):
        self.sock.settimeout(timeout)
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("LibreVNA-GUI closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode().strip()

    def query(self, q, timeout=5.0):
        self.sock.sendall(q.encode() + b"\n")
        return self._readline(timeout)

    def cmd(self, c, timeout=5.0):
        self.sock.sendall(c.encode() + b"\n")
        status = int(self.query("*ESR?", timeout))
        if status & 0x3C:
            raise RuntimeError(f"SCPI command failed ({c!r}), *ESR? = {status}")


# ---------------------------------------------------------------- input helpers

def parse_freq(text, default_unit="MHz"):
    """'2.4G', '2400', '2400 MHz', '915e6 Hz' -> Hz. Bare numbers use default_unit."""
    m = re.fullmatch(r"\s*([0-9.]+(?:e[+-]?\d+)?)\s*([kmg]?)(?:hz)?\s*", text.lower())
    if not m:
        raise ValueError(f"can't read frequency {text!r}")
    value, prefix = float(m.group(1)), m.group(2)
    if not prefix and not text.lower().strip().endswith("hz"):
        prefix = default_unit[0].lower()
    return value * {"": 1, "k": 1e3, "m": 1e6, "g": 1e9}[prefix]


def ask(prompt, parse):
    while True:
        try:
            return parse(input(prompt))
        except ValueError as e:
            print(f"  -> {e}. Try again.")


def fmt_freq(f):
    if f >= 1e9:
        return f"{f / 1e9:.4g} GHz"
    if f >= 1e6:
        return f"{f / 1e6:.4g} MHz"
    return f"{f / 1e3:.4g} kHz"


def length_tag(length, unit):
    # 12.5 cm -> "L12p5cm" (no dots in filenames)
    return "L" + f"{length:g}".replace(".", "p").replace("-", "m") + unit


# ---------------------------------------------------------------- measurement

def setup_sweep(vna, start, stop, points):
    vna.cmd(":DEV:MODE VNA")
    vna.cmd(":VNA:SWEEP FREQUENCY")
    vna.cmd(":VNA:SWEEPTYPE LIN")
    vna.cmd(f":VNA:FREQuency:START {start:.0f}")
    vna.cmd(f":VNA:FREQuency:STOP {stop:.0f}")
    vna.cmd(f":VNA:ACQ:POINTS {points}")
    actual = int(float(vna.query(":VNA:ACQ:POINTS?")))
    if actual != points:
        print(f"WARNING: GUI is using {actual} points instead of {points}; "
              f"step is {fmt_freq((stop - start) / (actual - 1))}.")
    traces = vna.query(":VNA:TRACE:LIST?").split(",")
    if "S11" not in traces:
        raise SystemExit(f"No trace named S11 in the GUI (traces: {traces}). "
                         "Add an S11 trace in LibreVNA-GUI and rerun.")


def single_sweep(vna, timeout=120):
    vna.cmd(":VNA:ACQ:SINGLE TRUE")  # always triggers a fresh sweep
    t_end = time.time() + timeout
    while vna.query(":VNA:ACQ:FIN?") != "TRUE":
        if time.time() > t_end:
            raise RuntimeError("Sweep did not finish in time")
        time.sleep(0.1)
    raw = vna.query(":VNA:TRACE:DATA? S11", timeout=30)
    vals = [float(v) for v in raw.replace("[", "").replace("]", "").split(",") if v]
    arr = np.array(vals).reshape(-1, 3)
    freq, s11 = arr[:, 0], arr[:, 1] + 1j * arr[:, 2]
    return freq, s11, read_touchstone(vna)


def read_touchstone(vna):
    # The GUI answers with a multi-line Touchstone file terminated by an empty line
    first = vna.query(":VNA:TRACE:TOUCHSTONE? S11", timeout=30)
    if not first.startswith("#"):
        raise RuntimeError(f"Touchstone export failed: {first!r}")
    lines = [first]
    while True:
        line = vna._readline(timeout=30)
        if not line:
            return "\n".join(lines) + "\n"
        lines.append(line)


# ---------------------------------------------------------------- saving

def save_csv(path, freq, s11):
    z = Z0 * (1 + s11) / (1 - s11)
    mag = np.abs(s11)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Frequency_Hz", "S11_real", "S11_imag", "S11_mag_dB",
                    "S11_phase_deg", "Z_real_ohm", "Z_imag_ohm", "VSWR"])
        for row in zip(freq, s11.real, s11.imag, 20 * np.log10(mag),
                       np.degrees(np.angle(s11)), z.real, z.imag,
                       (1 + mag) / np.maximum(1 - mag, 1e-12)):
            w.writerow([f"{row[0]:.0f}"] + [f"{v:.6g}" for v in row[1:]])


# ---- markers: same readouts as the LibreVNA-GUI marker info panel

MARKER_COLORS = ("tab:green", "tab:red")


def si(value, unit, digits=4):
    """Engineering-prefix formatting, e.g. si(-7.32e-12, 'F') -> '-7.32 pF'."""
    if not np.isfinite(value):
        return f"NaN {unit}"
    prefixes = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"),
                (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f")]
    for scale, p in prefixes:
        if abs(value) >= scale:
            break
    return f"{value / scale:.{digits}g} {p}{unit}"


def group_delay(freq, s11, i, samples=5):
    # Same method as the GUI: linear fit of unwrapped phase over 5 samples
    half = samples // 2
    if len(freq) < samples:
        return float("nan")
    i = min(max(i, half), len(freq) - half - 1)
    ph = np.unwrap(np.angle(s11[i - half:i + half + 1]))
    slope = np.polyfit(np.arange(samples), ph, 1)[0]
    return -slope / (2 * np.pi * (freq[i] - freq[i - 1]))


def make_markers(freq, s11, target):
    """Marker 1 at minimum |S11| (resonance); marker 2 at the target frequency."""
    i_min = int(np.argmin(np.abs(s11)))
    markers = [dict(num=1, label="min |S11|", f=freq[i_min], s=s11[i_min],
                    tau=group_delay(freq, s11, i_min))]
    if freq[0] <= target <= freq[-1]:
        i_t = int(np.searchsorted(freq, target))
        s_t = np.interp(target, freq, s11.real) + 1j * np.interp(target, freq, s11.imag)
        markers.append(dict(num=2, label="target", f=target, s=s_t,
                            tau=group_delay(freq, s11, min(i_t, len(freq) - 1))))
    for m, color in zip(markers, MARKER_COLORS):
        m["color"] = color
    return markers


def marker_lines(m):
    f, s = m["f"], m["s"]
    z = Z0 * (1 + s) / (1 - s)
    w = 2 * np.pi * f
    db = 20 * np.log10(abs(s))
    vswr = (1 + abs(s)) / (1 - abs(s)) if abs(s) < 1 else float("nan")
    return [
        f"{f / 1e9:.5f} GHz",
        f"{db:.2f} dB",
        f"{db:.2f} dB / {np.degrees(np.angle(s)):.2f}°",
        f"{s.real:.5f} {'+' if s.imag >= 0 else '-'} {abs(s.imag):.5f}j",
        f"{z.real:.3f} Ω {'+' if z.imag >= 0 else '-'} {abs(z.imag):.3f}j Ω",
        f"VSWR: {vswr:.5g}:1",
        si(z.real, "Ω"),
        si(-1 / (w * z.imag) if z.imag else float("nan"), "F", 3),
        si(z.imag / w, "H"),
        f"Q: {abs(z.imag) / z.real:.3g}",
        "τg: " + si(m["tau"], "s"),
    ]


def draw_info_panel(fig, markers, x0=0.75):
    """Writes each marker's readout down the right side of the figure."""
    y = 0.90
    for m in markers:
        fig.text(x0, y, f" {m['num']} ", color="white", fontsize=10, weight="bold",
                 va="top", bbox=dict(boxstyle="round,pad=0.25", fc=m["color"], ec="none"))
        fig.text(x0 + 0.04, y, m["label"], color=m["color"], fontsize=9,
                 style="italic", va="top")
        y -= 0.045
        for line in marker_lines(m):
            fig.text(x0, y, line, color=m["color"], fontsize=9, va="top")
            y -= 0.033
        y -= 0.03


def plot_mag(path, freq, s11, target, title):
    db = 20 * np.log10(np.abs(s11))
    markers = make_markers(freq, s11, target)
    fig = plt.figure(figsize=(12, 6))
    ax = fig.add_axes([0.07, 0.10, 0.63, 0.80])
    ax.plot(freq / 1e6, db, lw=1.5, color="tab:blue", label="|S11|")
    ax.axhline(-10, color="gray", ls=":", lw=1, label="-10 dB")
    ax.axvline(target / 1e6, color="tab:red", ls="--", lw=0.8, alpha=0.6,
               label=f"Target {fmt_freq(target)}")
    for m in markers:
        y = 20 * np.log10(abs(m["s"]))
        ax.plot(m["f"] / 1e6, y, "v", ms=11, color=m["color"])
        ax.annotate(str(m["num"]), (m["f"] / 1e6, y), xytext=(0, 9),
                    textcoords="offset points", ha="center", color=m["color"],
                    weight="bold")
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("|S11| (dB)")
    ax.set_xlim(freq[0] / 1e6, freq[-1] / 1e6)
    ax.set_title(title)
    ax.grid(True, alpha=0.4)
    ax.legend(loc="lower left")
    draw_info_panel(fig, markers)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def draw_smith_grid(ax):
    t = np.linspace(0, 2 * np.pi, 400)
    ax.plot(np.cos(t), np.sin(t), color="black", lw=1)
    ax.plot([-1, 1], [0, 0], color="gray", lw=0.6)
    for r in (0.2, 0.5, 1, 2, 5):
        c, rad = r / (1 + r), 1 / (1 + r)
        ax.plot(c + rad * np.cos(t), rad * np.sin(t), color="gray", lw=0.6)
        ax.text(c - rad + 0.01, 0.02, f"{r:g}", fontsize=7, color="gray")
    for x in (0.2, 0.5, 1, 2, 5):
        for sgn in (1, -1):
            # constant-reactance arc, clipped to the unit circle
            zr = np.concatenate([np.linspace(0, 1, 200), np.logspace(0, 3, 200)])
            g = (zr + 1j * sgn * x - 1) / (zr + 1j * sgn * x + 1)
            ax.plot(g.real, g.imag, color="gray", lw=0.6)
        g = (1j * x - 1) / (1j * x + 1)
        ax.text(g.real * 1.07, g.imag * 1.07, f"{x:g}j", fontsize=7,
                color="gray", ha="center", va="center")
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.set_aspect("equal")
    ax.axis("off")


def plot_smith(path, freq, s11, target, title):
    markers = make_markers(freq, s11, target)
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_axes([0.02, 0.07, 0.68, 0.85])
    draw_smith_grid(ax)
    ax.plot(s11.real, s11.imag, lw=1.5, color="tab:blue", label="S11")
    ax.plot(s11.real[0], s11.imag[0], "^", color="tab:blue",
            label=f"Start {fmt_freq(freq[0])}")
    ax.plot(s11.real[-1], s11.imag[-1], "s", color="tab:blue",
            label=f"Stop {fmt_freq(freq[-1])}")
    for m in markers:
        ax.plot(m["s"].real, m["s"].imag, "v", ms=11, color=m["color"])
        ax.annotate(str(m["num"]), (m["s"].real, m["s"].imag), xytext=(0, 9),
                    textcoords="offset points", ha="center", color=m["color"],
                    weight="bold")
    ax.set_title(title)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=3, fontsize=8, frameon=False)
    draw_info_panel(fig, markers)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def append_summary(path, length, unit, base, freq, s11, target):
    db = 20 * np.log10(np.abs(s11))
    i_min = int(np.argmin(db))
    g = np.interp(target, freq, s11.real) + 1j * np.interp(target, freq, s11.imag)
    z = Z0 * (1 + g) / (1 - g)
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["Timestamp", f"Length_{unit}", "Resonance_Hz",
                        "S11_min_dB", "Target_Hz", "S11_at_target_dB",
                        "Z_real_at_target_ohm", "Z_imag_at_target_ohm", "Files"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), f"{length:g}",
                    f"{freq[i_min]:.0f}", f"{db[i_min]:.2f}", f"{target:.0f}",
                    f"{20 * np.log10(abs(g)):.2f}", f"{z.real:.2f}",
                    f"{z.imag:.2f}", base])
    return freq[i_min], db[i_min], 20 * np.log10(abs(g))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=19542)
    ap.add_argument("--step", default="1M",
                    help="default frequency step offered at the prompt (default 1M = 1 MHz)")
    ap.add_argument("--unit", default="cm", help="length unit for the prompt (default cm)")
    args = ap.parse_args()

    vna = LibreVNA(args.host, args.port)
    print("Connected to", vna.query("*IDN?"))
    dev = vna.query(":DEV:CONN?")
    if dev == "Not connected":
        raise SystemExit("LibreVNA-GUI is not connected to a VNA. Connect it in the GUI first.")
    print("Device:", dev)
    cal = vna.query(":VNA:CAL:ACTIVE?")
    print("Active calibration:", cal)
    if cal.strip().lower() in ("", "none"):
        print("WARNING: no calibration is active - results will include cable/port errors.")

    print("\nFrequencies: bare numbers are MHz; you can also type e.g. 2.4G or 915M.")
    target = ask("Target frequency: ", parse_freq)
    while True:
        start = ask("Sweep start frequency: ", parse_freq)
        stop = ask("Sweep stop frequency: ", parse_freq)
        if stop > start:
            break
        print("  -> stop must be greater than start.")
    if not start <= target <= stop:
        print("Note: target frequency is outside the sweep range.")

    try:
        max_points = int(float(vna.query(":DEV:INF:LIM:MAXP?")))
    except (ValueError, OSError):
        max_points = None
    default_step = parse_freq(args.step)

    def parse_step(text):
        step = parse_freq(text) if text.strip() else default_step
        if step <= 0:
            raise ValueError("step must be positive")
        points = int(round((stop - start) / step)) + 1
        if points < 2:
            raise ValueError("step is larger than the sweep range")
        if max_points and points > max_points:
            min_step = (stop - start) / (max_points - 1)
            raise ValueError(f"{points} points needed but the VNA allows at most "
                             f"{max_points}; use a step of at least {fmt_freq(min_step)} "
                             "or a narrower range")
        return step, points

    step, points = ask(f"Frequency step [Enter = {fmt_freq(default_step)}]: ", parse_step)
    # keep the step exact by snapping stop onto the start + n*step grid
    aligned_stop = start + (points - 1) * step
    if abs(aligned_stop - stop) > 0.5:
        print(f"Note: stop adjusted to {fmt_freq(aligned_stop)} to fit {fmt_freq(step)} steps.")
    stop = aligned_stop

    setup_sweep(vna, start, stop, points)
    print(f"\nSweeping S11 from {fmt_freq(start)} to {fmt_freq(stop)} in "
          f"{fmt_freq(step)} steps ({points} points). Output folder: {OUT_DIR}")
    summary = os.path.join(OUT_DIR, "dipole_summary.csv")

    def parse_length(text):
        text = text.strip().lower()
        if text in STOP_WORDS:
            return None
        v = float(text.replace(args.unit, "").strip())
        if v <= 0:
            raise ValueError("length must be positive")
        return v

    try:
        while True:
            length = ask(f"\nDipole length in {args.unit} (or 'stop'): ", parse_length)
            if length is None:
                break
            print("  Measuring...")
            freq, s11, ts = single_sweep(vna)

            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            base = f"dipole_{length_tag(length, args.unit)}_{stamp}"
            title = (f"Dipole L = {length:g} {args.unit}  |  S11  "
                     f"{fmt_freq(start)} - {fmt_freq(stop)}")
            p = lambda suffix: os.path.join(OUT_DIR, base + suffix)

            save_csv(p(".csv"), freq, s11)
            with open(p(".s1p"), "w") as f:
                f.write(f"! Dipole length {length:g} {args.unit}, measured {stamp}\n")
                f.write(ts)
            plot_mag(p("_S11_mag.png"), freq, s11, target, title)
            plot_smith(p("_S11_smith.png"), freq, s11, target, title)
            f_res, db_min, db_t = append_summary(summary, length, args.unit,
                                                 base, freq, s11, target)

            print(f"  Resonance (min |S11|): {fmt_freq(f_res)} at {db_min:.1f} dB; "
                  f"|S11| at target {fmt_freq(target)}: {db_t:.1f} dB")
            print(f"  Saved {base}.csv/.s1p/_S11_mag.png/_S11_smith.png")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        vna.close()
    print("Done. Summary of all lengths:", summary)


if __name__ == "__main__":
    main()
