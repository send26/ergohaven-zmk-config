#pragma once

#include <stdint.h>

/*
 * Raw HID, usage page 0xFF60, 32-byte reports.
 * Some stacks prepend a 0 report id; parsers accept that prefix.
 *
 * 0xAC  host → keyboard   layout index (0 ABC, 1 Russian)
 * 0xAD  keyboard → host   active layer
 * 0xAE  keyboard → host   layout request: index, non-zero sequence
 * 0xAF  host → keyboard   layout ACK: index, sequence
 * 0xB0  host → keyboard   focus (0 Mac, 1 Horizon)
 * 0xB1  keyboard → host   glyph: id, non-zero sequence
 * 0xB2  host → keyboard   glyph ACK: id, sequence
 *
 * A wait token is one 16-bit word, (id << 8) | sequence, so the HID
 * thread and the key thread never observe a torn pair. Sequence 0 is
 * reserved: the idle token is 0, and 0 is not a valid request id.
 */

#define HID_CMD_LAYOUT 0xAC
#define HID_CMD_LAYER 0xAD
#define HID_CMD_HOST_LAYOUT 0xAE
#define HID_CMD_HOST_LAYOUT_ACK 0xAF
#define HID_CMD_HORIZON 0xB0
#define HID_CMD_SYM_GLYPH 0xB1
#define HID_CMD_SYM_ACK 0xB2

#define LAYER_EN 0
#define LAYER_RU 1
#define LAYER_SYM 2

static inline uint8_t hid_next_seq(uint8_t seq) {
    uint8_t next = (uint8_t)(seq + 1U);

    if (next == 0U) {
        next = 1U;
    }
    return next;
}

static inline uint16_t hid_wait_token(uint8_t id, uint8_t seq) {
    return (uint16_t)(((uint16_t)id << 8) | seq);
}

/* Index of the command byte, or -1. payload_len is the count after that byte. */
static inline int hid_frame_at(const uint8_t *data, uint8_t length, uint8_t cmd,
                               uint8_t payload_len) {
    uint8_t direct;
    uint8_t prefixed;

    if (data == NULL || payload_len > 30U) {
        return -1;
    }
    direct = (uint8_t)(1U + payload_len);
    prefixed = (uint8_t)(direct + 1U);
    if (length >= direct && data[0] == cmd) {
        return 0;
    }
    if (length >= prefixed && data[0] == 0U && data[1] == cmd) {
        return 1;
    }
    return -1;
}
