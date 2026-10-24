target_sources_ifdef(CONFIG_ZMK_LAYER_REPORT app PRIVATE src/layer_report.c src/horizon_mode.c
                     src/behavior_host_layout.c src/behavior_host_key.c src/behavior_sym_glyph.c
                     src/behavior_er_lang.c)
target_include_directories(app PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/config)
if(CONFIG_RAW_HID)
  target_include_directories(app PRIVATE ${ZEPHYR_BASE}/../zmk-raw-hid/include)
endif()
