# Seven-QoS Performance Telemetry-Path Pilot

Status: EXCLUDED DEVELOPMENT PILOT

This workspace verifies the common 20-second telemetry, RTT, delivery, resource,
and PCAP capture path on the current mROS2 implementation. It also supports
excluded Deadline-family pilots, Lifespan probes, Resource Limits history
saturation probes, History/Depth KEEP_LAST burst probes, delayed-host
Durability replay probes, and bounded Liveliness outage probes. Each build has
a compile-time run token and cell ID. The
policy record is emitted after the telemetry seal so policy output cannot
perturb the measured window.

All six performance families now have an engineering-smoke path. The workspace
still cannot produce an accepted Seven-QoS performance run, and no row from the
frozen 1,530-run schedule may use it until the formal execution gate is opened.

The pilot uses RELIABLE/VOLATILE/KEEP_LAST endpoints with configurable payload,
rate, and host-side impairment. Energy is not collected. A common-path pass
closes only shared instrumentation and orchestration. Deadline-family readiness
additionally requires both an event-positive and an event-zero hardware smoke.
A Lifespan smoke additionally requires a fresh/disabled delivery probe, an
expired-sample drop probe, and an explicitly checked policy-applied workload
delivery outcome. These smokes verify mechanism wiring only; they do not freeze
or estimate the formal Lifespan performance effect.
A Resource Limits smoke requires within-capacity acceptance and one-over-cap
rejection probes, followed by history drain and an explicitly checked workload
outcome. A zero-duration legacy probe uses board-side transmission hold. A
positive ACK-suppression duration emits a readiness marker for an external,
source-audited host-egress outage and does not use the internal hold.
A History/Depth smoke holds a bounded burst, verifies the exact retained
sequence suffix for the configured KEEP_LAST depth, and requires history drain
before the workload. It does not implement or freeze the formal B2H ingress-loss
episode or burst estimand.
A Durability smoke emits a bounded cache before host startup and emits a UART
marker that starts the host. The host executor creates its input subscription
only after spinning, buffers replayed probe samples, and releases those replies
after the board reports bidirectional endpoint matching. The oracle compares
Volatile non-replay with Transient-Local ordered replay. It does not freeze the
formal late-join timing levels or cache-drain estimand.
A Liveliness smoke starts a bounded 100% host-egress outage only after a UART
readiness marker. The paired oracle requires no state transition for an outage
shorter than the lease and exactly one lost/recovered transition for an outage
longer than the lease, followed by a healthy workload. It does not freeze the
formal outage timing tolerance or recovery estimand.
