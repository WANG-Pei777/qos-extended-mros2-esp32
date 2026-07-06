/*
 * NOTE:
 *   This file is copied from esp-idf examples as the below, and modified for usage of mros2-esp32.
 *   https://github.com/espressif/esp-idf/blob/master/examples/wifi/getting_started/station/main/station_example_main.c
 *   Therefore, mROS-base org inherits the Public Domain (or CC0) LICENCE for this file from the original file.
 */

#include "esp_wifi_types.h"

#if defined(__has_include)
#if __has_include("wifi_secrets.h")
#include "wifi_secrets.h"
#endif
#endif

#ifndef ESP_WIFI_SSID
#define ESP_WIFI_SSID "YOUR_WIFI_SSID"
#endif

#ifndef ESP_WIFI_PASS
#define ESP_WIFI_PASS "YOUR_WIFI_PASSWORD"
#endif

#define ESP_MAXIMUM_RETRY 5
// Weakest auth mode the STA will associate with. WPA2_PSK is the Espressif
// station default: it accepts WPA2, WPA/WPA2-mixed, WPA3, and WPA2/WPA3
// transition APs while still rejecting open/WEP/WPA1. Do not raise this to
// WPA2_WPA3_PSK: that value refuses plain WPA2 and even pure WPA3 networks.
#define ESP_WIFI_SCAN_AUTH_MODE_THRESHOLD WIFI_AUTH_WPA2_PSK

#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT BIT1

/*
 * Caution:
 *   We have not tested the operation using STATIC_IP setting yet.
 *   So you may not un-comment the below line to use DHCP setting
 */
// #define STATIC_IP
#ifdef STATIC_IP
#define NETIF_IPADDR "192.168.11.107"
#define NETIF_NETMASK "255.255.255.0"
#define NETIF_GW "192.168.11.1"
#endif
#ifdef __cplusplus
extern "C" {
#endif
extern void init_wifi(void);
uint32_t get_mros2_ip_addr(void);
#ifdef __cplusplus
}
#endif
