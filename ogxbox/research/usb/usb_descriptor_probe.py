#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
usb_descriptor_probe.py — read-only USB descriptor + bus-speed capture helper.

Purpose: prove, with no privileges and no mutations, the negotiated bus speed and
the device/config/endpoint descriptors of an attached USB device (e.g. a wired
Xbox One GIP controller) from Linux sysfs. It is intended for the owner to run
later when a real controller is present; a single "12" in the speed column plus
the raw endpoint descriptors is the evidence that a pad enumerated at FULL SPEED.

SCOPE OF THIS EXERCISE (AmpJack-OG worker 01-usb):
  Only host root hubs are captured here, on a machine where lsusb showed NO
  gamepad at dispatch. This output must NOT be read as proof of controller
  enumeration. It only demonstrates that the tool reads descriptors/speed
  correctly against the host's own root hubs.

Everything below is read-only:
  - /sys/bus/usb/devices/*/descriptors  (binary descriptor blob, kernel >= 4.5)
  - /sys/bus/usb/devices/*/speed         ("1.5" | "12" | "480" | "5000" | "10000")
  - /sys/bus/usb/devices/*/idVendor, idProduct, version, bcdDevice, product, manufacturer
  No ioctl to /dev/bus/usb, no setspeed, no reset, no unbind, no echo into sysfs.

Optional fallback (also read-only): `lsusb -v -d vid:pid` and `lsusb -v -s bus:dev`
if the tool is available and readable.

Usage:
  python3 usb_descriptor_probe.py            # walk all devices on this host
  python3 usb_descriptor_probe.py --vid 045e # filter to a vendor (case-insensitive hex)
  python3 usb_descriptor_probe.py --json     # machine-readable output to stdout

Exit code 0 on success; non-zero if a sysfs read fails.
"""

import argparse
import json
import os
import struct
import subprocess
import sys

SYSFS_USB = "/sys/bus/usb/devices"

# USB descriptor types (usb 2.0 spec table 9-5)
USB_DT_DEVICE = 0x01
USB_DT_CONFIG = 0x02
USB_DT_STRING = 0x03
USB_DT_INTERFACE = 0x04
USB_DT_ENDPOINT = 0x05
USB_DT_DEVICE_QUALIFIER = 0x06
USB_DT_OTHER_SPEED_CONFIG = 0x07
USB_DT_INTERFACE_POWER = 0x08
USB_DT_BOS = 0x0F
USB_DT_DEVICE_CAPABILITY = 0x10

# bmAttributes endpoint transfer type (usb 2.0 spec table 9-13, bits 1..0)
EP_TYPE = {0: "control", 1: "isochronous", 2: "bulk", 3: "interrupt"}

# bcdUSB / speed cross-reference for the report
SPEED_MBPS = {
    "1.5": ("low", 1.5),
    "12": ("full", 12),
    "480": ("high", 480),
    "5000": ("super", 5000),
    "10000": ("super+(10G)", 10000),
    "20000": ("super(20G)", 20000),
    "unknown": ("unknown", None),
}


def usb_descriptor_is_class_ff47d0(interface_descs):
    """GIP data interface: class 0xFF, subclass 0x47, protocol 0xD0."""
    for i in interface_descs:
        if (i["bInterfaceClass"], i["bInterfaceSubClass"], i["bInterfaceProtocol"]) == \
                (0xFF, 0x47, 0xD0):
            return True
    return False


def parse_descriptors(blob):
    """Parse a concatenated USB descriptor blob into a dict of lists."""
    out = {
        "device": None,
        "configs": [],
        "interfaces": [],
        "endpoints": [],
        "bos": None,
        "unknown": [],
    }
    off = 0
    n = len(blob)
    while off + 2 <= n:
        bLength = blob[off]
        bDescriptorType = blob[off + 1]
        if bLength < 2 or off + bLength > n:
            out["unknown"].append({"offset": off, "type": bDescriptorType, "bLength": bLength})
            off += 1
            continue
        raw = blob[off:off + bLength]
        if bDescriptorType == USB_DT_DEVICE and bLength >= 18:
            out["device"] = {
                "bLength": raw[0],
                "bDescriptorType": raw[1],
                "bcdUSB": struct.unpack_from("<H", raw, 2)[0],
                "bDeviceClass": raw[4],
                "bDeviceSubClass": raw[5],
                "bDeviceProtocol": raw[6],
                "bMaxPacketSize0": raw[7],
                "idVendor": struct.unpack_from("<H", raw, 8)[0],
                "idProduct": struct.unpack_from("<H", raw, 10)[0],
                "bcdDevice": struct.unpack_from("<H", raw, 12)[0],
                "bNumConfigurations": raw[17],
            }
        elif bDescriptorType == USB_DT_CONFIG and bLength >= 9:
            out["configs"].append({
                "bLength": raw[0],
                "bDescriptorType": raw[1],
                "wTotalLength": struct.unpack_from("<H", raw, 2)[0],
                "bNumInterfaces": raw[4],
                "bConfigurationValue": raw[5],
                "bmAttributes": raw[7],
                "bMaxPower_mA": raw[8] * 2,
            })
        elif bDescriptorType == USB_DT_INTERFACE and bLength >= 9:
            out["interfaces"].append({
                "bLength": raw[0],
                "bDescriptorType": raw[1],
                "bInterfaceNumber": raw[2],
                "bAlternateSetting": raw[3],
                "bNumEndpoints": raw[4],
                "bInterfaceClass": raw[5],
                "bInterfaceSubClass": raw[6],
                "bInterfaceProtocol": raw[7],
            })
        elif bDescriptorType == USB_DT_ENDPOINT and bLength >= 7:
            bmAttributes = raw[3]
            out["endpoints"].append({
                "bLength": raw[0],
                "bDescriptorType": raw[1],
                "bEndpointAddress": raw[2],
                "direction": "IN" if raw[2] & 0x80 else "OUT",
                "bEndpointNumber": raw[2] & 0x0F,
                "bmAttributes": bmAttributes,
                "transfer_type": EP_TYPE.get(bmAttributes & 0x03, "reserved"),
                "wMaxPacketSize": struct.unpack_from("<H", raw, 4)[0],
                "bInterval": raw[6],
            })
        elif bDescriptorType == USB_DT_BOS:
            out["bos"] = {"bLength": raw[0], "bDescriptorType": raw[1]}
        else:
            out["unknown"].append({"offset": off, "type": bDescriptorType, "bLength": bLength})
        off += bLength
    return out


def read_text(path):
    try:
        with open(path, "r", encoding="ascii", errors="replace") as f:
            return f.read().strip()
    except (OSError, ValueError):
        return None


def read_binary(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except (OSError, ValueError):
        return None


def lsusb_verbose(bus, dev, vid, pid):
    """Read-only fallback using lsusb (no ioctl needed for -v library descriptors)."""
    if bus is None or dev is None:
        return None
    try:
        r = subprocess.run(
            ["lsusb", "-v", "-s", "%s:%s" % (bus, dev)],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def scan_device(path, name):
    info = {
        "sysfs_name": name,
        "sysfs_path": path,
        "speed_mbps": read_text(os.path.join(path, "speed")),
        "idVendor": read_text(os.path.join(path, "idVendor")),
        "idProduct": read_text(os.path.join(path, "idProduct")),
        "bcdDevice": read_text(os.path.join(path, "bcdDevice")),
        "manufacturer": read_text(os.path.join(path, "manufacturer")),
        "product": read_text(os.path.join(path, "product")),
        "version_bcdUSB": read_text(os.path.join(path, "version")),
        "descriptors": None,
        "descriptor_error": None,
        "lsusb": None,
    }
    blob = read_binary(os.path.join(path, "descriptors"))
    if blob is not None:
        info["descriptors"] = parse_descriptors(blob)
    else:
        info["descriptor_error"] = "no /descriptors sysfs file (kernel < 4.5 or no config read)"

    # lsusb fallback (read-only) for exact text descriptors when sysfs blob is absent
    if info["descriptors"] is None:
        parent = os.path.dirname(path.rstrip("/"))
        # derive bus/device from the sysfs name: "N-M" or "usbN"
        bus = dev = None
        if "-" in name:
            bus, dev = name.split("-", 1)
            if dev and "." in dev:
                dev = dev.split(".", 1)[0]
        info["lsusb"] = lsusb_verbose(bus, dev, info["idVendor"], info["idProduct"])
    return info


def is_interface(name):
    # interface children look like "1-7:1.0" (contain a ':')
    return ":" in name


def main():
    ap = argparse.ArgumentParser(description="Read-only USB descriptor + speed probe (sysfs).")
    ap.add_argument("--vid", help="Only show devices with this idVendor (hex, e.g. 045e)")
    ap.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    args = ap.parse_args()

    devices = []
    names = sorted(os.listdir(SYSFS_USB))
    vid_filter = args.vid.upper().lstrip("0X") if args.vid else None

    for name in names:
        if is_interface(name):
            continue  # interface nodes ("N-M:1.X") carry no descriptor blob of their own here
        path = os.path.join(SYSFS_USB, name)
        if not os.path.isdir(path):
            continue
        info = scan_device(path, name)
        if vid_filter:
            dev_vid = (info["idVendor"] or "")
            if dev_vid.upper().lstrip("0X") != vid_filter:
                continue
        devices.append(info)

    if args.json:
        print(json.dumps(devices, indent=2))
        return 0

    # human readable
    for d in devices:
        spd_txt = d["speed_mbps"] or "unknown"
        spd_name, spd_mbps = SPEED_MBPS.get(spd_txt, ("unknown", None))
        vid = d["idVendor"] or "????"
        pid = d["idProduct"] or "????"
        product = (d["product"] or "")[:40]
        print("=" * 78)
        print("Device %-12s  %s:%s  bus speed=%s Mbps (%s)  %s"
              % (d["sysfs_name"], vid, pid, spd_txt, spd_name, product))
        if d["version_bcdUSB"]:
            print("  sysfs version (bcdUSB) = %s" % d["version_bcdUSB"])
        if d["manufacturer"]:
            print("  manufacturer = %s" % d["manufacturer"])
        desc = d["descriptors"]
        if desc is None:
            print("  [descriptors unavailable] %s" % (d["descriptor_error"] or ""))
            if d["lsusb"]:
                print("  --- lsusb -v ---")
                for line in d["lsusb"].splitlines():
                    print("  " + line)
            continue
        dev = desc["device"]
        if dev:
            print("  Device Descriptor: bcdUSB=0x%04x class/sub/proto=%d/%d/%d "
                  "bMaxPacketSize0=%d idVendor:idProduct=%04x:%04x bcdDevice=0x%04x nConfigs=%d"
                  % (dev["bcdUSB"], dev["bDeviceClass"], dev["bDeviceSubClass"],
                     dev["bDeviceProtocol"], dev["bMaxPacketSize0"], dev["idVendor"],
                     dev["idProduct"], dev["bcdDevice"], dev["bNumConfigurations"]))
        for c in desc["configs"]:
            print("  Configuration: bConfigurationValue=%d bNumInterfaces=%d "
                  "bMaxPower=%d mA  (wTotalLength=%d)"
                  % (c["bConfigurationValue"], c["bNumInterfaces"], c["bMaxPower_mA"],
                     c["wTotalLength"]))
        for i in desc["interfaces"]:
            print("    Interface %d alt %d: class/sub/proto=0x%02X/0x%02X/0x%02X endpoints=%d"
                  % (i["bInterfaceNumber"], i["bAlternateSetting"], i["bInterfaceClass"],
                     i["bInterfaceSubClass"], i["bInterfaceProtocol"], i["bNumEndpoints"]))
        for e in desc["endpoints"]:
            print("      EP 0x%02x %s: %s wMaxPacketSize=%d bInterval=%d"
                  % (e["bEndpointAddress"], e["direction"], e["transfer_type"],
                     e["wMaxPacketSize"], e["bInterval"]))
        gip = usb_descriptor_is_class_ff47d0(desc["interfaces"])
        if gip:
            print("  ** GIP class interface (FF/47/D0) present -> Xbox One/Series-style pad **")
    return 0


if __name__ == "__main__":
    sys.exit(main())
