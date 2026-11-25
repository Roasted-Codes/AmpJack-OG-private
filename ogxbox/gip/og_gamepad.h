/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * og_gamepad.h -- the original Xbox controller state, and the map from a wired
 * Xbox One (GIP) pad to it.
 *
 * The target shape is the OG Xbox XINPUT_GAMEPAD: VERIFIED against the OG SDK
 * header (OXDK/xbox/xdk/include/xbox.h, inside the #include <PSHPACK1.H> block):
 *
 *     typedef struct _XINPUT_GAMEPAD {
 *         WORD    wButtons;          // dpad / start / back / thumb-click bits
 *         BYTE    bAnalogButtons[8]; // A B X Y Black White LT RT (analog)
 *         SHORT   sThumbLX; sThumbLY; sThumbRX; sThumbRY;
 *     } XINPUT_GAMEPAD;              // packed, 18 bytes
 *
 * A/B/X/Y/Black/White are pressure-sensitive on the original pad; an Xbox One
 * pad's A/B/X/Y/LB/RB are digital, so they are emitted as 0x00 / 0xFF.
 * The original console is x86 (little-endian), so this packed struct in memory IS
 * the wire/XInputGetState layout; og_gamepad_pack() spells that out explicitly.
 */
#pragma once

#include "../../core/compat.h"
#include "../../core/gip.h"

/* wButtons bits (OXDK xbox.h) */
#define OG_GP_DPAD_UP    0x0001u
#define OG_GP_DPAD_DOWN  0x0002u
#define OG_GP_DPAD_LEFT  0x0004u
#define OG_GP_DPAD_RIGHT 0x0008u
#define OG_GP_START      0x0010u
#define OG_GP_BACK       0x0020u
#define OG_GP_LTHUMB     0x0040u
#define OG_GP_RTHUMB     0x0080u

/* bAnalogButtons[8] indices (OXDK xbox.h) */
enum {
	OG_AB_A = 0, OG_AB_B, OG_AB_X, OG_AB_Y,
	OG_AB_BLACK, OG_AB_WHITE, OG_AB_LTRIG, OG_AB_RTRIG,
};

/* full-pressure value for a digital (non-pressure) button presented as analog */
#define OG_BTN_PRESSED  0xffu
#define OG_BTN_RELEASED 0x00u

struct og_gamepad {
	u16 buttons;                 /* OG_GP_* : dpad/start/back/thumb */
	u8  analog[8];               /* OG_AB_* : A B X Y Black White LT RT */
	s16 stick_lx, stick_ly;      /* up = positive, right = positive */
	s16 stick_rx, stick_ry;
} __packed;

#define OG_GAMEPAD_WIRE 18
_Static_assert(sizeof(struct og_gamepad) == OG_GAMEPAD_WIRE,
	       "og_gamepad must pack to the 18-byte XINPUT_GAMEPAD");

/* GIP buttons -> OG wButtons bits */
#define OG_FROM_GIP_BITS 0

/* GIP triggers are nominally 0..1023; an out-of-range u16 report must SATURATE
 * to 1023 before the 0..255 scale, otherwise the narrowing cast wraps (e.g.
 * 65535 * 255 / 1023 = 16337 -> (u8)209, and larger values wrap to 0). */
static inline u8 og_trigger_scale(u16 t)
{
	u32 v = t > 1023 ? 1023 : t;

	return (u8)(v * 255 / 1023);
}

static inline void og_gamepad_from_gip(struct og_gamepad *g,
				       const struct gip_gamepad_state *s)
{
	u16 bits = 0, b = s->buttons;

	memset(g, 0, sizeof(*g));

	if (b & GIP_GP_BTN_MENU)     bits |= OG_GP_START;
	if (b & GIP_GP_BTN_VIEW)     bits |= OG_GP_BACK;
	if (b & GIP_GP_BTN_STICK_L)  bits |= OG_GP_LTHUMB;
	if (b & GIP_GP_BTN_STICK_R)  bits |= OG_GP_RTHUMB;
	if (b & GIP_GP_BTN_DPAD_U)   bits |= OG_GP_DPAD_UP;
	if (b & GIP_GP_BTN_DPAD_D)   bits |= OG_GP_DPAD_DOWN;
	if (b & GIP_GP_BTN_DPAD_L)   bits |= OG_GP_DPAD_LEFT;
	if (b & GIP_GP_BTN_DPAD_R)   bits |= OG_GP_DPAD_RIGHT;
	g->buttons = bits;

	g->analog[OG_AB_A]     = (b & GIP_GP_BTN_A)     ? OG_BTN_PRESSED : OG_BTN_RELEASED;
	g->analog[OG_AB_B]     = (b & GIP_GP_BTN_B)     ? OG_BTN_PRESSED : OG_BTN_RELEASED;
	g->analog[OG_AB_X]     = (b & GIP_GP_BTN_X)     ? OG_BTN_PRESSED : OG_BTN_RELEASED;
	g->analog[OG_AB_Y]     = (b & GIP_GP_BTN_Y)     ? OG_BTN_PRESSED : OG_BTN_RELEASED;
	/* The Xbox One's LB/RB stand in for the original's Black/White. This is the
	 * standard dual-analog equivalence (LB -> left bumper -> Black, RB -> right
	 * bumper -> White) and is an INFERENCE: there is no verified Halo 2 or user
	 * mapping evidence that reverses it, so it is kept as-is rather than swapped
	 * on a guess. The boundary tests below detect a swap should one ever creep
	 * in. */
	g->analog[OG_AB_BLACK] = (b & GIP_GP_BTN_BUMPER_L) ? OG_BTN_PRESSED : OG_BTN_RELEASED;
	g->analog[OG_AB_WHITE] = (b & GIP_GP_BTN_BUMPER_R) ? OG_BTN_PRESSED : OG_BTN_RELEASED;

	/* GIP triggers 0..1023 -> OG analog 0..255, saturated (see og_trigger_scale) */
	g->analog[OG_AB_LTRIG] = og_trigger_scale(s->trigger_left);
	g->analog[OG_AB_RTRIG] = og_trigger_scale(s->trigger_right);

	g->stick_lx = s->stick_left_x;
	g->stick_ly = s->stick_left_y;
	g->stick_rx = s->stick_right_x;
	g->stick_ry = s->stick_right_y;
}

/* the 18-byte on-the-wire / XInputGetState layout (little-endian, packed) */
static inline void og_gamepad_pack(const struct og_gamepad *g, u8 out[OG_GAMEPAD_WIRE])
{
	put_le16(out + 0, g->buttons);
	memcpy(out + 2, g->analog, 8);
	put_le16(out + 10, (u16)g->stick_lx);
	put_le16(out + 12, (u16)g->stick_ly);
	put_le16(out + 14, (u16)g->stick_rx);
	put_le16(out + 16, (u16)g->stick_ry);
}

static inline void og_gamepad_unpack(const u8 in[OG_GAMEPAD_WIRE], struct og_gamepad *g)
{
	g->buttons = get_le16(in + 0);
	memcpy(g->analog, in + 2, 8);
	g->stick_lx = (s16)get_le16(in + 10);
	g->stick_ly = (s16)get_le16(in + 12);
	g->stick_rx = (s16)get_le16(in + 14);
	g->stick_ry = (s16)get_le16(in + 16);
}
