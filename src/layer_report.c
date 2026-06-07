#include <raw_hid/events.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/keymap.h>

#include <zephyr/logging/log.h>
LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#define HID_CMD_LAYER 0xAD
#define HID_CMD_LAYOUT 0xAC
#define LAYER_EN 0
#define LAYER_RU 1

static struct k_work_delayable layer_report_work;
static uint8_t last_reported_layer = 0xFF;
static uint8_t layer_report[CONFIG_RAW_HID_REPORT_SIZE];

static void send_layer_report(struct k_work *work) {
    ARG_UNUSED(work);

    zmk_keymap_layer_index_t layer = zmk_keymap_highest_layer_active();

    if (layer == last_reported_layer) {
        return;
    }

    last_reported_layer = layer;

    memset(layer_report, 0, sizeof(layer_report));
    layer_report[0] = HID_CMD_LAYER;
    layer_report[1] = (uint8_t)layer;

    LOG_INF("Sending layer report: %u", layer);

    raise_raw_hid_sent_event((struct raw_hid_sent_event){
        .data = layer_report,
        .length = CONFIG_RAW_HID_REPORT_SIZE,
    });
}

static int layer_state_changed_listener(const zmk_event_t *eh) {
    struct zmk_layer_state_changed *event = as_zmk_layer_state_changed(eh);

    if (event == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    k_work_reschedule(&layer_report_work, K_MSEC(CONFIG_ZMK_LAYER_REPORT_DEBOUNCE_MS));
    return ZMK_EV_EVENT_BUBBLE;
}

static int layer_report_init(void) {
    k_work_init_delayable(&layer_report_work, send_layer_report);
    k_work_schedule(&layer_report_work, K_MSEC(1000));
    return 0;
}

SYS_INIT(layer_report_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);

ZMK_LISTENER(layer_report_listener, layer_state_changed_listener);
ZMK_SUBSCRIPTION(layer_report_listener, zmk_layer_state_changed);

static int raw_hid_received_event_listener(const zmk_event_t *eh) {
    struct raw_hid_received_event *event = as_raw_hid_received_event(eh);
    if (event == NULL || event->length < 2) {
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

ZMK_LISTENER(layer_sync_listener, raw_hid_received_event_listener);
ZMK_SUBSCRIPTION(layer_sync_listener, raw_hid_received_event);
