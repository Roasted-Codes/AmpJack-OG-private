/* AmpJack OG - Halo 2 OG XINPUT_GAMEPAD backend-independent input model.
 *
 * This header defines the canonical XINPUT_STATE for the classic Xbox (XDK 5849),
 * the backend-independent snapshot struct, and the mapping function.
 *
 * Source: ~/Desktop/Xbox/OXDK/xbox/xdk/include/xbox.h lines 576-644 (VERIFIED)
 * Cross-referenced against XBInput.cpp SDK sample and u803 XBE disassembly.
 *
 * No dependency on Xbox hardware, USB, GIP, or real controllers.
 */

#ifndef AMPJACK_OG_INPUT_MODEL_H
#define AMPJACK_OG_INPUT_MODEL_H

#include <stdint.h>
#include <stdbool.h>

/* ----------------------------------------------------------------------
 * Classic Xbox XINPUT_GAMEPAD (xbox.h:576-584, packed via PSHPACK1)
 *
 * Size: 2 + 8 + 4*2 = 18 bytes.
 * wButtons bitmask: DPAD 0x1..0x8, START 0x10, BACK 0x20,
 *   LEFT_THUMB 0x40, RIGHT_THUMB 0x80.
 * bAnalogButtons[8]: A=0,B=1,X=2,Y=3,BLACK=4,WHITE=5,LT=6,RT=7.
 * No digital A/B/X/Y bits in wButtons on classic Xbox (VERIFIED xbox.h:586-593).
 * -------------------------------------------------------------------- */

#define XINPUT_GAMEPAD_SIZE      18

/* wButtons bitmask (classic Xbox only; NOT Xbox 360 values) */
#define XG_DPAD_UP               0x0001u
#define XG_DPAD_DOWN             0x0002u
#define XG_DPAD_LEFT             0x0004u
#define XG_DPAD_RIGHT            0x0008u
#define XG_START                 0x0010u
#define XG_BACK                  0x0020u
#define XG_LEFT_THUMB            0x0040u
#define XG_RIGHT_THUMB           0x0080u

/* bAnalogButtons indices */
#define XG_AB_A                  0
#define XG_AB_B                  1
#define XG_AB_X                  2
#define XG_AB_Y                  3
#define XG_AB_BLACK              4
#define XG_AB_WHITE              5
#define XG_AB_LEFT_TRIGGER       6
#define XG_AB_RIGHT_TRIGGER      7

/* Threshold: analog value > this is "pressed" (xbox.h:610) */
#define XG_MAX_CROSSTALK         30

/* Minimum/maximum axis range: classic Xbox sticks */
#define XG_STICK_MIN         (-32768)
#define XG_STICK_MAX          32767
#define XG_TRIGGER_MAX        255

/* Error codes returned by XInputGetState et al. (from XBE disasm) */
#define XINPUT_ERR_INVALID_PARAM    (0x57)       /* 87 */
#define XINPUT_ERR_NOT_CONNECTED    (0x48F)      /* 1167 */
#define XINPUT_ERR_SUCCESS          (0)

/* OEM controller caps SubType (xbox.h:680-681) */
#define XINPUT_DEVSUBTYPE_GC_GAMEPAD      0x01
#define XINPUT_CAPABILITIES_SIZE          25   /* SubType(1)+Reserved(2)+Gamepad(18)+Rumble(4) */

/* ---- Packed structs matching XDK exactly ----- */

#ifdef _MSC_VER
#pragma pack(push, 1)
#define PACKED
#else
#define PACKED __attribute__((packed))
#endif

typedef struct PACKED {
    uint16_t wButtons;
    uint8_t  bAnalogButtons[8];
    int16_t  sThumbLX;
    int16_t  sThumbLY;
    int16_t  sThumbRX;
    int16_t  sThumbRY;
} og_xinput_gamepad_t;

typedef struct PACKED {
    uint32_t         dwPacketNumber;
    og_xinput_gamepad_t Gamepad;
} og_xinput_state_t;

typedef struct PACKED {
    uint16_t wLeftMotorSpeed;
    uint16_t wRightMotorSpeed;
} og_xinput_rumble_t;

typedef struct PACKED {
    uint8_t  SubType;
    uint16_t Reserved;
    og_xinput_gamepad_t Gamepad;
    og_xinput_rumble_t  Rumble;
} og_xinput_caps_t;

#ifdef _MSC_VER
#pragma pack(pop)
#endif

/* compile-time size assertions */
_Static_assert(sizeof(og_xinput_gamepad_t) == XINPUT_GAMEPAD_SIZE, "gamepad size");
_Static_assert(sizeof(og_xinput_state_t) == 22, "state size");
_Static_assert(sizeof(og_xinput_caps_t) == XINPUT_CAPABILITIES_SIZE, "caps size");

/* ----------------------------------------------------------------------
 * Backend-independent snapshot — what a GIP adapter (worker 04) publishes.
 * This is the DATA CONTRACT between this worker (03-halo) and ogxbox/gip/.
 *
 * All fields use canonical generic gamepad units:
 *   - digital buttons: true = pressed
 *   - triggers: 0..255 analog
 *   - sticks: ±32767
 * No Xbox-specific XID/GIP packet detail leaks here.
 * -------------------------------------------------------------------- */

typedef struct PACKED {
    /* Virtual port index (0..3) this snapshot describes; 0xFF = nothing. */
    uint8_t   port;
    uint8_t   connected;    /* 0 = disconnected (all fields zero/invalid) */
    /* Unit is ticks since device opened (arbitrary, monotonic) */
    uint32_t  packet_number;

    /* Digital face buttons */
    bool a, b, x, y;
    /* Bumpers → classic Black/White */
    bool lb, rb;
    /* Menu/View click */
    bool start, back;
    /* Stick clicks */
    bool left_thumb, right_thumb;
    /* D-pad (4-way) */
    bool dpad_up, dpad_down, dpad_left, dpad_right;

    /* Analog triggers (unsigned 8-bit: 0 = released, 255 = fully pulled) */
    uint8_t  left_trigger;
    uint8_t  right_trigger;

    /* Analog sticks (signed 16-bit: ±32767) */
    int16_t  left_stick_x,  left_stick_y;
    int16_t  right_stick_x, right_stick_y;

    /* Rumble output sent to this port (set by C4; ignored if 0) */
    uint16_t rumble_left_motor;
    uint16_t rumble_right_motor;
} ampjack_input_snapshot_t;

/* ----------------------------------------------------------------------
 * Mapping: backend-independent snapshot → XINPUT_GAMEPAD
 *
 * Caller writes the resulting XINPUT_STATE to the game's pState buffer.
 * The XG_* button bits in gamepad.wButtons match classic Xbox only.
 * Modern bumpers (LB/RB) → Black (bAnalogButtons[4]), White (bAnalogButtons[5]).
 * -------------------------------------------------------------------- */

#ifdef __cplusplus
extern "C" {
#endif

void ampjack_map_snapshot_to_xinput(
    const ampjack_input_snapshot_t *snap,
    og_xinput_state_t *out_state);

/* Check if snapshot indicates a connected device. */
bool ampjack_snapshot_has_device(const ampjack_input_snapshot_t *snap);

/* Fill XINPUT_CAPABILITIES for a gamepad (SubType=1, rumble=yes). */
void ampjack_fill_gamepad_caps(og_xinput_caps_t *out_caps);

#ifdef __cplusplus
}
#endif

#endif /* AMPJACK_OG_INPUT_MODEL_H */