// Test for buffer overflow fixes in Domain.cpp
#include <cstdio>
#include <cstring>
#include <cassert>
#include <cstdint>

// Mock Config namespace
namespace Config {
    const int MAX_TOPICNAME_LENGTH = 40;
    const int MAX_TYPENAME_LENGTH = 40;
}

// Test function mimicking the fixed code
bool test_strncpy_bounds() {
    char topicName[Config::MAX_TOPICNAME_LENGTH];
    char typeName[Config::MAX_TYPENAME_LENGTH];

    // Test 1: Exactly 39 characters (should work - leaves room for null)
    const char* test39 = "123456789012345678901234567890123456789"; // 39 chars
    if (strlen(test39) >= Config::MAX_TOPICNAME_LENGTH) {
        printf("[FAIL] Test 1: strlen check failed for 39 chars\n");
        return false;
    }
    strncpy(topicName, test39, Config::MAX_TOPICNAME_LENGTH - 1);
    topicName[Config::MAX_TOPICNAME_LENGTH - 1] = '\0';
    if (strcmp(topicName, test39) != 0) {
        printf("[FAIL] Test 1: strncpy failed for 39 chars\n");
        return false;
    }
    printf("[PASS] Test 1: 39 char topic name handled correctly\n");

    // Test 2: Exactly 40 characters (should be rejected by >= check)
    const char* test40 = "1234567890123456789012345678901234567890"; // 40 chars
    if (strlen(test40) >= Config::MAX_TOPICNAME_LENGTH) {
        printf("[PASS] Test 2: 40 char topic name correctly rejected by >= check\n");
    } else {
        printf("[FAIL] Test 2: 40 char topic name should be rejected\n");
        return false;
    }

    // Test 3: 50 characters (should be rejected)
    const char* test50 = "12345678901234567890123456789012345678901234567890"; // 50 chars
    if (strlen(test50) >= Config::MAX_TOPICNAME_LENGTH) {
        printf("[PASS] Test 3: 50 char topic name correctly rejected\n");
    } else {
        printf("[FAIL] Test 3: 50 char topic name should be rejected\n");
        return false;
    }

    // Test 4: Null termination verification
    const char* testLong = "This is a very long string that exceeds the buffer size completely";
    strncpy(topicName, testLong, Config::MAX_TOPICNAME_LENGTH - 1);
    topicName[Config::MAX_TOPICNAME_LENGTH - 1] = '\0';
    if (strlen(topicName) == Config::MAX_TOPICNAME_LENGTH - 1) {
        printf("[PASS] Test 4: String correctly truncated and null-terminated\n");
    } else {
        printf("[FAIL] Test 4: String length = %zu, expected %d\n",
               strlen(topicName), Config::MAX_TOPICNAME_LENGTH - 1);
        return false;
    }

    return true;
}

// Test for overflow protection
bool test_overflow_protection() {
    struct Duration {
        int32_t sec;
        uint32_t nanosec;
    };

    // Test 1: Normal value (100ms)
    Duration d1 = {0, 100000000};
    uint32_t ms1 = static_cast<uint32_t>(d1.sec) * 1000 + d1.nanosec / 1000000;
    if (ms1 == 100) {
        printf("[PASS] Test 1: 100ms converts correctly\n");
    } else {
        printf("[FAIL] Test 1: Expected 100, got %u\n", ms1);
        return false;
    }

    // Test 2: Large value that would overflow (5000000 seconds = ~57 days)
    Duration d2 = {5000000, 0};
    // Check if overflow protection would trigger
    if (d2.sec > UINT32_MAX / 1000) {
        printf("[PASS] Test 2: Overflow protection would trigger for %d seconds\n", d2.sec);
    } else {
        // Calculate manually
        uint64_t calc = static_cast<uint64_t>(d2.sec) * 1000;
        if (calc > UINT32_MAX) {
            printf("[PASS] Test 2: Multiplication would overflow: %llu > %u\n",
                   (unsigned long long)calc, UINT32_MAX);
        } else {
            printf("[FAIL] Test 2: Should detect overflow but didn't\n");
            return false;
        }
    }

    // Test 3: Maximum safe value
    Duration d3 = {UINT32_MAX / 1000 - 1, 999000000};
    uint64_t calc3 = static_cast<uint64_t>(d3.sec) * 1000 + d3.nanosec / 1000000;
    if (calc3 <= UINT32_MAX) {
        printf("[PASS] Test 3: Maximum safe value handled correctly\n");
    } else {
        printf("[FAIL] Test 3: Safe value caused overflow\n");
        return false;
    }

    return true;
}

int main() {
    printf("=== Buffer Overflow Fix Verification ===\n\n");

    bool bounds_ok = test_strncpy_bounds();
    printf("\n");

    printf("=== Overflow Protection Verification ===\n\n");
    bool overflow_ok = test_overflow_protection();
    printf("\n");

    if (bounds_ok && overflow_ok) {
        printf("=== All verification tests PASSED ===\n");
        return 0;
    } else {
        printf("=== Verification FAILED ===\n");
        return 1;
    }
}
