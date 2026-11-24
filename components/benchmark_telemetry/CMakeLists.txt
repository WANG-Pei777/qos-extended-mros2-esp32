idf_component_register(
  SRCS "benchmark_telemetry.cpp"
  INCLUDE_DIRS "include"
  REQUIRES driver esp_timer esp_hw_support heap freertos)
