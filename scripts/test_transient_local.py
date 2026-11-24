#!/usr/bin/env python3
"""Automated TRANSIENT_LOCAL late-joiner test."""
import serial, time, subprocess, sys, os

PORT = '/dev/ttyUSB0'
TIMEOUT_S = 90

def log(msg):
    print(msg, flush=True)

# Reset ESP32
ser = serial.Serial(PORT, 115200, timeout=0.2)
try:
    ser.dtr = False; ser.rts = True; time.sleep(0.15)
    ser.rts = False; time.sleep(0.2)
except: pass

start = time.time()
cached_published = False

log('[test] Resetting ESP32 and capturing serial...')
while time.time() - start < TIMEOUT_S:
    data = ser.read(4096)
    if data:
        text = data.decode('utf-8', 'replace')
        for line in text.split('\n'):
            line = line.strip()
            if line:
                if 'All cached messages published' in line:
                    cached_published = True
                    log(f'[test] Cached messages published at {time.time()-start:.1f}s')
                    break
    if cached_published:
        break

if not cached_published:
    ser.close()
    log('[test] FAIL: ESP32 did not publish cached messages within timeout')
    sys.exit(1)

# Start ROS2 subscriber
log('[test] Starting ROS2 subscriber...')
proc = subprocess.Popen(
    ['ros2', 'topic', 'echo', '/step8_transient_local',
     '--qos-reliability', 'reliable', '--qos-durability', 'transient_local'],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy()
)

sub_start = time.time()
cached_received = False
post_match_received = False
sub_lines = []

while time.time() - sub_start < 25:
    line = proc.stdout.readline()
    if not line:
        break
    decoded = line.decode('utf-8', 'replace').strip()
    if decoded:
        sub_lines.append(decoded)
        if '[CACHED]' in decoded:
            cached_received = True
            log(f'[test] Received CACHED msg: {decoded}')
        if '[POST_MATCH]' in decoded:
            post_match_received = True

proc.terminate()
try: proc.wait(timeout=3)
except: proc.kill()
ser.close()

log('')
log('===== TRANSIENT_LOCAL Test Result =====')
log(f'  ESP32 cached published:   {cached_published}')
log(f'  ROS2 received CACHED:     {cached_received}')
log(f'  ROS2 received POST_MATCH: {post_match_received}')
log(f'  Total subscriber lines:   {len(sub_lines)}')
if sub_lines:
    for l in sub_lines[:8]:
        log(f'    {l}')
log('')
if cached_received:
    log('[test] RESULT: PASS')
else:
    log('[test] RESULT: FAIL')
    sys.exit(1)
