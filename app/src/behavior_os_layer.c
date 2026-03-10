#include <zephyr/kernel.h>
#include <zephyr/init.h>
#include <zmk/keymap.h>
#include <zmk/event_manager.h>
#include <zmk/events/ble_active_profile_changed.h>
#include <zmk/ble.h>

static void update_os_layers(uint8_t profile) {
    switch (profile) {
        case 0:
            // Профиль 0 (например, ПК) - оставляем только базовый слой (0)
            zmk_keymap_layer_deactivate(5); // Отключаем русский слой (если он под номером 1)
            zmk_keymap_layer_deactivate(6);
            zmk_keymap_layer_activate(0);
            
            // Если у вас несколько доп. слоев, отключаем их все
            // zmk_keymap_layer_deactivate(2);
            break;
        case 1:
            zmk_keymap_layer_deactivate(0); // Отключаем русский слой (если он под номером 1)
            zmk_keymap_layer_deactivate(1);
            zmk_keymap_layer_activate(5);
            break;
        // case 2:
            // Профиль 2 (например, Планшет) - можно настроить отдельно
            // zmk_keymap_layer_activate(2);
            // break;
        // Добавьте case для других профилей при необходимости
    }
}

// Слушатель событий срабатывает при смене профиля
static int os_layer_listener_cb(const zmk_event_t *eh) {
    const struct zmk_ble_active_profile_changed *ev =
        as_zmk_ble_active_profile_changed(eh);
    if (ev) {
        update_os_layers(ev->index);
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(os_layer_listener, os_layer_listener_cb);
ZMK_SUBSCRIPTION(os_layer_listener, zmk_ble_active_profile_changed);

// Инициализация при старте клавиатуры
static int behavior_os_layer_init(void) {
    update_os_layers(zmk_ble_active_profile_index());
    return 0;
}

SYS_INIT(behavior_os_layer_init, APPLICATION, 95);