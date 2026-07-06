/*
 * NOTE:
 *   This file is copied from esp-idf examples as the below, and modified for usage of mros2-esp32.
 *   https://github.com/espressif/esp-idf/blob/master/examples/wifi/getting_started/station/main/station_example_main.c
 *   Therefore, mROS-base org inherits the Public Domain (or CC0) LICENCE for this file from the original file.
 */

#include "wifi.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_log.h"
#include "nvs_flash.h"

#include "lwip/err.h"
#include "lwip/ip_addr.h"

static EventGroupHandle_t s_wifi_event_group;
static const char *TAG = "wifi station";
static int s_retry_num = 0;
/* Set once the first IP is obtained; from then on, reconnect forever. */
static bool s_connected_once = false;

/* keep IP address obtained in event_handler */
static uint32_t mros2_ip_addr;

static void event_handler(void *arg, esp_event_base_t event_base,
                          int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START)
    {
        esp_wifi_connect();
    }
#ifdef STATIC_IP
    else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_CONNECTED)
    {
        esp_netif_t *netif = (esp_netif_t *)arg;
        if (esp_netif_dhcpc_stop(netif) != ESP_OK)
        {
            ESP_LOGE(TAG, "Failed to stop dhcp client");
            return;
        }
        esp_netif_ip_info_t ip;
        memset(&ip, 0, sizeof(esp_netif_ip_info_t));
        ip.ip.addr = ipaddr_addr(NETIF_IPADDR);
        ip.netmask.addr = ipaddr_addr(NETIF_NETMASK);
        ip.gw.addr = ipaddr_addr(NETIF_GW);
        if (esp_netif_set_ip_info(netif, &ip) != ESP_OK)
        {
            ESP_LOGE(TAG, "Failed to set ip info");
            return;
        }
    }
#endif
    else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED)
    {
        wifi_event_sta_disconnected_t *event = (wifi_event_sta_disconnected_t *)event_data;
        if (s_connected_once)
        {
            /* An established link must self-heal: without this the node goes
             * permanently dark after any AP hiccup (observed on hardware:
             * the board stopped answering ARP and sending SPDP after idling).
             * Reconnect attempts are naturally rate-limited by the connect
             * timeout, so no explicit backoff is needed. */
            ESP_LOGW(TAG, "wifi disconnected (reason=%d), reconnecting...", event->reason);
            esp_wifi_connect();
        }
        else if (s_retry_num < ESP_MAXIMUM_RETRY)
        {
            esp_wifi_connect();
            s_retry_num++;
            ESP_LOGI(TAG, "retry to connect to the AP (%d/%d)", s_retry_num, ESP_MAXIMUM_RETRY);
        }
        else
        {
            /* Initial connect failed: give up so the app can report it
             * (likely wrong credentials or AP out of range). */
            xEventGroupSetBits(s_wifi_event_group, WIFI_FAIL_BIT);
            ESP_LOGE(TAG, "connect to the AP failed after %d retries (reason=%d)",
                     ESP_MAXIMUM_RETRY, event->reason);
        }
    }
    else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP)
    {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "got ip:" IPSTR, IP2STR(&event->ip_info.ip));
        s_retry_num = 0;
        s_connected_once = true;
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
        
        /* keep IP address obtained in event_handler */
        mros2_ip_addr = event->ip_info.ip.addr;
    }
}

void wifi_init_sta(void)
{
    s_wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());

    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                    ESP_EVENT_ANY_ID,
                    &event_handler,
                    NULL,
                    &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                    IP_EVENT_STA_GOT_IP,
                    &event_handler,
                    NULL,
                    &instance_got_ip));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = ESP_WIFI_SSID,
            .password = ESP_WIFI_PASS,
            .threshold = {.authmode = ESP_WIFI_SCAN_AUTH_MODE_THRESHOLD},
            .sae_pwe_h2e = WPA3_SAE_PWE_BOTH,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    /* Disable modem power save. The default WIFI_PS_MIN_MODEM sleeps between
     * DTIM beacons, which for this always-on DDS node caused multi-hundred-ms
     * RTT spikes, dropped unicast (ping loss), and eventual disassociation
     * while idle. This node is USB-powered; reliability and latency win. */
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));

    ESP_LOGI(TAG, "wifi_init_sta finished.");

    /* Wait until the connection is established or the retry limit is reached. */
    EventBits_t bits = xEventGroupWaitBits(s_wifi_event_group,
                                           WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
                                           pdFALSE,
                                           pdFALSE,
                                           portMAX_DELAY);

    /* xEventGroupWaitBits() returns the event bits that completed the wait. */
    if (bits & WIFI_CONNECTED_BIT)
    {
        ESP_LOGI(TAG, "connected to ap SSID:%s", ESP_WIFI_SSID);
    }
    else if (bits & WIFI_FAIL_BIT)
    {
        ESP_LOGI(TAG, "Failed to connect to SSID:%s", ESP_WIFI_SSID);
    }
    else
    {
        ESP_LOGE(TAG, "UNEXPECTED EVENT");
    }
}

void init_wifi(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND)
    {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_LOGI(TAG, "ESP_WIFI_MODE_STA");
    wifi_init_sta();
}

uint32_t get_mros2_ip_addr(void)
{
    return mros2_ip_addr;
}
