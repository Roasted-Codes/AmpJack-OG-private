/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * xinput_model.h -- the classic-Xbox XINPUT structures, promoted from the earlier
 * input_model.h TYPES (VERIFIED against OXDK/xbox/xdk/include/xbox.h). The
 * backend-independent ampjack_input_snapshot_t + ampjack_map_snapshot_to_xinput()
 * are DROPPED here: the hardened og_gip adapter (ogxbox/gip/og_gamepad.h) already
 * owns the single GIP->classic-button map, and the presentation layer
 * (ogxbox/integration/ogx_present.c) serves that snapshot directly. Keeping a
 * second mapping would duplicate the finalized button/mapping logic.
 *
 * Layout is VERIFIED and machine-asserted:
 *   XINPUT_GAMEPAD      18 B  (wButtons u16 + bAnalogButtons[8] + 4 x s16 stick)
 *   XINPUT_STATE        22 B  (dwPacketNumber u32 + XINPUT_GAMEPAD)
 *   XINPUT_CAPABILITIES 25 B  (SubType u8 + Reserved u16 + GAMEPAD + RUMBLE)
 *   XINPUT_FEEDBACK      4 B  (wLeftMotorSpeed u16 + wRightMotorSpeed u16)
 */
#ifndef OGX_XINPUT_MODEL_H
#define OGX_XINPUT_MODEL_H

#include <stdint.h>
#include <string.h>

#define OGX_XINPUT_GAMEPAD_SIZE  18
#define OGX_XINPUT_STATE_SIZE    22
#define OGX_XINPUT_CAPS_SIZE     25

/* wButtons bits (classic Xbox; NOT Xbox 360 values) */
#define XG_DPAD_UP        0x0001u
#define XG_DPAD_DOWN      0x0002u
#define XG_DPAD_LEFT      0x0004u
#define XG_DPAD_RIGHT     0x0008u
#define XG_START          0x0010u
#define XG_BACK           0x0020u
#define XG_LEFT_THUMB     0x0040u
#define XG_RIGHT_THUMB    0x0080u

/* bAnalogButtons indices */
#define XG_AB_A           0
#define XG_AB_B           1
#define XG_AB_X           2
#define XG_AB_Y           3
#define XG_AB_BLACK       4
#define XG_AB_WHITE       5
#define XG_AB_LEFT_TRIG   6
#define XG_AB_RIGHT_TRIG  7

/* Return codes (VERIFIED from u803 XBE disassembly) */
#define OGX_ERR_SUCCESS           0u     /* XINPUT_ERR_SUCCESS */
#define OGX_ERR_INVALID_PARAM     0x57u  /* 87 ERROR_INVALID_PARAMETER */
#define OGX_ERR_NOT_CONNECTED     0x48Fu /* 1167 ERROR_DEVICE_NOT_CONNECTED */
#define OGX_ERR_NOT_SUPPORTED     0x32u  /* 50 ERROR_NOT_SUPPORTED:
                                           * input-only rumble milestone (no
                                           * motors -> rumble cannot actuate) */

/* XINPUT_DEVSUBTYPE_GC_GAMEPAD (OXDK xbox.h) */
#define OGX_DEVSUBTYPE_GAMEPAD    0x01u

#ifdef __i386__
#define OGX_PACKED __attribute__((packed))
#else
#define OGX_PACKED __attribute__((packed))
#endif

typedef struct OGX_PACKED {
	uint16_t wButtons;
	uint8_t  bAnalogButtons[8];
	int16_t  sThumbLX;
	int16_t  sThumbLY;
	int16_t  sThumbRX;
	int16_t  sThumbRY;
} ogx_gamepad_t;

typedef struct OGX_PACKED {
	uint32_t     dwPacketNumber;
	ogx_gamepad_t Gamepad;
} ogx_state_t;

typedef struct OGX_PACKED {
	uint16_t wLeftMotorSpeed;
	uint16_t wRightMotorSpeed;
} ogx_vibration_t;

typedef struct OGX_PACKED {
	uint8_t       SubType;
	uint16_t      Reserved;
	ogx_gamepad_t Gamepad;
	ogx_vibration_t Vibration;
} ogx_capabilities_t;

/* compile-time size assertions (i386 32-bit ABI) */
_Static_assert(sizeof(ogx_gamepad_t)     == OGX_XINPUT_GAMEPAD_SIZE, "gamepad 18B");
_Static_assert(sizeof(ogx_state_t)       == OGX_XINPUT_STATE_SIZE,   "state 22B");
_Static_assert(sizeof(ogx_capabilities_t)== OGX_XINPUT_CAPS_SIZE,    "caps 25B");
_Static_assert(sizeof(ogx_vibration_t)   == 4,                        "feedback 4B");

/* ---------------------------------------------------------------------------
 * XINPUT_FEEDBACK (VERIFIED against OXDK/xbox/xdk/include/xbox.h, inside the
 * #include <PSHPACK1.H> block, lines ~647-662). XInputSetState does NOT take a
 * bare PC XINPUT_VIBRATION pointer: OG takes `PXINPUT_FEEDBACK`, whose 4-byte
 * XINPUT_RUMBLE sits BEHIND an IN OUT XINPUT_FEEDBACK_HEADER (dwStatus/hEvent +
 * 58-byte reserved region). The XID driver fills Header.dwStatus when the
 * output report actually completes (Halo's completion gate; `XID_OutputComplete`
 * / `XID_fSendDeviceReport(_URB*, _XINPUT_FEEDBACK_INTERNAL*)` in the linker
 * map). Reading the first 4 bytes of the feedback as motor speeds would read
 * dwStatus + the low word of hEvent -- never do that.
 *
 * The 4-byte XINPUT_RUMBLE swap substructure (ogx_vibration_t) is what
 * XINPUT_CAPABILITIES.Out carries; it must not be confused with the full 70-byte
 * XINPUT_FEEDBACK.
 * ------------------------------------------------------------------------- */
#define OGX_XINPUT_FEEDBACK_HEADER_INTERNAL_SIZE 58
#define OGX_XINPUT_FEEDBACK_SIZE                 70   /* header 66 + rumble 4 */

typedef struct OGX_PACKED {
	uint32_t dwStatus;                /* offset 0: ERROR_* (IN OUT), the completion gate */
	uint32_t hEvent;                  /* offset 4: optional HANDLE (IN), never signalled here */
	uint8_t  Reserved[OGX_XINPUT_FEEDBACK_HEADER_INTERNAL_SIZE]; /* offset 8 */
} ogx_input_feedback_header_t;

typedef struct OGX_PACKED {
	ogx_input_feedback_header_t Header;   /* offset 0, 66 bytes */
	ogx_vibration_t             Rumble;   /* offset 66: wLeft/wRightMotorSpeed */
} ogx_input_feedback_t;

_Static_assert(sizeof(ogx_input_feedback_header_t) == 66, "feedback header 66B");
_Static_assert(sizeof(ogx_input_feedback_t)         == OGX_XINPUT_FEEDBACK_SIZE, "feedback 70B");

/* Fully initialize an XINPUT_CAPABILITIES. Every field is written (zero-fill
 * first) -- fixes the earlier initializer which left Gamepad fields set.
 *
 * Rumble (Vibration) is reported as ZERO: this milestone has NO motors, and
 * claiming 0xFFFF support while returning no output would be dishonest.
 *
 * caps->Gamepad.* capability markers are an INFERENCE (sizes/layout VERIFIED,
 * the "presence" marker values chosen so a generic reader sees the same set of
 * controls the adapter actually serves); Halo 2 itself only reads SubType. */
void ogx_fill_gamepad_caps(ogx_capabilities_t *caps);

#endif /* OGX_XINPUT_MODEL_H */
