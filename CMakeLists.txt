if(CONFIG_OP36_LAYER_SYNC)
  zephyr_library()
  zephyr_library_sources(src/layer_sync.c)
endif()
