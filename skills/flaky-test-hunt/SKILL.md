---
name: flaky-test-hunt
description: Track down flaky or failing tests in CI and quarantine or fix them.
min_level: 2
---
# Flaky test hunt playbook

1. Run the suite (ask test-runner) and note every failure.
2. Re-run the failures. Passing on retry = flaky. Failing every time = broken.
3. For flaky ones, look for: time, randomness, ordering, shared state, network.
4. Fix one if it's quick. Otherwise quarantine it AND file a follow-up. Never just skip it.
5. Report: what's broken, what's flaky, what you fixed, what you filed.
