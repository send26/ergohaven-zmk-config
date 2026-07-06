# Контекст проекта для агента (ergohaven-zmk-config)

Документ фиксирует состояние работы по **ru/en раскладке**, **sym-слою** и **синхронизации клавиатура ↔ macOS** на **Velvet v3 UI Qube** (пользователь `senders`, macOS). Обновлено: 2026-07-06.

---

## Цель

Клавиатура с прошивкой **velvet_v3_ui_ruen**:
- слои **base (en)** и **ru** для английского/русского ввода;
- sym-слои **sym** (layer 2) и **sym_ru** (layer 3) для символов `, \ : / |` и т.д.;
- двусторонняя синхронизация активного слоя с системной раскладкой macOS;
- **без мусорных символов** при переключении слоёв (в т.ч. `"` при base→ru).

---

## Текущая архитектура (два независимых демона)

```
┌─────────────────┐     Raw HID 0xAD (layer)      ┌──────────────────────┐
│  ZMK firmware   │ ────────────────────────────► │  zmk_hid_daemon.py   │
│  velvet_v3_ruen │                               │  (layer sync)        │
│                 │ ◄──────────────────────────── │                      │
│                 │     Raw HID 0xAC (layout idx)   │  • state.json        │
└────────┬────────┘                               │  • SketchyBar        │
         │                                        │  • Mac TIS на 0/1    │
         │ Ctrl+Shift+1/2 (только sym `en`)       └──────────┬───────────┘
         ▼                                                   │
┌─────────────────┐                               macOS input source notify
│ zmk_mac_layout  │ ◄── CGEventTap (HID only)                 │
│ _daemon.py      │     consume_shortcuts=true                ▼
└─────────────────┘                               System Settings layouts
```

| Компонент | Роль | Конфиг |
|-----------|------|--------|
| `scripts/zmk_hid_daemon.py` | Raw HID: отчёты слоя → `~/.cache/zmk_layer/state.json` + SketchyBar; при смене слоя **0/1** переключает Mac через TIS/macime; при смене раскладки в Mac → шлёт индекс на клавиатуру | `layout_sync.json` |
| `scripts/zmk_mac_layout_daemon.py` | Перехват **Ctrl+Shift+1** → ABC, **Ctrl+Shift+2** → Russian с HID-клавиатуры; глотает событие (`consume_shortcuts`) | `mac_layout.json` |
| `scripts/zmk_tis.py` | Общие TIS API + fallback `macime set` | — |

**Разделение ответственности (важно):**
- Переключение **base ↔ ru** (макросы `layer_en` / `layer_ru`) — **только смена слоя в прошивке**; Mac раскладку меняет **layer-демон** по Raw HID отчёту.
- **Ctrl+Shift+1/2** из прошивки остаются в макросах `to_en` / `to_ru` для sym-макроса `en` и Windows VM; их обрабатывает **mac-layout-демон** с `consume_shortcuts: true`.

---

## Прошивка (keymap)

Основной файл: `config/velvet_v3_ui_ruen.keymap`

### Слои (индексы)

| Index | ID | Назначение |
|-------|-----|------------|
| 0 | base | Английский слой |
| 1 | ru | Русский слой |
| 2 | sym | Символы на `&kp` (ABC Mac) |
| 3 | sym_ru | Символы с `&en` макросами (Russian Mac) |
| 4+ | nav, mouse, … | прочие |

### Переход на sym

- **base**: `&lt 2 BACKSPACE` → sym (layer 2)
- **ru**: `&lt 3 BACKSPACE` → sym_ru (layer 3)

### Макросы (критично)

```dts
layer_en: bindings = <&to 0>;          // БЕЗ &to_en — иначе мусор в тексте
layer_ru: bindings = <&to 1>;          // БЕЗ &to_ru — иначе печатается "

to_en:  bindings = <&kp LS(LC(N1))>, <&macro_press>;
to_ru:  bindings = <&kp LS(LC(N2))>;

en:     // sym: временно ABC → символ → обратно Russian
        bindings = <&to_en>, <&macro_press>, ..., <&to_ru>;
```

Общие макросы вынесены в `config/ruen.dtsi` (подключается из `op36_ruen.keymap`). Остальные ruen-keymap'ы дублируют те же правила inline.

### Почему убрали `to_ru` из `layer_ru`

На macOS раскладке **Russian** клавиша **Shift+2** даёт символ **`"`** (QUOTEDBL). Макрос `to_ru` шлёт **Ctrl+Shift+2**; если событие не перехвачено, в активное поле попадает `"`. Исправление: layer-переключение без HID-шорткатов; Mac layout — через демон.

### Raw HID в прошивке

- `src/layer_report.c` — шлёт `HID_CMD_LAYER (0xAD)` при смене слоя; для sym (layer 2) отчёт без debounce.
- Приём `HID_CMD_LAYOUT (0xAC)` — переключает клавиатуру на layer 0 или 1.

### Сборка / прошивка

```bash
./scripts/flash-qube-ruen.sh
# см. scripts/BUILD.md
```

После смены слоёв в keymap:
```bash
python3 scripts/parse_keymap_layers.py -k config/velvet_v3_ui_ruen.keymap \
  -o scripts/layers_velvet_v3_ui_ruen.json
```

---

## Демоны macOS

### Установка и перезапуск

```bash
./scripts/install-zmk-daemons.sh
```

**Не использовать** `launchctl load` — на новых macOS даёт `Load failed: 5` если агент уже загружен. Использовать `bootstrap` / `kickstart` (см. скрипт).

LaunchAgents:
- `scripts/com.senders.zmk-layer-daemon.plist`
- `scripts/com.senders.zmk-mac-layout-daemon.plist`

Логи:
- `~/Library/Logs/zmk-layer-daemon.log`
- `~/Library/Logs/zmk-mac-layout-daemon.log`

### Требования macOS

1. **Accessibility** для `/usr/local/bin/python3` (mac-layout-демон, CGEventTap) — не Terminal/Cursor, если демон запущен через launchd.
2. Системные шорткаты: Ctrl+Shift+1 → ABC, Ctrl+Shift+2 → Russian (для sym `en` и Windows).
3. `macime` по пути `/usr/local/bin/macime` (fallback переключения раскладки).

### Конфиги

**`scripts/layout_sync.json`**
```json
{
  "layouts": ["com.apple.keylayout.ABC", "com.apple.keylayout.Russian"],
  "macime_layouts": { "0": "ABC", "1": "Russian" },
  "sym_layers": [2, 3],
  "pause_sync_when_frontmost": ["Windows App"]
}
```
- `sym_layers` — на этих слоях демон **не** меняет Mac раскладку и **не** синхронизирует Mac→keyboard.

**`scripts/mac_layout.json`**
```json
{
  "shortcut_layouts": { "1": "ABC", "2": "Russian" },
  "consume_shortcuts": true,
  "hid_events_only": true
}
```

### Поведение layer-демона (детали)

1. **Keyboard → Mac**: Raw HID layer 0/1 → `switch_macime_layout()` → TIS, иначе macime.
2. **Mac → Keyboard**: notification input source → `send_layout_report(index)` если индекс изменился.
3. **Echo suppression**: `_suppress_mac_to_keyboard_until` (1.5 с) после keyboard-initiated Mac switch.
4. На sym-слоях (2, 3): пропуск Mac→keyboard sync.

Ожидаемые строки лога при base→ru:
```
Layer update [velvet_v3_ui_ruen]: ru (index 1)
Keyboard layer 1 → Mac com.apple.keylayout.Russian
```

---

## История попыток (не повторять без причины)

| Подход | Результат |
|--------|-----------|
| **zmk-unicode** (`&uc`) + Unicode Hex Input на sym | Слишком медленно (~100–500 ms); символы уходят до смены раскладки; мусор `#}πϐ*` |
| **Один демон** с sym session / grace timer / macime worker | Гонки, sym↔ru flicker при удержании Backspace, Russian залипал на ABC |
| **layer_ru + to_ru** (Ctrl+Shift+2 из прошивки) | Печать `"` при переходе на ru |
| **sym_layers: []** + dual sym в прошивке | sym на `&kp`, sym_ru с `&en`; Mac layout на sym не трогаем |

Текущий sym: два слоя в прошивке, Mac на sym не переключается автоматически; sym_ru использует `en` макрос для отдельных клавиш.

---

## Тесты

```bash
./scripts/run_daemon_tests.sh    # 20 тестов: layer switch, layer sync, mac shortcuts
./scripts/run_sym_tests.sh       # алиас на run_daemon_tests.sh
```

| Файл | Что проверяет |
|------|----------------|
| `scripts/test_layer_switch.py` | keymap: `layer_en`/`layer_ru` без шорткатов; демон переключает Mac на layer report; чеклист |
| `scripts/test_layer_switch_manual.py` | интерактивный ручной тест в TextEdit |
| `scripts/test_zmk_layer_sync.py` | Mac↔keyboard sync, pause apps |
| `scripts/test_zmk_mac_layout_daemon.py` | Ctrl+Shift+1/2, consume_shortcuts |
| `scripts/test_zmk_hid_daemon_sym.py` | **УСТАРЕЛ** — monolithic sym debounce; не запускать без рефакторинга |
| `scripts/test_sym_unicode.py` | ручной/аналитический тест sym unicode; `--analyze-daemon-log` |

Ручной чеклист:
```bash
python3 scripts/test_layer_switch.py --print-manual
python3 scripts/test_layer_switch_manual.py
```

---

## Известные проблемы

1. **TIS ctypes warmup** в `zmk_tis.py` — на части вызовов `NSInvalidArgumentException` (`-[... count]`); переключение работает через **macime fallback**. Лог: `TIS switch failed ... macime →`.
2. **sym-слой** — надёжность символов `, \ : / |` на всех комбинациях base/ru + Mac layout может требовать доработки; autotests sym unicode в `test_sym_unicode.py`.
3. **sym_ru flicker** в логе (быстрое sym_ru↔ru) при удержании `&lt 3 BACKSPACE` — поведение layer-tap, не демона.
4. Пути в plist захардкожены под `/Users/senders/zmk/ergohaven-zmk-config` — при переносе репо обновить.

---

## Карта файлов

| Путь | Роль |
|------|------|
| `config/velvet_v3_ui_ruen.keymap` | Основная раскладка Qube ruen |
| `config/ruen.dtsi` | Общие макросы ru/en |
| `config/velvet_v3_ui.conf` | Kconfig (Raw HID, layer report) |
| `src/layer_report.c` | HID отчёты слоя / приём layout |
| `scripts/zmk_hid_daemon.py` | Layer sync демон |
| `scripts/zmk_mac_layout_daemon.py` | Shortcut демон |
| `scripts/zmk_tis.py` | TIS + macime |
| `scripts/layout_sync.json` | Конфиг layer sync |
| `scripts/mac_layout.json` | Конфиг shortcuts |
| `scripts/keyboards.json` | Профили клавиатур |
| `scripts/layers_velvet_v3_ui_ruen.json` | Метаданные слоёв для демона |
| `scripts/install-zmk-daemons.sh` | Установка LaunchAgents |
| `scripts/BUILD.md` | Сборка, прошивка, демоны |
| `backups/ruen-unified-20260609/` | Бэкап до unified/split (keymap, daemon) |

---

## Типичный workflow пользователя

1. Правка `config/velvet_v3_ui_ruen.keymap`
2. `parse_keymap_layers.py` при смене слоёв
3. `./scripts/flash-qube-ruen.sh`
4. `./scripts/install-zmk-daemons.sh` или `kickstart` обоих агентов
5. `./scripts/run_daemon_tests.sh`
6. Ручная проверка base↔ru в TextEdit

---

## Открытые направления (если продолжать)

- Починить TIS API без macime (latency).
- Стабилизировать sym/sym_ru вывод punctuation на Mac.
- Рефакторить или удалить `test_zmk_hid_daemon_sym.py`.
- Снизить sym_ru↔ru flicker в прошивке (`hold-while-undecided` на `&lt` уже есть — возможно увеличить debounce в `layer_report.c` для layer 3).

---

## Ссылки в репозитории

- Подробная инструкция сборки: [`scripts/BUILD.md`](../scripts/BUILD.md)
- Транскрипт сессии: `~/.cursor/projects/Users-senders-zmk-ergohaven-zmk-config/agent-transcripts/ef0ab6d3-e28d-4d5a-bcf3-9e6634cb22de.jsonl`
