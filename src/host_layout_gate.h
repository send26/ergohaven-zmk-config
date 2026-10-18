#pragma once

#include <stdbool.h>

/**
 * @brief Whether the latest 0xAE request received a matching 0xAF.
 *
 * @return true after a confirmed layout switch, and before any request.
 *         false after a send failure or ACK timeout. The `en` macro's
 *         key reads this so a timed-out switch does not type a scancode.
 *         Safe to call from any thread.
 */
bool zmk_host_layout_confirmed(void);
