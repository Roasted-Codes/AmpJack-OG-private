/* Host tests for the input model (mapping, state, invalid handle, disconnect).
 * Compiles and runs on any host (no Xbox hardware). Synthetic fixtures only.
 */
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "input_model.h"

static int failures = 0;

#define CHECK(cond, msg) do { \
    if (!(cond)) { printf("FAIL: %s\n", msg); failures++; } \
    else { printf("ok:   %s\n", msg); } \
} while (0)

static ampjack_input_snapshot_t make_snap(void)
{
    ampjack_input_snapshot_t s;
    memset(&s, 0, sizeof(s));
    s.port = 0;
    s.connected = 1;
    return s;
}

static void test_mapping_face_buttons(void)
{
    ampjack_input_snapshot_t s = make_snap();
    og_xinput_state_t st;
    memset(&st, 0xCC, sizeof(st)); /* poison to prove full write */

    s.a = 1; s.b = 1; s.x = 1; s.y = 1;
    ampjack_map_snapshot_to_xinput(&s, &st);

    CHECK(st.Gamepad.bAnalogButtons[XG_AB_A] == 0xFF, "A -> analog A full on");
    CHECK(st.Gamepad.bAnalogButtons[XG_AB_B] == 0xFF, "B -> analog B full on");
    CHECK(st.Gamepad.bAnalogButtons[XG_AB_X] == 0xFF, "X -> analog X full on");
    CHECK(st.Gamepad.bAnalogButtons[XG_AB_Y] == 0xFF, "Y -> analog Y full on");
    CHECK(st.Gamepad.wButtons == 0, "face buttons do not set wButtons (classic)");
}

static void test_mapping_bumpers_and_face()
{
    ampjack_input_snapshot_t s = make_snap();
    og_xinput_state_t st;
    memset(&st, 0, sizeof(st));

    s.lb = 1; s.rb = 1;
    ampjack_map_snapshot_to_xinput(&s, &st);

    CHECK(st.Gamepad.bAnalogButtons[XG_AB_BLACK] == 0xFF, "LB -> Black analog on");
    CHECK(st.Gamepad.bAnalogButtons[XG_AB_WHITE] == 0xFF, "RB -> White analog on");
}

static void test_mapping_dpad_and_meta(void)
{
    ampjack_input_snapshot_t s = make_snap();
    og_xinput_state_t st;
    memset(&st, 0, sizeof(st));

    s.dpad_up = 1; s.dpad_left = 1;
    s.start = 1; s.back = 1;
    s.left_thumb = 1; s.right_thumb = 1;
    ampjack_map_snapshot_to_xinput(&s, &st);

    CHECK(st.Gamepad.wButtons == (XG_DPAD_UP | XG_DPAD_LEFT | XG_START | XG_BACK |
                                   XG_LEFT_THUMB | XG_RIGHT_THUMB),
          "dpad+meta bits set in wButtons");
}

static void test_mapping_axes(void)
{
    ampjack_input_snapshot_t s = make_snap();
    og_xinput_state_t st;
    memset(&st, 0, sizeof(st));

    s.left_trigger = 128;
    s.right_trigger = 255;
    s.left_stick_x = -30000; s.left_stick_y = 32767;
    s.right_stick_x = 1; s.right_stick_y = -1;
    ampjack_map_snapshot_to_xinput(&s, &st);

    CHECK(st.Gamepad.bAnalogButtons[XG_AB_LEFT_TRIGGER] == 128, "LT analog value");
    CHECK(st.Gamepad.bAnalogButtons[XG_AB_RIGHT_TRIGGER] == 255, "RT full analog");
    CHECK(st.Gamepad.sThumbLX == -30000, "left stick X");
    CHECK(st.Gamepad.sThumbLY == 32767, "left stick Y");
    CHECK(st.Gamepad.sThumbRX == 1 && st.Gamepad.sThumbRY == -1, "right stick");
}

static void test_disconnect(void)
{
    ampjack_input_snapshot_t s = make_snap();
    og_xinput_state_t st;
    memset(&st, 0xCC, sizeof(st));

    s.connected = 0;
    s.a = 1; s.left_trigger = 200; s.left_stick_x = 12345; /* stale fields */
    ampjack_map_snapshot_to_xinput(&s, &st);

    CHECK(st.Gamepad.wButtons == 0, "disconnect: wButtons zeroed");
    CHECK(st.Gamepad.bAnalogButtons[XG_AB_A] == 0, "disconnect: A zeroed");
    CHECK(st.Gamepad.bAnalogButtons[XG_AB_LEFT_TRIGGER] == 0, "disconnect: LT zeroed");
    CHECK(st.Gamepad.sThumbLX == 0, "disconnect: stick zeroed");
    CHECK(st.dwPacketNumber == 0, "disconnect: packet zeroed");
}

static void test_no_device_and_invalid(void)
{
    ampjack_input_snapshot_t s = make_snap();
    CHECK(ampjack_snapshot_has_device(&s) == true, "connected snapshot reports device");

    s.connected = 0;
    CHECK(ampjack_snapshot_has_device(&s) == false, "disconnected snapshot reports no device");

    s.connected = 1; s.port = 9; /* invalid port */
    CHECK(ampjack_snapshot_has_device(&s) == false, "port out of range -> no device");

    CHECK(ampjack_snapshot_has_device(NULL) == false, "NULL snapshot -> no device");
}

static void test_packet_number(void)
{
    ampjack_input_snapshot_t s = make_snap();
    og_xinput_state_t st;
    s.packet_number = 0xDEADBEEF;
    ampjack_map_snapshot_to_xinput(&s, &st);
    CHECK(st.dwPacketNumber == 0xDEADBEEF, "packet number passthrough");
}

static void test_caps(void)
{
    og_xinput_caps_t caps;
    memset(&caps, 0xCC, sizeof(caps));
    ampjack_fill_gamepad_caps(&caps);
    CHECK(caps.SubType == XINPUT_DEVSUBTYPE_GC_GAMEPAD, "caps SubType == 1 gamepad");
    CHECK(caps.Rumble.wLeftMotorSpeed == 0xFFFF, "caps rumble present");
}

static void test_size_contracts(void)
{
    /* XDK sizes on i386: XINPUT_STATE is packed 22 bytes. */
    CHECK(sizeof(og_xinput_gamepad_t) == 18, "gamepad == 18 bytes");
    CHECK(sizeof(og_xinput_state_t) == 22, "state == 22 bytes");
    CHECK(sizeof(og_xinput_caps_t) == 25, "caps == 25 bytes");
    CHECK(sizeof(ampjack_input_snapshot_t) >= 24, "snapshot has expected minimum size");
    /* Offsets of the analog buttons in the packed state (dwPacketNumber@0,
     * wButtons@4, bAnalogButtons@6, then 4 sticks @14). */
    og_xinput_state_t st;
    uint8_t *byte = (uint8_t *)&st;
    CHECK((byte + 4) == (uint8_t *)&st.Gamepad.wButtons, "wButtons offset 4");
    CHECK((byte + 6) == (uint8_t *)&st.Gamepad.bAnalogButtons[0], "bAnalogButtons offset 6");
}

int main(void)
{
    test_mapping_face_buttons();
    test_mapping_bumpers_and_face();
    test_mapping_dpad_and_meta();
    test_mapping_axes();
    test_disconnect();
    test_no_device_and_invalid();
    test_packet_number();
    test_caps();
    test_size_contracts();

    printf("\n%s: %d failure(s)\n", failures == 0 ? "PASS" : "FAIL", failures);
    return failures == 0 ? 0 : 1;
}
