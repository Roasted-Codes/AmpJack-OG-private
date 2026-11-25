#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GIP full-speed conformance checker (host-only, read-only, no privileged mutation).

Owned by worker 06 (ogxbox/work/06-alternatives/). Complements worker 01's raw
descriptor-capture helper: this one answers ONE specific question — is the
"all GIP high speed" claim true? It checks Microsoft's MS-GIPUSB rules for the
GIP *data* interface against a data source, and reports bus speed.

Two parts, clearly separated so no synthetic fixture is ever mistaken for a
live capture:

  PART A — live scan (VERIFIED, real execution): reads Linux sysfs
  (/sys/bus/usb/devices/<dev>/speed|version|idVendor|idProduct|bNumInterfaces)
  and `lsusb`. Root-only. Reports each device's bus speed vs bcdUSB, and whether
  any device looks like a GIP/Xbox-One pad (vendor 0x045E). Does NOT claim to
  prove real-hardware enumeration of a controller on an OHCI host.

  PART B — conformance rules (synthetic fixtures, labelled): a pure function
  checks MS-GIPUSB's full-speed data-interface requirements against a descriptor
  dict. Fixtures are SYNTHETIC and are NOT USB captures.

References (MS-GIPUSB):
  - GIP Data Interrupt IN endpoint descriptor, Table 11, section 2.2.9.1.2:
    https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-gipusb/e77f6af7-481d-4d86-b72a-848cb233e3d6
      * wMaxPacketSize field D12..11 "MUST be zero for Full Speed devices"
      * bInterval "MUST be >= 4" (milliseconds) for full speed
  - MS-GIPUSB PDF: "USB GIP devices MUST respond to a request for the
    device_qualifier descriptor with a request error (STALL) to indicate that this
    is a Full-Speed (12 Mbps) device and not a High-Speed (480 Mbps) device ..."
    https://winprotocoldoc.z19.web.core.windows.net/MS-GIPUSB/%5BMS-GIPUSB%5D.pdf
      * Data Interface (USB Interface #0): one 64-byte interrupt IN + one 64-byte
        interrupt OUT, class/subclass/protocol FF/47/D0.
  - UHCI/OHCI full speed only: https://xboxdevwiki.net/USB ("OHCI supports USB
    devices up to USB 1.1 12Mbit/s").
"""

import os
import subprocess
import sys

SYSUSB = "/sys/bus/usb/devices"

# bcdUSB versions we know how to classify
SPEED_NAMES = {
    "1.5": "Low-Speed (1.5 Mbps)",
    "12": "Full-Speed (12 Mbps)",
    "480": "High-Speed (480 Mbps)",
    "5000": "SuperSpeed (5 Gbps)",
    "10000": "SuperSpeed+ (10 Gbps)",
    "20000": "SuperSpeed+ (20 Gbps)",
}

# Known Xbox One / Series GIP pad vendor = Microsoft 0x045E; other GIP vendors
# (SCUF 0x2E95, PowerA, PDP, 8BitDo) are NOT all 0x045E, so this is a heuristic,
# not a full detector. A definitive test still needs the interface descriptor.
GIP_EXAMPLE_VIDS = {"045e", "2e95"}


def read_sysfs_text(path):
    try:
        with open(path, "r", encoding="ascii", errors="replace") as f:
            return f.read().strip()
    except (OSError, IOError):
        return None


def live_scan():
    """Part A: walk /sys/bus/usb/devices for stable bus-speed facts. Read-only."""
    rows = []
    if not os.path.isdir(SYSUSB):
        return rows, "no sysfs under " + SYSUSB
    for name in sorted(os.listdir(SYSUSB)):
        d = os.path.join(SYSUSB, name)
        speed = read_sysfs_text(os.path.join(d, "speed"))
        if not speed:
            continue  # interfaces (e.g. "1-7:1.0") live under device names, skip
        rows.append({
            "dev": name,
            "speed_mbps": speed,
            "version": read_sysfs_text(os.path.join(d, "version")),
            "idVendor": read_sysfs_text(os.path.join(d, "idVendor")),
            "idProduct": read_sysfs_text(os.path.join(d, "idProduct")),
            "bNumInterfaces": read_sysfs_text(os.path.join(d, "bNumInterfaces")),
            "product": read_sysfs_text(os.path.join(d, "product")),
            "manufacturer": read_sysfs_text(os.path.join(d, "manufacturer")),
        })
    return rows, None


def check_gip_full_speed(desc):
    """
    Part B: pure conformance check of the MS-GIPUSB *data interface* (input-only
    milestone). `desc` is a dict with device-level and data-interface facts.
    Returns a list of (severity, message). Does no I/O, makes no hardware claim.
    """
    notes = []
    device_speed_mbps = desc.get("device_speed_mbps")
    if device_speed_mbps is not None:
        if device_speed_mbps in ("480", "5000", "10000", "20000"):
            notes.append(("FAIL", "device enumerating at %s Mbps — a GIP device "
                         "MUST be Full-Speed/12 Mbps (device_qualifier STALL)" % device_speed_mbps))
        elif device_speed_mbps in ("12",):
            notes.append(("OK", "device at 12 Mbps (Full-Speed) — consistent with "
                         "MS-GIPUSB full-speed requirement"))
        else:
            notes.append(("WARN", "unexpected speed %s" % device_speed_mbps))

    cls = desc.get("iface_class")
    sub = desc.get("iface_subclass")
    proto = desc.get("iface_protocol")
    if (cls, sub, proto) != (0xFF, 0x47, 0xD0):
        notes.append(("FAIL", "data interface class/subclass/protocol = %s/%s/%s; "
                      "MS-GIPUSB requires FF/47/D0 (got %s)" %
                      (cls, sub, proto, (cls, sub, proto))))
    else:
        notes.append(("OK", "data interface FF/47/D0 (GIP)"))

    if desc.get("interrupt_in_wMaxPacketSize") != 64:
        notes.append(("FAIL", "interrupt IN wMaxPacketSize != 64 (got %s); "
                      "MS-GIPUSB requires a 64-byte-capable interrupt IN" %
                      desc.get("interrupt_in_wMaxPacketSize")))
    else:
        notes.append(("OK", "interrupt IN wMaxPacketSize 64 (matches MS-GIPUSB Table 11)"))
    if desc.get("interrupt_out_wMaxPacketSize") != 64:
        notes.append(("FAIL", "interrupt OUT wMaxPacketSize != 64 (got %s); "
                      "MS-GIPUSB requires a 64-byte-capable interrupt OUT" %
                      desc.get("interrupt_out_wMaxPacketSize")))
    else:
        notes.append(("OK", "interrupt OUT wMaxPacketSize 64 (matches MS-GIPUSB Table 11)"))

    interval_ms = desc.get("interrupt_in_bInterval_ms")
    if interval_ms is None:
        pass
    elif interval_ms < 4:
        notes.append(("FAIL", "interrupt IN bInterval = %s ms (< 4 ms); MS-GIPUSB "
                      "Table 11 requires >= 4 ms at Full-Speed" % interval_ms))
    else:
        notes.append(("OK", "interrupt IN bInterval %s ms (>= 4 ms, full-speed scope)" % interval_ms))

    # NAK/poll: interrupt transfers are fine on OHCI at full speed; the packet
    # cap of 64 bytes is already the OHCI full-speed upper bound, so no extra note.
    return notes


SYNTHETIC = [
    # SYNTHETIC FIXTURE — NOT a USB capture.
    {
        "label": "synthetic conforming GIP pad (full-speed)",
        "device_speed_mbps": "12",
        "iface_class": 0xFF, "iface_subclass": 0x47, "iface_protocol": 0xD0,
        "interrupt_in_wMaxPacketSize": 64,
        "interrupt_out_wMaxPacketSize": 64,
        "interrupt_in_bInterval_ms": 4,
    },
    {
        "label": "synthetic GIP pad at high-speed (contradicts MS-GIPUSB)",
        "device_speed_mbps": "480",
        "iface_class": 0xFF, "iface_subclass": 0x47, "iface_protocol": 0xD0,
        "interrupt_in_wMaxPacketSize": 64,
        "interrupt_out_wMaxPacketSize": 64,
        "interrupt_in_bInterval_ms": 4,
    },
    {
        "label": "synthetic GIP pad with wrong endpoint size",
        "device_speed_mbps": "12",
        "iface_class": 0xFF, "iface_subclass": 0x47, "iface_protocol": 0xD0,
        "interrupt_in_wMaxPacketSize": 32,
        "interrupt_out_wMaxPacketSize": 64,
        "interrupt_in_bInterval_ms": 2,
    },
]


def main():
    print("=== PART A — live host scan (sysfs, read-only, root hubs + devices) ===")
    print("scope: THIS x86_64 host's xHCI controllers. Not an OG Xbox, not an OHCI")
    print("host, and NOT proof a pad enumerates on an Xbox. bcdUSB 2.00 != high speed.")
    rows, err = live_scan()
    if err:
        print("ERROR:", err)
    else:
        print("%-12s %-7s %-8s %-10s %-10s %s" %
              ("dev", "speed", "version", "vendor", "product", "name"))
        for r in rows:
            print("%-12s %-7s %-8s %-10s %-10s %s%s" %
                  (r["dev"], r["speed_mbps"], r["version"] or "-",
                   r["idVendor"] or "-", r["idProduct"] or "-",
                   (r["product"] or r["manufacturer"] or "?").strip(),
                   ("  <-- GIP/Xbox vendor heurisin" if r["idVendor"] in GIP_EXAMPLE_VIDS else "")))

    print()
    print("bcdUSB vs actual speed (the common confusion), from this host:")
    seen = set()
    for r in rows:
        v = r["version"] or "-"
        s = r["speed_mbps"] or "-"
        key = (v, s)
        if key in seen:
            continue
        seen.add(key)
        if v == "2.00" and s == "12":
            print("  VERIFIED on this host: version 2.00 but speed 12 Mbps (full-speed): %s" %
                  r["dev"])
    print("  (full-speed-only OHCI therefore sees any device that negotiated full speed,")
    print("   regardless of its bcdUSB==2.00 device descriptor.)")

    print()
    print("=== PART B — MS-GIPUSB data-interface conformance (SYNTHETIC fixtures) ===")
    print("These fixtures are SYNTHETIC parser inputs, NOT USB captures.")
    for fx in SYNTHETIC:
        print("--- %s ---" % fx["label"])
        for sev, msg in check_gip_full_speed(fx):
            print("  [%s] %s" % (sev, msg))
        # overall verdict = not FAIL
        fails = [n for n in check_gip_full_speed(fx) if n[0] == "FAIL"]
        print("  verdict: %s" % ("CONFORMING" if not fails else "NON-CONFORMING"))

    # GIP-candidate detection on this host
    cand = [r for r in rows if r["idVendor"] in GIP_EXAMPLE_VIDS]
    print()
    print("=== GIP/Xbox-One pad present on this host? ===")
    print("  %s" % ("yes: " + ", ".join(r["dev"] for r in cand) if cand
                    else "no (no 0x045E/0x2E95 vendor device seen). "
                    "Consistent with 'no pad at dispatch'."))


if __name__ == "__main__":
    main()
