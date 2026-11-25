# AmpJack-OG worker09 diagnostic — standalone original-Xbox XBE.
# Build:  cd ogxbox/diagnostic && make
# Output: bin/default.xbe  (+ bin/AmpJackProbe.exe and bin/AmpJackProbe.map)
#
# The LDFLAGS below map this project's clean-room C declarations onto the
# PRIVATE XAPILIB symbol names (re-derived from the xapilib.lib COFF symbol
# table in ogxbox/research/binding). This is the only place proprietary
# symbol *names* (not code) are referenced, via lld-link /alternatename.

OXDK_DIR  = /home/roasted/Desktop/Xbox/OXDK
XBE_TITLE = AmpJackProbe
XBE_NAME  = AmpJack USB Probe
XBE_MODE  = RETAIL

SRCS = src/main.c src/lld_workaround.c

# Title-linked USBD lives in xapilib.lib. libcmt/libcpmt = CRT (memset etc).
# d3d8.lib = Direct3DCreate8 for the optional on-screen status colour.
OXDK_LIBS = libcmt.lib libcpmt.lib xboxkrnl.lib xapilib.lib xbdm.lib d3d8.lib

LDFLAGS = \
	/alternatename:_usbd_GetClassId=?GetClassId@IUsbDevice@@QBE?AT_PNP_CLASS_ID@@XZ \
	/alternatename:_usbd_GetDeviceDescriptor=?GetDeviceDescriptor@IUsbDevice@@QBEPBU_USB_DEVICE_DESCRIPTOR8@@XZ \
	/alternatename:_usbd_GetConfigurationDescriptor=?GetConfigurationDescriptor@IUsbDevice@@QBEPBU_USB_CONFIGURATION_DESCRIPTOR@@XZ \
	/alternatename:_usbd_GetInterfaceDescriptor=?GetInterfaceDescriptor@IUsbDevice@@QBEPBU_USB_INTERFACE_DESCRIPTOR@@XZ \
	/alternatename:_usbd_GetEndpointDescriptor=?GetEndpointDescriptor@IUsbDevice@@QBEPBU_USB_ENDPOINT_DESCRIPTOR@@EEE@Z \
	/alternatename:_usbd_GetInterfaceNumber=?GetInterfaceNumber@IUsbDevice@@QBEEXZ \
	/alternatename:_usbd_GetPort=?GetPort@IUsbDevice@@QBEKXZ \
	/alternatename:_usbd_GetLowSpeed=?GetLowSpeed@IUsbDevice@@QBEEXZ \
	/alternatename:_usbd_IsHardwareConnected=?IsHardwareConnected@IUsbDevice@@QBEEXZ \
	/alternatename:_usbd_FindClassDriver@4=?USBD_FindClassDriver@@YGPAU_USB_CLASS_DRIVER_DESCRIPTION@@T_PNP_CLASS_ID@@@Z \
	/alternatename:@usbd_LoadClassDriver@8=?USBD_LoadClassDriver@@YIXPAVIUsbDevice@@T_PNP_CLASS_ID@@@Z

include $(OXDK_DIR)/oxdk.mk

# Fail-closed build gate: re-derive the LoadClassDriver E9-detour pin from the
# freshly built .exe/.xbe and diff against the committed src/pinned_load.h.
# Any drift (e.g. new xapilib objects changing the link layout) fails the build.
# The header itself is generated with the same script (no --verify).
verify-pin: bin/default.xbe
	python3 ../work/09-diagnostic/gen_pinned_load.py --verify

all: verify-pin

.PHONY: verify-pin
