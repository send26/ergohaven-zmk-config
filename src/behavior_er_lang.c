/*
 * E+R language chord.
 *
 * Horizon (Raw HID 0xB0 = 1): hold left Alt and left Shift together for 40 ms.
 * That sleep is the whole chord and blocks the key thread. Do not add another
 * sleep here. Windows treats the overlap as the layout toggle. A sequential
 * tap does not. The ZMK layer and the Mac input source stay where they are.
 *
 * Otherwise: toggle firmware layer 0/1. The host daemon maps that to ABC/Russian.
 */

#define DT_DRV_COMPAT zmk_behavior_er_lang

#include <drivers/behavior.h>
#include <dt-bindings/zmk/keys.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/keycode_state_changed.h>
#include <zmk/keymap.h>

#include "hid_cmd.h"
#include "horizon_mode.h"

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#define ER_CHORD_MS 40

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

static int key_event(uint32_t code, bool pressed, int64_t timestamp) {
    int rc = raise_zmk_keycode_state_changed_from_encoded(code, pressed, timestamp);

    if (rc == 0 || pressed) {
        return rc;
    }
    rc = raise_zmk_keycode_state_changed_from_encoded(code, false, timestamp);
    if (rc != 0) {
        LOG_WRN("er: key release failed: %d", rc);
    }
    return rc;
}

static int send_windows_lang_toggle(int64_t timestamp) {
    if (key_event(LEFT_ALT, true, timestamp) != 0) {
        LOG_WRN("er: Alt press failed");
        return -EIO;
    }
    if (key_event(LEFT_SHIFT, true, timestamp) != 0) {
        LOG_WRN("er: Shift press failed");
        if (key_event(LEFT_ALT, false, timestamp) != 0) {
            LOG_WRN("er: Alt release failed");
        }
        return -EIO;
    }
    k_msleep(ER_CHORD_MS);
    if (key_event(LEFT_SHIFT, false, timestamp) != 0) {
        LOG_WRN("er: Shift release failed");
    }
    if (key_event(LEFT_ALT, false, timestamp) != 0) {
        LOG_WRN("er: Alt release failed");
    }
    return 0;
}

static int on_keymap_binding_pressed(struct zmk_behavior_binding *binding,
                                     struct zmk_behavior_binding_event event) {
    int rc;

    ARG_UNUSED(binding);
    if (zmk_horizon_active()) {
        rc = send_windows_lang_toggle(event.timestamp);
        if (rc != 0) {
            return rc;
        }
        return ZMK_BEHAVIOR_OPAQUE;
    }

    if (zmk_keymap_layer_active(LAYER_RU)) {
        rc = zmk_keymap_layer_to(LAYER_EN);
    } else {
        rc = zmk_keymap_layer_to(LAYER_RU);
    }
    if (rc != 0) {
        LOG_WRN("er: layer switch failed: %d", rc);
        return rc;
    }
    return ZMK_BEHAVIOR_OPAQUE;
}

static int on_keymap_binding_released(struct zmk_behavior_binding *binding,
                                      struct zmk_behavior_binding_event event) {
    ARG_UNUSED(binding);
    ARG_UNUSED(event);
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api behavior_er_lang_driver_api = {
    .binding_pressed = on_keymap_binding_pressed,
    .binding_released = on_keymap_binding_released,
};

#define ER_LANG_INST(n)                                                                            \
    BEHAVIOR_DT_INST_DEFINE(n, NULL, NULL, NULL, NULL, POST_KERNEL,                                \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &behavior_er_lang_driver_api);

DT_INST_FOREACH_STATUS_OKAY(ER_LANG_INST)

#endif
