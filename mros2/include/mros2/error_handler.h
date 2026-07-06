// mROS2 Error Handling
// Centralized error handling for fatal errors in embedded systems

#ifndef MROS2_ERROR_HANDLER_H
#define MROS2_ERROR_HANDLER_H

#include <cstdio>

namespace mros2 {

enum class ErrorCode {
    NODE_CREATION_FAILED = 1,
    INVALID_QOS_PROFILE = 2,
    WRITER_CREATION_FAILED = 3,
    READER_CREATION_FAILED = 4,
    TRANSPORT_ERROR = 5,
    RESOURCE_EXHAUSTED = 6
};

// Fatal error handler for unrecoverable errors
// Logs error details and restarts the system
// cppcheck-suppress [noreturn]
[[noreturn]] inline void handle_fatal_error(ErrorCode code, const char* context) {
    printf("\n=== FATAL ERROR ===\n");
    printf("Code: %d\n", static_cast<int>(code));
    printf("Context: %s\n", context);
    printf("System will restart in 3 seconds...\n");

    // Platform-specific implementations
    #ifdef ESP_PLATFORM
        #include "esp_system.h"
        vTaskDelay(pdMS_TO_TICKS(3000));
        esp_restart();
    #else
        // For unit tests: exit instead of infinite loop
        printf("Non-ESP platform: exiting...\n");
        exit(static_cast<int>(code));
    #endif
}

} // namespace mros2

#endif // MROS2_ERROR_HANDLER_H
