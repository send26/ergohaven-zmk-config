#pragma once

#include <stdbool.h>

/**
 * @brief Host focus bit from Raw HID 0xB0.
 *
 * @return true when the frontmost app is Omnissa Horizon. Symbol keys then
 *         send Alt+numpad, and E+R holds left Alt+Shift. false means Mac
 *         apps. Safe to call from any thread; the value is one atomic word.
 */
bool zmk_horizon_active(void);
