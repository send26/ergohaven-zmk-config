/*
 * Key inside the `en` macro. Presses the US scancode only when the preceding
 * 0xAE got a matching 0xAF. A timeout leaves the key unsent, including its
 * later release, so the HID count cannot stick.
 */

#define DT_DRV_COMPAT zmk_behavior_host_key

#include <drivers/behavior.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/keycode_state_changed.h>

#include "host_layout_gate.h"

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

static bool host_key_dropped;

static int key_event(uint32_t code, bool pressed, int64_t timestamp) {
    int rc = raise_zmk_keycode_state_changed_from_encoded(code, pressed, timestamp);

    if (rc == 0 || pressed) {
        return rc;
    }
    rc = raise_zmk_keycode_state_changed_from_encoded(code, false, timestamp);
    if (rc != 0) {
        LOG_WRN("host_key: release failed: %d", rc);
    }
    return rc;
}

static int on_keymap_binding_pressed(struct zmk_behavior_binding *binding,
                                     struct zmk_behavior_binding_event event) {
    int rc;

    if (!zmk_host_layout_confirmed()) {
        host_key_dropped = true;
        LOG_WRN("host_key: dropped, layout was not confirmed");
        return ZMK_BEHAVIOR_OPAQUE;
    }
    rc = key_event(binding->param1, true, event.timestamp);
    if (rc != 0) {
        host_key_dropped = true;
        LOG_WRN("host_key: press failed: %d", rc);
        return rc;
    }
    host_key_dropped = false;
    return ZMK_BEHAVIOR_OPAQUE;
}

static int on_keymap_binding_released(struct zmk_behavior_binding *binding,
                                      struct zmk_behavior_binding_event event) {
    int rc;

    if (host_key_dropped) {
        host_key_dropped = false;
        return ZMK_BEHAVIOR_OPAQUE;
    }
    rc = key_event(binding->param1, false, event.timestamp);
    if (rc != 0) {
        return rc;
    }
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api behavior_host_key_driver_api = {
    .binding_pressed = on_keymap_binding_pressed,
    .binding_released = on_keymap_binding_released,
};

#define HOST_KEY_INST(n)                                                                           \
    BEHAVIOR_DT_INST_DEFINE(n, NULL, NULL, NULL, NULL, POST_KERNEL,                                \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &behavior_host_key_driver_api);

DT_INST_FOREACH_STATUS_OKAY(HOST_KEY_INST)

#endif
