# Development and Evaluation Method

Status: ACTIVE PROCESS DESCRIPTION
Updated: 2026-07-23

## Method Layers

This project uses three complementary method layers. They must not be treated
as interchangeable.

1. A SCRUM-inspired iterative engineering process organizes implementation.
2. Requirements-to-evidence traceability organizes the technical design.
3. Frozen protocols, randomized schedules, acceptance ledgers, and statistical
   analysis organize formal evaluation.

The project does not claim strict compliance with the complete Scrum framework.
The term `SCRUM-inspired` is used because the work adopts bounded iterations
without asserting every formal Scrum role, event, and artifact.

## Iterative Engineering Cycle

Each engineering iteration follows:

`planning -> implementation -> automated test -> hardware validation -> review`

Current work packages are:

- QoS API and profile mapping;
- DDS/RTPS protocol and ESP32-S3 firmware behavior;
- deterministic compatibility and mechanism validation;
- native ROS 2, upstream mros2-esp, micro-ROS, and current-system baselines;
- formal performance collection;
- audit, analysis, figure generation, and archival.

An iteration may change code, tests, or an unfrozen protocol. It may not silently
change the interpretation of already collected evidence.

## Technical Traceability

Every evaluated QoS behavior should connect:

`robotics scenario -> requirement -> user API/profile -> DDS/RTPS mechanism -> observable -> acceptance rule -> retained evidence`

This traceability follows the method pattern identified in the mROS 2 work by
Hideki Takase and collaborators: begin with bounded embedded requirements,
expose a usable ROS 2-compatible interface, evaluate the same workload against
appropriate baselines, and separate end-to-end outcomes from internal
attribution.

## Formal Evaluation Boundary

Formal evaluation starts only after the applicable gate is frozen. It retains:

- source commit and exact firmware hashes;
- cell configuration and stable firmware token;
- unique campaign attempt identity and randomized ordinal;
- accepted and rejected attempt records;
- serial telemetry, PCAP, host logs, and resource measurements;
- predefined estimands and completeness audits.

Engineering smokes, debugging attempts, and single-host native pilots remain
excluded even when they pass. SCRUM-inspired iteration does not override this
evidence boundary.

## Current Stage

The deterministic Seven-QoS compatibility and mechanism campaigns are complete.
The performance campaign is in the pre-data artifact-binding and exact-hardware
validation iteration. Formal performance collection remains blocked until its
launch gate passes.

## Related Method Example

Toapanta and Fierro-Silva describe a ROS 2, micro-ROS, and ESP32 system developed
through iterative planning, implementation, testing, and validation phases:

<https://doi.org/10.61961/injei.v3i1.87>
