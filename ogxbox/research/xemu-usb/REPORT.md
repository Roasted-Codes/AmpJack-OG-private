# xemu host-USB passthrough for GIP driver work — research report (read-only)

Date: 2026-11-24. Nothing was launched, and no config, udev rule or USB setting was changed.

## TLDR (plain English)
1. The installed xemu already contains QEMU's standard "plug a real USB device into the virtual machine" feature (`usb-host`). No rebuild is needed.
2. It is turned on with extra command-line words when xemu starts, not with a menu or a toml setting.
3. Linux has to let your user account open the controller's raw USB device. Today it doesn't (files are root-only), so one udev rule or a one-off permission change is needed. This is your decision.
4. The pad has to be attached at the same spot in the virtual USB tree where a real Xbox controller sits (behind a small hub). Otherwise the game may not see it. xemu's own controller code shows that layout exactly.
5. Recommendation: **passthrough available now**. Try it on the devkit xemu before touching the real console again.

## 1. Is passthrough in this build?
| Claim | Label | Evidence |
|---|---|---|
| Devkit binary is xemu 0.8.136 (AppImage, extracted read-only to scratch) | VERIFIED | `devkit--xemu--0.8.136/xemu.AppImage` → `usr/bin/xemu`; string `0.8.136` |
| Binary links libusb (`NEEDED libusb-1.0.so.0`). The AppImage does not ship it, so it uses the host's libusb 1.0.30 (`/usr/lib/libusb-1.0.so.0` exists) | VERIFIED | `readelf -d`; `pkg-config --modversion libusb-1.0` |
| The QEMU `usb-host` device is compiled in: strings `usb-host`, `../hw/usb/host-libusb.c`, properties `hostbus`/`hostaddr`/`hostdevice`/`vendorid`/`productid`/`isobufs`/`guest-reset`, plus the `libusb_detach_kernel_driver`/`claim_interface` calls | VERIFIED | `strings -a usr/bin/xemu` |
| Generic QEMU `-device` args are passed through. xemu's own preamble is `-device usb-hub,port=1,ports=4`, and user argv is appended after it | VERIFIED | `OGH2_Server/reference/xemu/system/vl.c:3100-3108` (current source); same string is in the 0.8.136 binary |
| There is no GUI or toml key for passthrough. `[input.peripherals.portN]` only covers XMU/peripheral type and param | VERIFIED | `config_spec.yml:23-62`; xemu.app/docs/controller says "USB passthru is not supported yet" (meaning no UI) |
| Other users have used `-device usb-host,...` with xemu (OG Duke, SBC) | VERIFIED (third-party report) | github.com/xemu-project/xemu/issues/389, /issues/606 |

## 2. Recipe (do not run until the owner approves the udev step)
**Emulated USB topology** (VERIFIED, `ui/xemu-input.c:261,739-765`; binary has `1.%d`, `1.%d.1`):
- Root port 1 → 4-port "daughterboard" `usb-hub`.
- Daughterboard port 3/4/1/2 = Xbox players 1/2/3/4 (`port_map = {3,4,1,2}`).
- Each player has a 3-port `usb-hub` at `1.N`:
  - pad at `1.N.1`
  - XMU slots at `1.N.2` and `1.N.3`.
- The pads' bus is the OHCI at PCI 00:02.0. Issue #1717 shows the path `pci.0:02.0/1.3/usb-hub`, and in issue #389 the default bus is named `usb-bus.1` (VERIFIED, third-party). Two OHCIs are created with 4 ports each (`hw/xbox/xbox.c:317-323`).

**Steps:**
1. Plug in the pad and run `lsusb` to get VID:PID. No Microsoft pad was plugged in during this check. Your xemu toml's gamepad history includes GUID `…5e04…120b…` = 045e:0b12 (Series X|S, GIP). INFERENCE: that is probably the pad.
2. Permission (owner decision): `/dev/bus/usb/BBB/DDD` is root:root 0664 (`50-udev-default.rules:74`). `uaccess` only tags `input` joystick nodes, not the USB device (`70-uaccess.rules:61`), so xemu can't claim the device as your user. Options:
   - a udev rule `SUBSYSTEM=="usb", ATTR{idVendor}=="045e", ATTR{idProduct}=="0b12", TAG+="uaccess"`, or
   - a one-off `setfacl -m u:roasted:rw /dev/bus/usb/BBB/DDD`.
3. Use player 4 (port 1.2), which the devkit toml leaves unbound (`port1=keyboard`, `port2=<Duke 045e:0289>`). Append to the folder launcher's xemu argv (an experiment-local copy, not the toml):
   `-device usb-hub,bus=usb-bus.1,port=1.2,ports=3 -device usb-host,bus=usb-bus.1,port=1.2.1,vendorid=0x045e,productid=0x0b12`
4. Check it took with the existing QMP socket: `human-monitor-command "info usb"`, which should list the host device at 1.2.1.
   - Alternative: hot-add both devices after boot with QMP `device_add` (same args). This lets you replug the device without restarting xemu.
5. On the host, libusb detaches `xpad` automatically. When xemu exits, the kernel driver is re-attached.

**Constraints and risks:**
- **xemu crash on port collision.** xemu creates its hubs with `&error_abort` (`xemu-input.c:746,769`). If SDL auto-binds any controller to player 4 while your hub is there, xemu aborts (INFERENCE from code).
  - Keep only keyboard + Duke bound, and don't hot-plug other pads.
  - SDL3's `SDL_JOYSTICK_HIDAPI_XBOX_ONE`/`SDL_HIDAPI_LIBUSB` is compiled in (VERIFIED strings), so SDL might try to grab the same pad. If it does, start xemu with env `SDL_JOYSTICK_HIDAPI_XBOX_ONE=0` (INFERENCE).
- **Topology matters.** In issue #389, a device placed on a bare root port (`port=x`) was "never seen as a controller". Use the `1.N` hub → `.1` layout. Whether XAPI also enumerates usb-bus.0 (00:03.0) is UNKNOWN.
- **Speed is fine.** OHCI is full-speed only. GIP pads are full-speed (12 Mb/s) and so are OHCI-compatible (INFERENCE; check `lsusb -v` bMaxPacketSize/speed).
- **Snapshots.** They won't load with a different device tree (issue #1717). Cold-boot only.
- **Fidelity.** QEMU OHCI and hub timing is not real MCPX timing. A driver that works in xemu still needs a final pass on the real console, but hangs in xemu cost nothing.
- **GPU-hang guard.** Extra argv doesn't change binary identity. Keep the normal launch-safety preflight.

## 3. Known-good model: xemu's emulated OG pad (`hw/xbox/xid-gamepad.c`, `xid.h`, `hw/usb/dev-hub.c`) — VERIFIED source
- **Device:** bcdUSB 0x0110, bDeviceClass/Sub/Proto 0/0/0 (class at interface level), bMaxPacketSize0 0x40.
  - Duke `usb-xbox-gamepad`: VID 0x045E / PID 0x0202. Controller S `usb-xbox-gamepad-s`: PID 0x0289.
  - bcdDevice 0x0100. Strings "QEMU" / "Microsoft Xbox Controller" / "1". 1 configuration.
- **Config:** bNumInterfaces 1, bConfigurationValue 1, bmAttributes 0x80, bMaxPower 50 (100 mA).
- **Interface 0:** class **0x58** (XID), subclass **0x42**, protocol 0, 2 endpoints.
  - EP **0x82** IN interrupt, wMaxPacketSize **0x20**, bInterval **4**.
  - EP **0x02** OUT interrupt, wMaxPacketSize **0x20**, bInterval **4**.
- **XID class descriptor** (GET_DESCRIPTOR vendor/class request, wValue **0x4200**, type 0x42): bLength 0x10, bcdXid 0x0100, bType 0x01 (gamepad), bSubType 0x01 Duke / 0x02 S, bMaxInputReportSize 20, bMaxOutputReportSize 6, wAlternateProductIds FFFF×4.
- **Also handled:** GET_REPORT (input state), SET_REPORT (rumble), GET_CAPABILITIES (`xid.c:118-180`).
- **Hub in front of the pad:** QEMU `usb-hub` (device/interface class 0x09, status EP interrupt, bInterval 0xFF) created with `ports=3`: pad on hub port 1, XMUs on ports 2–3. It sits behind the 4-port daughterboard hub on root port 1.
- **Contrast with the GIP pad:** the GIP pad shows up as interface FF/47/D0 with 64-byte interrupt EPs. A title-local class driver has to match that interface itself, because the XID 0x58/0x42 path won't.

## Recommendation
**Passthrough available now.** No rebuild is needed: usb-host and libusb are compiled into 0.8.136. Host toolchain notes in case they're ever needed: ninja, gcc, libusb-1.0 and sdl2 pkg-configs are present, meson is missing.

The only blocker is the owner-approved USB permission for the pad. After that: follow the step-2 recipe, use player 4, check with `info usb`, and add the GIP pad as a single device.
