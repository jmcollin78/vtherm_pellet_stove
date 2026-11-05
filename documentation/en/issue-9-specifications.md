# Issue #9 - Consolidated functional specifications

| Metadata | Value |
| --- | --- |
| Version | 1.0, consolidated on 2026-11-05 |
| Status | Functional decisions approved; technical design and conformance pending verification; implementation not authorized |
| Sources | [Issue #9](https://github.com/jmcollin78/vtherm_pellet_stove/issues/9), user decisions of 2026-11-03 and 2026-11-05 |
| Documents | [FR version](../fr/issue-9-specifications.md), [bilingual design](../tech-docs/issue-9-design.md), [review](../tech-docs/issue-9-review.md), [FR guide](../fr/vtherm_pellet_stove.md), [EN guide](vtherm_pellet_stove.md) |

This version replaces historical amendments and proposals. Identifiers remain stable; acceptance criteria describe checks to perform, not tests already passed. Authorization covers documents, not implementation.

## 1. Goal and scope

Enable Pellet Stove regulation through dry contact: stove, bistable contact, HA `switch`, `over_switch` VTherm, `pellet_regulation` algorithm. No intermediate generic thermostat is required.

Every VTherm used by Pellet Stove must have **exactly one underlying**, in dry-contact and `climate` modes. Dry contact is an explicit local option, not automatic activation based on domain or inherited from a common setting.

Underlying state following, persistence/recovery, reconciliation and pending commands apply to both modes. In `climate`, retain burner phases and protections: the shared following change is intentional, not a requirement for strictly unchanged behavior. Preserve identifiers, configuration and type-specific commands, except for adaptations explicitly specified here.

Excluded: multiple underlyings, `input_boolean`, pulses or presumed hardware inversion, invented physical feedback, new ignition/shutdown durations, power/boost on dry contact, changes to VTherm, Duepi-EVO, firmware or hardware. External interface limitations must be reported, not bypassed with fictional guarantees.

## 2. Observations and time

| Usable observation | Meaning and acknowledgement |
| --- | --- |
| `switch.on` | Active contact / heating requested; acknowledges ON without proof of flame or heating. At startup, already-present ON is immediately adopted as on for regulation only. |
| `switch.off` | Inactive contact / presumed cooling; acknowledges OFF and starts OFF/cooling counters at observation. |
| `climate` burner startup | Acknowledges ON without waiting for actual heating. |
| Burner directly heating | Also acknowledges ON without requiring observed startup. |
| Duepi-EVO burner `Cooldown` | Acknowledges OFF, then track cooling; do not wait for `Off` or claim completed cooling. |
| Burner directly `Off` | Also acknowledges OFF without requiring prior `Cooldown` or inventing its duration. |
| Requested HVAC `heat` / `off` alone | Proves neither heating nor cooling completion; does not replace burner observation. |
| `unknown`, `unavailable`, missing/unclassifiable observation | No usable state; pause regulation and counters, monitor then reconcile. |

`Cooldown` is the approved functional label. Design must explicitly map target-version representations, including local-code `Cooling down`. Service return is never observed acknowledgement or physical proof.

Retain only the three existing durations, including units, values and bounds:

- `min_on_duration_min`: minimum activation before ordinary OFF, never ignition duration.
- `cooldown_duration_min`: dry-contact presumed cooling duration; completion is not physical proof.
- `min_off_duration_min + cooldown_duration_min`: next-ON guard since OFF observation, in accumulated active time.

Counters pause while HA is stopped and during unavailability. Expiry grants permission, not an order. Physical `climate` phases remain separate guards; do not reduce the burner to a binary relay or reset the whole cycle on each normal phase progression.

## 3. Requirements

| ID | Normative requirement |
| --- | --- |
| FR-001 | Offer dry contact in each VTherm's own Pellet Stove configuration at creation, in Options and Reconfigure if offered. Explicit activation, no automatic conversion or global propagation. |
| FR-002 | Show a visible FR/EN warning before confirmation: ON does not prove ignition, cooling is presumed, durations must suit the stove; too short a cooldown may permit restart while cooling. Logs/diagnostics alone are insufficient. |
| FR-003 | Require one underlying for all Pellet Stove VTherms; dry contact requires `over_switch` and one ON/OFF `switch`. User confirms bistability without claimed hardware detection. Reject noncompliant configurations without arbitrary selection. |
| FR-004 | Reuse only the three existing durations without confusing them with physical times. Invalid applicable durations do not authorize ON. |
| FR-005 | Adopt usable observed state; distinguish active contact, startup regulation convention, presumed cooling and burner phases. Invent neither physical transition nor past age. |
| FR-006 | Issue justified ON/OFF commands without repetition on stable state or pending alone. Hide power/boost settings and neutralize runtime effects in dry contact regardless of value source, while retaining stored legacy values for explicit return to `climate`. |
| FR-007 | ON requires current demand, all guards clear and no ongoing stop. Silently ignore noncompliant ON without rejection alert, queue, deferred intent or replay after stop/expiry. Only a fresh compliant evaluation may decide a new ON. |
| FR-008 | Save cycle state and counter values per VTherm; restore before regulation. Matching observation: resume without interruption credit; mismatch or unusable snapshot: adopt and zero relevant counters. No lifecycle-only or reconciliation-only command. |
| FR-009 | On unavailability, Pellet Stove becomes `unavailable`, waits indefinitely, pauses decisions/counters and monitors. Follow external actions without permanent hold. Explicit command errors remain visible without automatic retry; monitor and reconcile even if underlying changes despite error. |
| FR-010 | Explicit OFF/safety immediately takes priority, including during minimum ON or pending ON. Late ON confirmation does not restore obsolete intent. Distinguish logical priority, transmission and observation; guarantee neither in-flight ON cancellation nor hardware stop. |
| FR-011 | Expose observed state, interpreted phase, availability, counters, separate pending status, recovery reason and explicit error. No fictional timestamp or physical guarantee; keep error accessible without history-only permanent hold. Normal ON rejection is silent. |
| FR-012 | Preserve existing entry identifiers/options and no implicit conversion. Explicitly extend following/reconciliation to `climate` while retaining its phases/protections and specific commands. Single-underlying constraint also applies. |
| FR-013 | Keep FR/EN guides and warning consistent with these rules. Until validated implementation, present target behavior as planned, not available in the current release. |

## 4. Business rules

| ID | Normative rule |
| --- | --- |
| BR-001 | Usable observation overrides previous internal state; decision, call, observed acknowledgement and physical phase completion differ. Stable observations and normal phase progressions do not reset cycle counters. |
| BR-002 | In dry contact, next ON after accumulated minimum OFF plus cooldown since observed OFF, with current demand and other guards. Retain additional phase guards for `climate`. No deferred ON from rejected requests. |
| BR-003 | Ordinary OFF respects accumulated minimum ON; explicit OFF/safety bypasses it and overrides pending ON. No additional duration. |
| BR-004 | Call without observation: separate pending state, no fictional counter advance. OFF remains pending without expiry, time-based alert or retry. Explicit error: visible, state retained, no automatic resend; late observation enables reconciliation without intervention. |
| BR-005 | Explicit local dry-contact option and warning, single underlying in both modes, power/boost hidden and ineffective without destroying values, no implicit activation or changes to other shared-option resolution rules. |

## 5. Recovery and reconciliation

At HA shutdown, save elapsed counters and cycle state, not just configuration. Example: 20 saved minutes against a 30-minute minimum ON leave 10 minutes on recovery, regardless of downtime, if state matches.

| Retained state and first usable observation | Handling |
| --- | --- |
| Matching | Resume saved/retained counters without credit for stopped/unavailable time. |
| Retained ON, observed OFF | Adopt OFF; minimum OFF and cooldown restart at zero on observation. |
| Retained OFF, observed ON | Adopt ON; full minimum ON from observation before ordinary OFF. |
| No usable snapshot / first installation | Adopt first usable state and zero corresponding counters. |
| Crash with usable matching snapshot | Resume saved values without reconstructing unsaved time. |
| Unavailable underlying | Pellet Stove `unavailable`, counters/decisions paused, indefinite monitoring then same reconciliation on return. |

These rules apply at startup, reload and runtime for both types; design specifies `climate` phase matching. Do not claim to know transition time during interruption. No default shutdown. Explicit OFF/safety retains priority when command path is usable, without claiming delivery/execution during unavailability.

Adopt usable external actions, then continue regulation under guards. Do not issue an opposite command to restore former internal state or require manual acknowledgement solely for that action. External authorship is not always identifiable.

## 6. Pending commands and errors

After ON/OFF, retain last observed state separately from pending command. Still-published previous state, especially through polling, does not alone imply failure or external action. Section 2 observations may acknowledge without an observed intermediate phase; invent neither missed phase nor elapsed duration.

After OFF, await observation indefinitely without time-based alert; keep monitoring however late. No new ON timeout or retry mechanism is added. Pending alone with an available underlying does not mean `unavailable`.

Explicit ON/OFF error: retain observation, expose error and monitor. Error proves neither transition nor absence of hardware effect. No automatic resend, including periodic evaluations; later relevant observation can confirm without intervention. Keep error accessible without a history-only hold.

Explicit OFF/safety during pending ON immediately takes priority. Reconcile late observed ON without lifting it. Conversely, silently ignore ON during ongoing stop, without memory/replay or rejection-driven state/counter changes. Do not retain rejected ON for after stop.

## 7. Acceptance criteria

All are **to be executed during development**, not evidence of execution or hardware behavior.

| ID | Scenario and expected result |
| --- | --- |
| AC-001 | Creation, Options, Reconfigure if offered: explicit non-preselected choice, FR/EN warning before confirmation, cancellation without effect, no new duration and applicable duration validation. |
| AC-002 | Migration/reload without choice: no conversion, preserved IDs/options; `climate` follows approved shared rules without losing specific commands/phases. |
| AC-003 | Eligible dry contact and current demand: one ON; observed ON means active contact even after waiting, never flame; ordinary OFF respects minimum ON; no power/boost. |
| AC-004 | Observed OFF: presumed cooling until accumulated cooldown; next ON only after minimum OFF plus cooldown, current demand and other guards; expiry alone issues no command. |
| AC-005 | Initial ON adopted for regulation without invented physical date or new ON; counters follow matching snapshot or zero initialization under AC-012 through AC-016. |
| AC-006 | Unavailability during ON/OFF/phase: aligned Pellet Stove availability, paused counters, automatic recovery without unknown-time credit under AC-013 through AC-016. |
| AC-007 | External ON/OFF actions: adoption without automatic inverse or permanent hold, updated counters and retained guards; see AC-017/018. |
| AC-008 | Call without observation distinct from explicit error: no invented transition/counter, ongoing monitoring, late reconciliation and no retry; see AC-019 through AC-025. |
| AC-009 | Explicit OFF/safety bypasses minimum ON and pending ON; priority request without fictional shutdown guarantee; see AC-026. |
| AC-010 | Diagnostics and FR/EN guides distinguish observation, pending, counters, recovery, uncertainty and presumption; no normal ON rejection alert. |
| AC-011 | Reject out-of-contract configuration without arbitrary selection; no HA authentication of bistability; see AC-030. |
| AC-012 | Shutdown/restart in partially elapsed ON, OFF and cooldown: resume saved values, including 20/30 ON minutes, without interruption credit or lifecycle-only ON/OFF; include repeated restarts. |
| AC-013 | Long unavailability at boot/runtime: `unavailable`, paused counters, no five-minute limit, monitoring and automatic late return before decision. |
| AC-014 | Retained ON to observed OFF: adopt, zero OFF/cooldown, no reconciliation command or past credit; current demand and guards for new ON. |
| AC-015 | Retained OFF to observed ON: full minimum ON from observation; matching cases resume counters; explicit OFF/safety retains priority. |
| AC-016 | First install, lost/invalid snapshot, crash: adopt first observation and zero counters unless usable matching snapshot can resume without reconstructing lost time. |
| AC-017 | `switch` external actions and stable publications: follow and regulate without manual acknowledgement, repetition, adoption inverse or stable-state resets. |
| AC-018 | Same following/recovery in `climate`, retaining phases/protections, no HVAC-request/physical-phase confusion and no whole-cycle reset on normal progression. |
| AC-019 | Duepi-EVO OFF, old states then `Cooldown`: wait then acknowledge at `Cooldown`, not `Off`, without claiming cooling completion; verify target-version mapping. |
| AC-020 | Prolonged or never-confirmed OFF: no expiry, time-based alert, repetition or inverse; automatically acknowledge very late observation. |
| AC-021 | Burner directly `Off`: acknowledge without previous `Cooldown`, invented past duration or adoption command; retain guards. |
| AC-022 | Late contact OFF: acknowledge and start counters from observation, never call; stable OFF does not reset them; absent OFF remains pending. |
| AC-023 | ON: contact ON or Duepi-EVO startup phase acknowledges without waiting for heating; service return/HVAC alone insufficient, available pending, observation-derived counters and no repetition. |
| AC-024 | Direct heating phase, including late: acknowledge ON without prior startup, adoption command, invented past phase/age; stable state does not reset and safety retained. |
| AC-025 | ON/OFF errors with available underlying: visible error, retained observation, no false success or periodic retry; late observation reconciles without intervention and error remains accessible. Separately test actual unavailability. |
| AC-026 | Explicit OFF/safety during pending ON: immediate priority without minimum; late ON does not restore ON request; distinguish priority, transmission and observed stop. Verify in-flight service ordering without assuming hardware cancellation. |
| AC-027 | Repeated ON during stop or uncleared guards: no ON, alert, memory, replay or rejection-driven state/counter change; stop acknowledgement and guard expiry replay nothing. Only fresh compliant evaluation may decide ON under current demand. |
| AC-028 | Two VTherms: local choice and FR/EN warning change only confirmed entry; global, migration and reload do not enable dry contact elsewhere. |
| AC-029 | Power/boost hidden and ineffective despite legacy/global/default values; save/reload/restart preserve values; explicit return to `climate` makes them available, other `climate` entry unchanged for these functions. |
| AC-030 | Exactly one underlying in both modes: zero/multiple rejected without selection; dry contact requires `over_switch` + ON/OFF `switch` and user bistability confirmation, no implicit `climate` conversion. Verify validation and subsequent configuration change. |

## 8. Decisions and gates

| Question | Approved decision |
| --- | --- |
| Q-001 | Only three existing durations; no extra ignition/shutdown duration. |
| Q-002 | Counter persistence/recovery, paused interruption, indefinite unavailability waiting and matching-based adoption/reconciliation. |
| Q-003 | Follow usable external `switch` and `climate` actions/states without permanent hold or adoption-only inverse command. |
| Q-004 | Observed pending/acknowledgements, errors without retry, explicit OFF/safety priority, noncompliant ON ignored without memory. Technical in-flight ordering remains to demonstrate. |
| Q-005 | Explicit local option and warning; power/boost hidden/neutralized with values retained; one underlying for both modes. |

D-001: observations and durations, never invented physical proof. D-002: explicit option with pre-confirmation warning. D-003: user sets existing durations for the appliance. Former H-001/H-002 are superseded by Q-002; H-003 is confirmed by Q-005.

No functional decision remains identified at this stage. Design must provide data model, phase mapping, validation, persistence/lifecycle, command/deduplication and diagnostics. Do not claim guaranteed external ON/OFF ordering without evidence. If existing interfaces cannot enforce required priority, report the blocker and request a decision without changing out-of-scope dependencies.

Before development: consolidation/documentary audit, design review and explicit authorization. Before release: execute criteria/technical gates, check HA/VTherm integration and regression. These documents establish neither hardware tests nor a proven cause for reported shutdown during restart.