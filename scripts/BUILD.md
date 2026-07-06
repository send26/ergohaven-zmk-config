# Сборка и прошивка velvet qube ruen

> **Контекст для агента / продолжение работы:** см. [`docs/AGENT_CONTEXT.md`](../docs/AGENT_CONTEXT.md) — архитектура демонов, история sym/ru-en, тесты, известные баги.

Инструкция для `scripts/flash-qube-ruen.sh` — локальная сборка прошивки **velvet_v3_ui_qube_ruen** в Docker и копирование `.uf2` на Qube через USB bootloader.

## Что делает скрипт

`flash-qube-ruen.sh` — обёртка над `zmk-docker-build.sh`. Она:

1. Собирает прошивку `velvet_v3_ui_qube_ruen-ergohaven-zmk.uf2` в Docker (тот же поток, что CI ergohaven).
2. Ждёт появления тома bootloader `NRF52BOOT`.
3. Копирует `.uf2` на Qube — устройство перезагружается с новой прошивкой.

Целевая конфигурация (как в `build.yaml`):

| Параметр | Значение |
|----------|----------|
| Board | `ergohaven` |
| Shield | `velvet_v3_ui_qube qube dongle_screen raw_hid_adapter` |
| Keymap | `velvet_v3_ui_ruen` |
| Конфиг | `config/velvet_v3_ui.conf` + `config/velvet_v3_ui_ruen.keymap` |
| Артефакт | `build/artifacts/velvet_v3_ui_qube_ruen-ergohaven-zmk.uf2` |

В прошивке включены Raw HID и синхронизация слоёв (`CONFIG_ZMK_LAYER_REPORT`).

---

## Требования

- **macOS** (скрипт ожидает `/Volumes/NRF52BOOT`)
- **Docker Desktop** — установлен и запущен (`docker info` без ошибок)
- **Qube** (velvet v3 ui) с USB-кабелем
- Права на запуск: `chmod +x scripts/flash-qube-ruen.sh` (обычно уже есть)

Первый запуск скачивает образ `zmkfirmware/zmk-build-arm:stable` и инициализирует `.zmk-workspace/` — это может занять **15–30 минут**. Повторные сборки — обычно **2–5 минут**.

---

## Быстрый старт (сборка + прошивка)

```bash
cd ~/zmk/ergohaven-zmk-config
```

### 1. Отредактировать конфиг (если нужно)

Основные файлы:

- `config/velvet_v3_ui_ruen.keymap` — слои, макросы, комбо
- `config/velvet_v3_ui.conf` — опции прошивки (sleep, Raw HID, layer report)
- `config/keys_ru.h` — русские символы

После правок keymap обновите метаданные слоёв для демона синхронизации:

```bash
python3 scripts/parse_keymap_layers.py -k config/velvet_v3_ui_ruen.keymap \
  -o scripts/layers_velvet_v3_ui_ruen.json
```

### 2. Перевести Qube в режим bootloader

1. Подключите Qube по USB к Mac.
2. **Дважды быстро** нажмите кнопку reset на Qube (double-tap reset).
3. В Finder должен появиться диск **`NRF52BOOT`** (`/Volumes/NRF52BOOT`).

Если диск не появился — отключите/подключите USB, повторите double-tap.

### 3. Запустить скрипт

```bash
./scripts/flash-qube-ruen.sh
```

Скрипт сначала соберёт прошивку, затем дождётся `NRF52BOOT` (до 180 с) и скопирует файл. Qube перезагрузится автоматически.

Успешный вывод заканчивается строкой:

```
Done. Qube should reboot with the new firmware shortly.
```

---

## Режимы работы

### Только сборка (без прошивки)

```bash
./scripts/flash-qube-ruen.sh --build-only
```

Результат: `build/artifacts/velvet_v3_ui_qube_ruen-ergohaven-zmk.uf2`

Прошить вручную позже:

```bash
cp build/artifacts/velvet_v3_ui_qube_ruen-ergohaven-zmk.uf2 /Volumes/NRF52BOOT/
```

### Bootloader уже подключён — не ждать

```bash
./scripts/flash-qube-ruen.sh --no-wait
```

Если `NRF52BOOT` нет — скрипт сразу завершится с ошибкой.

### Увеличить время ожидания bootloader

```bash
./scripts/flash-qube-ruen.sh --wait 300
```

По умолчанию: 180 секунд (`WAIT_TIMEOUT`).

### Справка

```bash
./scripts/flash-qube-ruen.sh --help
```

---

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `NRF52_BOOT_MOUNT` | `/Volumes/NRF52BOOT` | Путь к тому bootloader |
| `WAIT_TIMEOUT` | `180` | Секунды ожидания `NRF52BOOT` |

Пример:

```bash
NRF52_BOOT_MOUNT=/Volumes/NRF52BOOT WAIT_TIMEOUT=60 ./scripts/flash-qube-ruen.sh
```

---

## Типичный рабочий цикл

```
Редактируешь keymap/conf
        ↓
(parse_keymap_layers.py — если менялись слои)
        ↓
Double-tap reset на Qube → NRF52BOOT
        ↓
./scripts/flash-qube-ruen.sh
        ↓
Qube перезагружается с новой прошивкой
        ↓
(опционально) перезапуск обоих демонов для синхронизации Ru/En
```

---

## Синхронизация раскладки Ru/En (после прошивки)

Два независимых демона:

| Демон | Роль | Конфиг |
|-------|------|--------|
| `zmk_hid_daemon.py` | Raw HID: слой клавиатуры → SketchyBar; Mac раскладка → слой на клавиатуре | `layout_sync.json` |
| `zmk_mac_layout_daemon.py` | Ctrl+Shift+1/2 с клавиатуры → ABC / Russian в macOS | `mac_layout.json` |

Переключение раскладки macOS делает **только** `zmk_mac_layout_daemon` (через CGEventTap). Демон синхронизации слоёв **не** трогает TIS/macime — только читает текущую раскладку и шлёт индекс на клавиатуру.

### Запуск вручную

```bash
./scripts/run_zmk_hid_daemon.sh -v
./scripts/run_zmk_mac_layout_daemon.sh -v
```

### launchd (оба агента)

На современных macOS **`launchctl load` устарел** — при уже загруженном агенте даёт `Load failed: 5: Input/output error`. Используйте скрипт установки:

```bash
chmod +x scripts/install-zmk-daemons.sh
./scripts/install-zmk-daemons.sh
```

Или вручную (после `cp` plist в `~/Library/LaunchAgents/`):

```bash
UID_NUM=$(id -u)
# первая установка:
launchctl bootstrap gui/$UID_NUM ~/Library/LaunchAgents/com.senders.zmk-layer-daemon.plist
launchctl bootstrap gui/$UID_NUM ~/Library/LaunchAgents/com.senders.zmk-mac-layout-daemon.plist

# перезагрузка после правки plist:
launchctl bootout gui/$UID_NUM/com.senders.zmk-layer-daemon
launchctl bootstrap gui/$UID_NUM ~/Library/LaunchAgents/com.senders.zmk-layer-daemon.plist

# быстрый перезапуск без правки plist:
launchctl kickstart -k gui/$UID_NUM/com.senders.zmk-layer-daemon
launchctl kickstart -k gui/$UID_NUM/com.senders.zmk-mac-layout-daemon
```

Проверить, что агент уже работает:

```bash
launchctl print gui/$(id -u)/com.senders.zmk-layer-daemon | grep 'state ='
launchctl print gui/$(id -u)/com.senders.zmk-mac-layout-daemon | grep 'state ='
```

Если `state = running` — повторный `load` не нужен.

Логи:

- `~/Library/Logs/zmk-layer-daemon.log`
- `~/Library/Logs/zmk-mac-layout-daemon.log`

### Требования macOS

- **Accessibility** для `zmk_mac_layout_daemon` (CGEventTap). При запуске через launchd процесс — это **`/usr/local/bin/python3`**, не Terminal/Cursor: System Settings → Privacy & Security → Accessibility → добавьте Python.
- В системных настройках клавиатуры: горячие клавиши **Ctrl+Shift+1** → ABC, **Ctrl+Shift+2** → Russian (макросы `to_en` / `to_ru` в прошивке шлют те же сочетания).

Настройки: `scripts/layout_sync.json`, `scripts/mac_layout.json`, `scripts/keyboards.json`, `scripts/layers_velvet_v3_ui_ruen.json`.

Тесты: `./scripts/run_daemon_tests.sh`

Ручной тест переключения base↔ru (без мусорных символов вроде `"`):

```bash
python3 scripts/test_layer_switch.py --print-manual   # чеклист
python3 scripts/test_layer_switch_manual.py           # интерактивно в TextEdit
```

---

## Низкоуровневая сборка (`zmk-docker-build.sh`)

`flash-qube-ruen.sh` внутри вызывает:

```bash
./scripts/zmk-docker-build.sh \
  --artifact velvet_v3_ui_qube_ruen-ergohaven-zmk \
  --output build/artifacts/velvet_v3_ui_qube_ruen-ergohaven-zmk.uf2
```

Другие цели (например, правая половина без qube):

```bash
./scripts/zmk-docker-build.sh \
  --shield "velvet_v3_ui_right raw_hid_adapter" \
  --keymap velvet_v3_ui_ruen \
  --artifact velvet_v3_ui_right_ruen-ergohaven-zmk
```

Обновить зависимости ZMK в workspace:

```bash
./scripts/zmk-docker-build.sh --refresh
```

Полный список опций: `./scripts/zmk-docker-build.sh --help`

---

## Устранение неполадок

### `Docker daemon is not running`

Запустите Docker Desktop, дождитесь зелёного статуса, повторите команду.

### `Timed out waiting for /Volumes/NRF52BOOT`

- Qube не в bootloader: сделайте double-tap reset.
- Плохой USB-кабель/порт — попробуйте другой.
- Увеличьте ожидание: `--wait 300`.
- Соберите заранее: `--build-only`, потом вручную скопируйте `.uf2` когда появится диск.

### Сборка падает с ошибкой devicetree / keymap

Проверьте синтаксис `config/velvet_v3_ui_ruen.keymap`. Типичные проблемы:

- `#include` до `<behaviors.dtsi>` для файлов с `&kp`
- неверное число клавиш в слое
- дублирующиеся label в behaviors/macros

### Прошивка скопировалась, но клавиатура ведёт себя странно

- Убедитесь, что прошили именно qube ruen артефакт, а не другой `.uf2`.
- Сбросьте настройки ZMK (профиль `settings_reset` из `build.yaml`) только если понимаете последствия.
- Перезапустите оба демона (`zmk-layer-daemon`, `zmk-mac-layout-daemon`) после смены слоёв в keymap.

### Первая сборка «висит» долго

Нормально: `west update` качает Zephyr и модули в `.zmk-workspace/`. Следующие сборки быстрее.

---

## Связанные файлы

| Файл | Роль |
|------|------|
| `scripts/flash-qube-ruen.sh` | Сборка + копирование на NRF52BOOT |
| `scripts/zmk-docker-build.sh` | Универсальная Docker-сборка |
| `config/velvet_v3_ui_ruen.keymap` | Раскладка ru/en |
| `config/velvet_v3_ui.conf` | Kconfig прошивки |
| `build.yaml` | Список целей CI (ergohaven) |
| `scripts/zmk_hid_daemon.py` | Синхронизация слоёв клавиатура ↔ macOS (Raw HID) |
| `scripts/zmk_mac_layout_daemon.py` | Ctrl+Shift+1/2 → системная раскладка |
| `scripts/zmk_tis.py` | Общие TIS/macime helpers |
| `docs/AGENT_CONTEXT.md` | Полный контекст для агента (архитектура, история, тесты) |
| `.zmk-workspace/` | Кэш west/Zephyr (не коммитится) |
| `build/artifacts/*.uf2` | Готовые прошивки (не коммитятся) |
