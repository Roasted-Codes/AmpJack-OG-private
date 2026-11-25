/* AmpJack OG - backend-independent input model implementation. Host-testable. */
#include <stddef.h>
#include "input_model.h"

bool ampjack_snapshot_has_device(const ampjack_input_snapshot_t *snap)
{
    if (snap == NULL) {
        return false;
    }
    if (!snap->connected) {
        return false;
    }
    if (snap->port >= 4) {
        return false;
    }
    return true;
}

void ampjack_map_snapshot_to_xinput(
    const ampjack_input_snapshot_t *snap,
    og_xinput_state_t *out_state)
{
    uint16_t buttons = 0;

    /* Zero the output by default (disconnect-safe). */
    out_state->dwPacketNumber = 0;
    for (int i = 0; i < 8; i++) {
        out_state->Gamepad.bAnalogButtons[i] = 0;
    }
    out_state->Gamepad.wButtons = 0;
    out_state->Gamepad.sThumbLX = 0;
    out_state->Gamepad.sThumbLY = 0;
    out_state->Gamepad.sThumbRX = 0;
    out_state->Gamepad.sThumbRY = 0;

    if (!ampjack_snapshot_has_device(snap)) {
        return;
    }

    out_state->dwPacketNumber = snap->packet_number;

    /* Digital-only control bits live in wButtons (classic Xbox layout). */
    if (snap->dpad_up)      buttons |= XG_DPAD_UP;
    if (snap->dpad_down)    buttons |= XG_DPAD_DOWN;
    if (snap->dpad_left)    buttons |= XG_DPAD_LEFT;
    if (snap->dpad_right)   buttons |= XG_DPAD_RIGHT;
    if (snap->start)        buttons |= XG_START;
    if (snap->back)         buttons |= XG_BACK;
    if (snap->left_thumb)   buttons |= XG_LEFT_THUMB;
    if (snap->right_thumb)  buttons |= XG_RIGHT_THUMB;
    out_state->Gamepad.wButtons = buttons;

    /* Face A/B/X/Y are pressure-sensitive analog on classic Xbox.
     * Digital Xbox One buttons map to full-scale 0xFF (way above crosstalk 30). */
    out_state->Gamepad.bAnalogButtons[XG_AB_A]    = snap->a ? 0xFF : 0x00;
    out_state->Gamepad.bAnalogButtons[XG_AB_B]    = snap->b ? 0xFF : 0x00;
    out_state->Gamepad.bAnalogButtons[XG_AB_X]    = snap->x ? 0xFF : 0x00;
    out_state->Gamepad.bAnalogButtons[XG_AB_Y]    = snap->y ? 0xFF : 0x00;

    /* Modern bumpers map to classic Black/White. */
    out_state->Gamepad.bAnalogButtons[XG_AB_BLACK] = snap->lb ? 0xFF : 0x00;
    out_state->Gamepad.bAnalogButtons[XG_AB_WHITE] = snap->rb ? 0xFF : 0x00;

    /* Triggers are genuinely analog on both sides. */
    out_state->Gamepad.bAnalogButtons[XG_AB_LEFT_TRIGGER]  = snap->left_trigger;
    out_state->Gamepad.bAnalogButtons[XG_AB_RIGHT_TRIGGER] = snap->right_trigger;

    /* Sticks. */
    out_state->Gamepad.sThumbLX = snap->left_stick_x;
    out_state->Gamepad.sThumbLY = snap->left_stick_y;
    out_state->Gamepad.sThumbRX = snap->right_stick_x;
    out_state->Gamepad.sThumbRY = snap->right_stick_y;
}

void ampjack_fill_gamepad_caps(og_xinput_caps_t *out_caps)
{
    out_caps->SubType   = XINPUT_DEVSUBTYPE_GC_GAMEPAD;
    out_caps->Reserved  = 0;
    /* In: report that sticks/analog are present (values are set at runtime). */
    out_caps->Gamepad.wButtons              = 0;
    out_caps->Gamepad.bAnalogButtons[0]     = 0;
    out_caps->Gamepad.sThumbLX              = 0;
    /* Out: rumble capability. */
    out_caps->Rumble.wLeftMotorSpeed        = 0xFFFF; /* supported */
    out_caps->Rumble.wRightMotorSpeed       = 0xFFFF;
}
