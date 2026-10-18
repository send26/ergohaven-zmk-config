#include <raw_hid/events.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include <zmk/event_manager.h>

#include "hid_cmd.h"
#include "horizon_mode.h"

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

static atomic_t horizon_active = ATOMIC_INIT(0);

bool zmk_horizon_active(void) { return atomic_get(&horizon_active) != 0; }

static int on_horizon_hid(const zmk_event_t *eh) {
    const struct raw_hid_received_event *event = as_raw_hid_received_event(eh);
    int at;
    uint8_t index;
    atomic_val_t prev;

    if (event == NULL || event->data == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    at = hid_frame_at(event->data, event->length, HID_CMD_HORIZON, 1);
    if (at < 0) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    index = event->data[at + 1];
    if (index > 1U) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    prev = atomic_set(&horizon_active, (atomic_val_t)index);
    if ((uint8_t)prev != index) {
        LOG_INF("Symbol destination %s", index ? "horizon" : "mac");
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(horizon_mode_hid, on_horizon_hid);
ZMK_SUBSCRIPTION(horizon_mode_hid, raw_hid_received_event);
