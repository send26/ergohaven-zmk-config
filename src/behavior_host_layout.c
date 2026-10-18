/*
 * Ask the host to switch input source over Raw HID (0xAE + non-zero sequence),
 * then wait for 0xAF echoing that index and sequence. Used by to_en/to_ru so
 * the `en` macro types on ABC and returns to Russian. No host-side sleep: the
 * daemon TIS-selects and ACKs immediately. Timeout is only a hang-guard if
 * the host is gone.
 *
 * The key thread blocks for at most HOST_LAYOUT_ACK_TIMEOUT_MS. Do not add
 * another sleep here.
 */

#define DT_DRV_COMPAT zmk_behavior_host_layout

#include <drivers/behavior.h>
#include <raw_hid/events.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include <zmk/behavior.h>

#include "hid_cmd.h"
#include "host_layout_gate.h"

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#define HOST_LAYOUT_ACK_TIMEOUT_MS 500

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

static uint8_t host_layout_report[CONFIG_RAW_HID_REPORT_SIZE];
static uint8_t host_layout_seq;
static atomic_t host_layout_wait = ATOMIC_INIT(0);
static atomic_t host_layout_ok = ATOMIC_INIT(1);
static K_SEM_DEFINE(host_layout_ack_sem, 0, 1);

bool zmk_host_layout_confirmed(void) { return atomic_get(&host_layout_ok) != 0; }

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

static int on_host_layout_ack(const zmk_event_t *eh) {
    const struct raw_hid_received_event *event = as_raw_hid_received_event(eh);
    int at;
    atomic_val_t expected;

    if (event == NULL || event->data == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    at = hid_frame_at(event->data, event->length, HID_CMD_HOST_LAYOUT_ACK, 2);
    if (at < 0) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    expected = atomic_get(&host_layout_wait);
    if (expected != 0 &&
        (uint16_t)expected == hid_wait_token(event->data[at + 1], event->data[at + 2])) {
        k_sem_give(&host_layout_ack_sem);
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(host_layout_ack, on_host_layout_ack);
ZMK_SUBSCRIPTION(host_layout_ack, raw_hid_received_event);

static int on_keymap_binding_pressed(struct zmk_behavior_binding *binding,
                                     struct zmk_behavior_binding_event event) {
    uint8_t index = (uint8_t)binding->param1;
    int rc;

    ARG_UNUSED(event);
    if (index > 1) {
        LOG_ERR("host_layout: invalid index %u", index);
        return -EINVAL;
    }

    host_layout_seq = hid_next_seq(host_layout_seq);
    atomic_set(&host_layout_wait, (atomic_val_t)hid_wait_token(index, host_layout_seq));
    memset(host_layout_report, 0, sizeof(host_layout_report));
    host_layout_report[0] = HID_CMD_HOST_LAYOUT;
    host_layout_report[1] = index;
    host_layout_report[2] = host_layout_seq;
    k_sem_reset(&host_layout_ack_sem);
    rc = raise_raw_hid_sent_event((struct raw_hid_sent_event){
        .data = host_layout_report,
        .length = CONFIG_RAW_HID_REPORT_SIZE,
    });
    if (rc != 0) {
        atomic_set(&host_layout_wait, 0);
        atomic_set(&host_layout_ok, 0);
        LOG_WRN("host_layout: HID send failed: %d", rc);
        return rc;
    }

    rc = k_sem_take(&host_layout_ack_sem, K_MSEC(HOST_LAYOUT_ACK_TIMEOUT_MS));
    atomic_set(&host_layout_wait, 0);
    if (rc != 0) {
        /* `&host_key` in the `en` macro reads this and does not type. */
        atomic_set(&host_layout_ok, 0);
        LOG_WRN("host_layout: ACK timeout after %u ms (index %u)", HOST_LAYOUT_ACK_TIMEOUT_MS,
                index);
        return -ETIMEDOUT;
    }
    atomic_set(&host_layout_ok, 1);
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
