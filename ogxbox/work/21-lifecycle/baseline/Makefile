# AmpJack-OG worker11 GIP class-driver transport proof — standalone Xbox XBE.
# Build:  cd ogxbox/gipdriver && make
# Output: bin/default.xbe  (+ bin/AmpJackGip.exe and bin/AmpJackGip.map)
#
# LDFLAGS map this project's clean-room C declarations onto the PRIVATE
# XAPILIB symbol names (re-derived from the xapilib.lib COFF symbol table in
# ogxbox/work/07-binding/symbols_full.txt). Names only; no proprietary code.

OXDK_DIR  = /home/roasted/Desktop/Xbox/OXDK
XBE_TITLE = AmpJackGip
XBE_NAME  = AmpJack GIP Driver Probe
XBE_MODE  = RETAIL

SRCS = src/main.c src/lld_workaround.c

# Title-linked USBD lives in xapilib.lib. libcmt/libcpmt = CRT (memset etc).
# d3d8.lib = Direct3DCreate8 for the optional on-screen status colour.
OXDK_LIBS = libcmt.lib libcpmt.lib xboxkrnl.lib xapilib.lib xbdm.lib d3d8.lib

LDFLAGS = \
	/alternatename:_usbd_FindClassDriver@4=?USBD_FindClassDriver@@YGPAU_USB_CLASS_DRIVER_DESCRIPTION@@T_PNP_CLASS_ID@@@Z \
	/alternatename:_usbd_SubmitRequest=?SubmitRequest@IUsbDevice@@QAEJPAT_URB@@@Z

include $(OXDK_DIR)/oxdk.mk

# Fail-closed build gate: re-derive the FindClassDriver E9-detour pin from the
# freshly built .exe/.xbe and diff against the committed src/pinned_findclass.h.
verify-pin: bin/default.xbe
	python3 ../work/11-gipdriver/gen_pinned_findclass.py --verify

all: verify-pin

.PHONY: verify-pin
