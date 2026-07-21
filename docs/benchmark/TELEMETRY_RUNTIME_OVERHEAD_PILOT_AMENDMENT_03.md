# Telemetry Runtime-Overhead Pilot Amendment 03

Recorded: 2026-07-17T05:54:50Z

Status: FROZEN VALIDATOR CORRECTION

## Trigger

The preregistration requires every accepted run to have 200/200 unique
deliveries, zero publish failures, zero duplicates, and zero malformed samples.
The incomplete analysis after 18 accepted runs found that `trop-014` recorded
199/200 deliveries even though its telemetry-on validator returned PASS.

The telemetry-on validator had strictly checked all 200 telemetry samples, the
measurement window, fault flags, task records, and dump CRC, but had not checked
the workload delivery counters in `COMPARE_FINAL` and `BENCH_FINAL`. The
telemetry-off validator already checked its workload delivery counters.

## Amendment

The telemetry-on validator now also requires:

1. exactly one `COMPARE_CONFIG` and one `COMPARE_FINAL` record;
2. the frozen BEST_EFFORT, 64-byte, 10 Hz, 200-message clean workload;
3. `tx=200`, `rx=200`, and `samples=200` in `COMPARE_FINAL`;
4. `attempted_tx=200`, `publish_failures=0`, `rx=200`, `duplicates=0`,
   `malformed=0`, and `rtt_samples=200` in `BENCH_FINAL`.

This is a correction that enforces the original frozen acceptance criterion. It
does not change firmware, workload, schedule, random seed, measurement window,
estimator, confidence interval, or decision threshold.

## Consistency Action

All previously accepted telemetry-on logs are revalidated with the corrected
validator. `trop-014` attempt 01 fails because both `COMPARE_FINAL` and
`BENCH_FINAL` record `rx=199`. It remains immutable and retained, but is
classified `REJECTED_VALIDATOR_DEFECT` and excluded from the accepted set. The
scheduled unit must be replaced by the campaign runner.

All other telemetry-on logs accepted before this amendment pass the corrected
validator. Telemetry-off logs remain governed by their existing strict validator.

The original schedule SHA-256 remains
`20849d0e044f9021eaba8ec037f9180d677dac9fe2f8cea07cad4e6fdb21e399`.
