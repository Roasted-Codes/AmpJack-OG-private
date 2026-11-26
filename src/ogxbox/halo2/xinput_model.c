/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "xinput_model.h"

void ogx_fill_gamepad_caps(ogx_capabilities_t *caps)
{
	if (!caps)
		return;

	/* Zero-fill the whole 25-byte struct: no field is left uninitialized,
	 * unlike worker 03's filler which wrote only SubType/Reserved/Rumble. */
	memset(caps, 0, sizeof(*caps));

	caps->SubType  = OGX_DEVSUBTYPE_GAMEPAD;
	caps->Reserved = 0;

	/* Capability markers (INFERENCE, documented in xinput_model.h): the digital
	 * buttons we actually emit, every analog button present, full-scale axis
	 * presence. Sticks are left 0 (we make no magnitude-marking claim). */
	caps->Gamepad.wButtons =
	    XG_DPAD_UP | XG_DPAD_DOWN | XG_DPAD_LEFT | XG_DPAD_RIGHT |
	    XG_START | XG_BACK | XG_LEFT_THUMB | XG_RIGHT_THUMB;
	for (int i = 0; i < 8; i++)
		caps->Gamepad.bAnalogButtons[i] = 0xff;
	caps->Gamepad.sThumbLX = 0;
	caps->Gamepad.sThumbLY = 0;
	caps->Gamepad.sThumbRX = 0;
	caps->Gamepad.sThumbRY = 0;

	/* Rumble: NOT supported this milestone (no motors). Deliberately 0. */
	caps->Vibration.wLeftMotorSpeed  = 0;
	caps->Vibration.wRightMotorSpeed = 0;
}
