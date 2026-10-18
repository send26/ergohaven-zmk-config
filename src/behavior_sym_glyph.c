/*
 * Symbol glyph with two destinations.
 *
 * Horizon (host set Raw HID 0xB0 = 1): left Alt + numpad digits. OEM codes
 * 32–126 match on CP437 and CP866, so the Windows layout does not matter.
 * № and ё use a leading zero (Windows-1251: Alt+0185 / Alt+0184).
 * 15 ms between digits so a remote session does not merge them.
 * Explicit modifiers are released for the sequence and restored after.
 *
 * Mac, Russian base layer (or a glyph with no US scancode): Raw HID 0xB1.
 * The host inserts one Unicode character and ACKs 0xB2. Input source stays.
 *
 * Mac, English base layer: the US scancode, pressed until release.
 *
 * The key thread sleeps for the Alt sequence or for the Unicode ACK.
 * Worst case is SYM_ACK_TIMEOUT_MS, or one Alt code:
 *   SYM_TAP_MS (modifier settle) + SYM_TAP_MS (Alt down)
 *   + alt_len * SYM_TAP_MS + (alt_len - 1) * SYM_GAP_MS.
 * Do not add another sleep on this thread. 15 ms is the measured floor
 * before Horizon merges numpad digits.
 */

#define DT_DRV_COMPAT zmk_behavior_sym_glyph

#include <drivers/behavior.h>
#include <dt-bindings/zmk/keys.h>
#include <raw_hid/events.h>
#include <string.h>
#include <sym_glyph.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/keycode_state_changed.h>
#include <zmk/hid.h>
#include <zmk/keymap.h>

#include "hid_cmd.h"
#include "horizon_mode.h"

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#define SYM_ACK_TIMEOUT_MS 120
#define SYM_TAP_MS 10
#define SYM_GAP_MS 15
#define SYM_HELD_MAX 256

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

struct sym_def {
    uint32_t us;
    uint8_t alt_len;
    uint8_t alt[4];
};

/* Alt digits are OEM decimal, matching kanata hzsym. Index is SYM_* id. */
static const struct sym_def sym_glyphs[SYM_GLYPH_COUNT] = {
    [SYM_HASH] = {HASH, 2, {3, 5}},
    [SYM_LT] = {LT, 2, {6, 0}},
    [SYM_EQUAL] = {EQUAL, 2, {6, 1}},
    [SYM_GT] = {GT, 2, {6, 2}},
    [SYM_ASTRK] = {ASTRK, 2, {4, 2}},
    [SYM_CARET] = {CARET, 2, {9, 4}},
    [SYM_DQT] = {DQT, 2, {3, 4}},
    [SYM_GRAVE] = {GRAVE, 2, {9, 6}},
    [SYM_SQT] = {SQT, 2, {3, 9}},
    [SYM_LBKT] = {LBKT, 2, {9, 1}},
    [SYM_RBKT] = {RBKT, 2, {9, 3}},
    [SYM_MINUS] = {MINUS, 2, {4, 5}},
    [SYM_AMPS] = {AMPS, 2, {3, 8}},
    [SYM_LPAR] = {LPAR, 2, {4, 0}},
    [SYM_RPAR] = {RPAR, 2, {4, 1}},
    [SYM_PLUS] = {PLUS, 2, {4, 3}},
    [SYM_PRCNT] = {PRCNT, 2, {3, 7}},
    [SYM_LBRC] = {LBRC, 3, {1, 2, 3}},
    [SYM_UNDER] = {UNDER, 2, {9, 5}},
    [SYM_RBRC] = {RBRC, 3, {1, 2, 5}},
    [SYM_SEMI] = {SEMI, 2, {5, 9}},
    [SYM_BSLH] = {BSLH, 2, {9, 2}},
    [SYM_TILDE] = {TILDE, 3, {1, 2, 6}},
    [SYM_COLON] = {COLON, 2, {5, 8}},
    [SYM_FSLH] = {FSLH, 2, {4, 7}},
    [SYM_PIPE] = {PIPE, 3, {1, 2, 4}},
    [SYM_AT] = {AT, 2, {6, 4}},
    [SYM_DOLLAR] = {DOLLAR, 2, {3, 6}},
    [SYM_COMMA] = {COMMA, 2, {4, 4}},
    [SYM_DOT] = {DOT, 2, {4, 6}},
    [SYM_QMARK] = {QMARK, 2, {6, 3}},
    [SYM_EXCL] = {EXCL, 2, {3, 3}},
    /* Windows-1251, leading zero. Russian guest only. */
    [SYM_NUMERO] = {0, 4, {0, 1, 8, 5}},
    [SYM_IO] = {0, 4, {0, 1, 8, 4}},
};

static const uint32_t kp_digit[] = {
    KP_N0, KP_N1, KP_N2, KP_N3, KP_N4, KP_N5, KP_N6, KP_N7, KP_N8, KP_N9,
};

static const uint32_t mod_keycodes[] = {
    LEFT_CONTROL, LEFT_SHIFT, LEFT_ALT, LEFT_GUI,
    RIGHT_CONTROL, RIGHT_SHIFT, RIGHT_ALT, RIGHT_GUI,
};

static atomic_t sym_wait = ATOMIC_INIT(0);
static uint8_t sym_seq;
static uint8_t sym_report[CONFIG_RAW_HID_REPORT_SIZE];
static uint32_t sym_held[SYM_HELD_MAX];
static uint16_t sym_drop_count;
static K_SEM_DEFINE(sym_ack_sem, 0, 1);

static int on_sym_hid(const zmk_event_t *eh) {
    const struct raw_hid_received_event *event = as_raw_hid_received_event(eh);
    int at;
    atomic_val_t expected;

    if (event == NULL || event->data == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    at = hid_frame_at(event->data, event->length, HID_CMD_SYM_ACK, 2);
    if (at < 0) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    expected = atomic_get(&sym_wait);
    if (expected != 0 &&
        (uint16_t)expected == hid_wait_token(event->data[at + 1], event->data[at + 2])) {
        k_sem_give(&sym_ack_sem);
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(sym_glyph_hid, on_sym_hid);
ZMK_SUBSCRIPTION(sym_glyph_hid, raw_hid_received_event);

static int key_event(uint32_t code, bool pressed, int64_t timestamp) {
    int rc = raise_zmk_keycode_state_changed_from_encoded(code, pressed, timestamp);

    if (rc == 0 || pressed) {
        return rc;
    }
    rc = raise_zmk_keycode_state_changed_from_encoded(code, false, timestamp);
    if (rc != 0) {
        LOG_WRN("sym: key release failed: %d", rc);
    }
    return rc;
}

static int tap_key(uint32_t code, int64_t timestamp) {
    int rc = key_event(code, true, timestamp);

    if (rc != 0) {
        return rc;
    }
    k_msleep(SYM_TAP_MS);
    return key_event(code, false, timestamp);
}

static void release_us(uint32_t position, int64_t timestamp) {
    if (position >= SYM_HELD_MAX || sym_held[position] == 0) {
        return;
    }
    if (key_event(sym_held[position], false, timestamp) != 0) {
        return;
    }
    sym_held[position] = 0;
}

static void restore_mods(const bool *saved, int64_t timestamp) {
    for (uint8_t i = 0; i < ARRAY_SIZE(mod_keycodes); i++) {
        if (saved[i] && key_event(mod_keycodes[i], true, timestamp) != 0) {
            LOG_WRN("sym: modifier restore failed");
        }
    }
}

static void send_alt_code(const struct sym_def *def, int64_t timestamp) {
    bool saved[ARRAY_SIZE(mod_keycodes)];
    bool released_mod = false;
    uint8_t count;
    uint8_t sent = 0;

    if (def == NULL) {
        return;
    }

    for (uint8_t i = 0; i < ARRAY_SIZE(mod_keycodes); i++) {
        saved[i] = zmk_hid_mod_is_pressed((zmk_mod_t)i);
        if (!saved[i]) {
            continue;
        }
        if (key_event(mod_keycodes[i], false, timestamp) != 0) {
            saved[i] = false;
            LOG_WRN("sym: modifier release failed");
            continue;
        }
        released_mod = true;
    }
    if (released_mod) {
        k_msleep(SYM_TAP_MS);
    }

    if (key_event(LEFT_ALT, true, timestamp) != 0) {
        LOG_WRN("sym: Alt press failed");
        restore_mods(saved, timestamp);
        return;
    }
    k_msleep(SYM_TAP_MS);

    count = def->alt_len;
    if (count > sizeof(def->alt)) {
        count = (uint8_t)sizeof(def->alt);
    }
    for (uint8_t i = 0; i < count; i++) {
        uint8_t digit = def->alt[i];

        if (digit > 9) {
            continue;
        }
        if (sent > 0) {
            k_msleep(SYM_GAP_MS);
        }
        if (tap_key(kp_digit[digit], timestamp) != 0) {
            LOG_WRN("sym: numpad digit failed");
            break;
        }
        sent++;
    }

    if (key_event(LEFT_ALT, false, timestamp) != 0) {
        LOG_WRN("sym: Alt release failed");
    }
    restore_mods(saved, timestamp);
}

static int request_unicode(uint8_t id) {
    int rc;

    sym_seq = hid_next_seq(sym_seq);
    atomic_set(&sym_wait, (atomic_val_t)hid_wait_token(id, sym_seq));
    memset(sym_report, 0, sizeof(sym_report));
    sym_report[0] = HID_CMD_SYM_GLYPH;
    sym_report[1] = id;
    sym_report[2] = sym_seq;
    k_sem_reset(&sym_ack_sem);
    rc = raise_raw_hid_sent_event((struct raw_hid_sent_event){
        .data = sym_report,
        .length = CONFIG_RAW_HID_REPORT_SIZE,
    });
    if (rc != 0) {
        atomic_set(&sym_wait, 0);
        return rc;
    }
    rc = k_sem_take(&sym_ack_sem, K_MSEC(SYM_ACK_TIMEOUT_MS));
    atomic_set(&sym_wait, 0);
    if (rc != 0) {
        return -ETIMEDOUT;
    }
    return 0;
}

static const struct sym_def *glyph_for(uint32_t id) {
    if (id == 0 || id >= SYM_GLYPH_COUNT) {
        return NULL;
    }
    if (sym_glyphs[id].alt_len == 0) {
        return NULL;
    }
    return &sym_glyphs[id];
}

static int on_keymap_binding_pressed(struct zmk_behavior_binding *binding,
                                     struct zmk_behavior_binding_event event) {
    const struct sym_def *def = glyph_for(binding->param1);
    int rc;

    if (def == NULL) {
        LOG_ERR("sym: unknown glyph %u", binding->param1);
        return -EINVAL;
    }

    release_us(event.position, event.timestamp);

    if (zmk_horizon_active()) {
        send_alt_code(def, event.timestamp);
        return ZMK_BEHAVIOR_OPAQUE;
    }
    if (zmk_keymap_layer_active(LAYER_RU) || def->us == 0) {
        rc = request_unicode((uint8_t)binding->param1);
        if (rc != 0) {
            if (sym_drop_count < UINT16_MAX) {
                sym_drop_count++;
            }
            LOG_WRN("sym glyph %u dropped (%d), count %u", binding->param1, rc, sym_drop_count);
        }
        return ZMK_BEHAVIOR_OPAQUE;
    }

    if (event.position >= SYM_HELD_MAX) {
        LOG_ERR("sym: position %u out of range", event.position);
        return -EINVAL;
    }
    rc = key_event(def->us, true, event.timestamp);
    if (rc != 0) {
        LOG_WRN("sym: US key press failed: %d", rc);
        return rc;
    }
    sym_held[event.position] = def->us;
    return ZMK_BEHAVIOR_OPAQUE;
}

static int on_keymap_binding_released(struct zmk_behavior_binding *binding,
                                      struct zmk_behavior_binding_event event) {
    ARG_UNUSED(binding);
    release_us(event.position, event.timestamp);
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api behavior_sym_glyph_driver_api = {
    .binding_pressed = on_keymap_binding_pressed,
    .binding_released = on_keymap_binding_released,
};

#define SYM_GLYPH_INST(n)                                                                          \
    BEHAVIOR_DT_INST_DEFINE(n, NULL, NULL, NULL, NULL, POST_KERNEL,                                \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &behavior_sym_glyph_driver_api);

DT_INST_FOREACH_STATUS_OKAY(SYM_GLYPH_INST)

#endif
