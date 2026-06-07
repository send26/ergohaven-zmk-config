#include <zephyr/kernel.h>
#include <zmk/event_manager.h>
#include <raw_hid/events.h>
#include <zmk/keymap.h>

#define HID_CMD_LAYOUT 0xAC
#define LAYER_EN 0
#define LAYER_RU 1

static int raw_hid_received_event_listener(const zmk_event_t *eh) {
    struct raw_hid_received_event *event = as_raw_hid_received_event(eh);
    if (!event || event->length < 2) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    if (event->data[0] != HID_CMD_LAYOUT) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    uint8_t target = event->data[1];
    if (target != LAYER_EN && target != LAYER_RU) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    if (zmk_keymap_layer_default() == target) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    zmk_keymap_layer_to(target);
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(op36_layer_sync, raw_hid_received_event_listener);
ZMK_SUBSCRIPTION(op36_layer_sync, raw_hid_received_event);
