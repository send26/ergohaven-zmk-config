/*
 * Ask the host to switch input source over Raw HID (0xAE), then wait for ACK
 * 0xAF. Used by to_en/to_ru so the `en` macro types on ABC and returns to
 * Russian. No host-side sleep: the daemon TIS-selects and ACKs immediately.
 * Timeout is only a hang-guard if the host is gone.
 */

#define DT_DRV_COMPAT zmk_behavior_host_layout

#include <drivers/behavior.h>
#include <raw_hid/events.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zmk/behavior.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#define HID_CMD_HOST_LAYOUT 0xAE
#define HID_CMD_HOST_LAYOUT_ACK 0xAF
#define HOST_LAYOUT_ACK_TIMEOUT_MS 500

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

static uint8_t host_layout_report[CONFIG_RAW_HID_REPORT_SIZE];
static K_SEM_DEFINE(host_layout_ack_sem, 0, 1);

#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)

static const struct behavior_parameter_value_metadata param_values[] = {
    {
        .value = 0,
        .display_name = "ABC",
        .type = BEHAVIOR_PARAMETER_VALUE_TYPE_VALUE,
    },
    {
        .value = 1,
        .display_name = "Russian",
        .type = BEHAVIOR_PARAMETER_VALUE_TYPE_VALUE,
    },
};

static const struct behavior_parameter_metadata_set param_metadata_set[] = {{
    .param1_values = param_values,
    .param1_values_len = ARRAY_SIZE(param_values),
}};

static const struct behavior_parameter_metadata metadata = {
    .sets_len = ARRAY_SIZE(param_metadata_set),
    .sets = param_metadata_set,
};

#endif

static uint8_t host_layout_cmd(const uint8_t *data, uint8_t length) {
    if (length >= 1 && data[0] == HID_CMD_HOST_LAYOUT_ACK) {
        return data[0];
    }
    if (length >= 2 && data[0] == 0 && data[1] == HID_CMD_HOST_LAYOUT_ACK) {
        return data[1];
    }
    return 0;
}

static int on_host_layout_ack(const zmk_event_t *eh) {
    struct raw_hid_received_event *event = as_raw_hid_received_event(eh);
    if (event == NULL || event->data == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    if (host_layout_cmd(event->data, event->length) != HID_CMD_HOST_LAYOUT_ACK) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    k_sem_give(&host_layout_ack_sem);
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(host_layout_ack, on_host_layout_ack);
ZMK_SUBSCRIPTION(host_layout_ack, raw_hid_received_event);

static int on_keymap_binding_pressed(struct zmk_behavior_binding *binding,
                                     struct zmk_behavior_binding_event event) {
    ARG_UNUSED(event);
    uint8_t index = (uint8_t)binding->param1;
    if (index > 1) {
        LOG_ERR("host_layout: invalid index %u", index);
        return -EINVAL;
    }

    memset(host_layout_report, 0, sizeof(host_layout_report));
    host_layout_report[0] = HID_CMD_HOST_LAYOUT;
    host_layout_report[1] = index;

    k_sem_reset(&host_layout_ack_sem);
    LOG_INF("Host layout HID 0xAE index %u", index);
    raise_raw_hid_sent_event((struct raw_hid_sent_event){
        .data = host_layout_report,
        .length = CONFIG_RAW_HID_REPORT_SIZE,
    });

    if (k_sem_take(&host_layout_ack_sem, K_MSEC(HOST_LAYOUT_ACK_TIMEOUT_MS)) != 0) {
        LOG_WRN("host_layout: ACK 0xAF timeout after %u ms (index %u)", HOST_LAYOUT_ACK_TIMEOUT_MS,
                index);
    }
    return ZMK_BEHAVIOR_OPAQUE;
}

static int on_keymap_binding_released(struct zmk_behavior_binding *binding,
                                      struct zmk_behavior_binding_event event) {
    ARG_UNUSED(binding);
    ARG_UNUSED(event);
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api behavior_host_layout_driver_api = {
    .binding_pressed = on_keymap_binding_pressed,
    .binding_released = on_keymap_binding_released,
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
    .parameter_metadata = &metadata,
#endif
};

BEHAVIOR_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL, CONFIG_KERNEL_INIT_PRIORITY_DEFAULT,
                        &behavior_host_layout_driver_api);

#endif
