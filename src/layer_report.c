#include <raw_hid/events.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/keymap.h>

#include <zephyr/logging/log.h>

#include "hid_cmd.h"

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

static struct k_work_delayable layer_report_work;
static uint8_t last_reported_layer = 0xFF;
static uint8_t layer_report[CONFIG_RAW_HID_REPORT_SIZE];
static bool layer_report_initialized;

static void send_layer_report(struct k_work *work) {
    zmk_keymap_layer_index_t layer = zmk_keymap_highest_layer_active();
    int rc;
    int delivered;

    ARG_UNUSED(work);
    if (layer == last_reported_layer) {
        return;
    }

    memset(layer_report, 0, sizeof(layer_report));
    layer_report[0] = HID_CMD_LAYER;
    layer_report[1] = (uint8_t)layer;

    delivered = -ENOTCONN;
    rc = raise_raw_hid_sent_event((struct raw_hid_sent_event){
        .data = layer_report,
        .length = CONFIG_RAW_HID_REPORT_SIZE,
        .status = &delivered,
    });
    if (rc != 0 || delivered != 0) {
        LOG_WRN("layer report was not delivered: %d", rc != 0 ? rc : delivered);
        if (delivered != -ENOTCONN) {
            k_work_reschedule(&layer_report_work, K_MSEC(CONFIG_ZMK_LAYER_REPORT_DEBOUNCE_MS));
        }
        return;
    }
    last_reported_layer = layer;
    LOG_INF("Sending layer report: %u", layer);
}

static void ensure_layer_report_init(void) {
    if (layer_report_initialized) {
        return;
    }

    k_work_init_delayable(&layer_report_work, send_layer_report);
    k_work_schedule(&layer_report_work, K_MSEC(1000));
    layer_report_initialized = true;
}

static int layer_state_changed_listener(const zmk_event_t *eh) {
    struct zmk_layer_state_changed *event = as_zmk_layer_state_changed(eh);

    if (event == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    ensure_layer_report_init();
    if (zmk_keymap_highest_layer_active() == LAYER_SYM) {
        k_work_reschedule(&layer_report_work, K_NO_WAIT);
    } else {
        k_work_reschedule(&layer_report_work, K_MSEC(CONFIG_ZMK_LAYER_REPORT_DEBOUNCE_MS));
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_report_listener, layer_state_changed_listener);
ZMK_SUBSCRIPTION(layer_report_listener, zmk_layer_state_changed);

static int raw_hid_received_event_listener(const zmk_event_t *eh) {
    const struct raw_hid_received_event *event = as_raw_hid_received_event(eh);
    int at;
    uint8_t target;
    int rc;

    if (event == NULL || event->data == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    ensure_layer_report_init();

    at = hid_frame_at(event->data, event->length, HID_CMD_LAYOUT, 1);
    if (at < 0) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    target = event->data[at + 1];
    if (target != LAYER_EN && target != LAYER_RU) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    if (zmk_keymap_layer_default() == target) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    rc = zmk_keymap_layer_to(target);
    if (rc != 0) {
        LOG_WRN("layer sync failed for %u: %d", target, rc);
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_sync_listener, raw_hid_received_event_listener);
ZMK_SUBSCRIPTION(layer_sync_listener, raw_hid_received_event);
