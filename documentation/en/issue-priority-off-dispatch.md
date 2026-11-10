# [Safety-critical] Priority OFF can become pending without sending a stop command

## Summary

With `vtherm_pellet_stove` 2.0.0.beta3, the regulation handler can receive an OFF decision while VTherm is OFF and the stove is observed running, set `pending="OFF"`, and send no OFF command. Subsequent control iterations do not retry because the controller already sees an OFF command as pending.

This command-dispatch defect has been reproduced offline using the real controller and the unmodified handler method, with all outgoing commands mocked. It is not a minimum-runtime delay: the controller explicitly returns a priority OFF decision, but the handler does not dispatch it.

An unattended stove ignition was also recorded while VTherm was OFF. The failure to stop is confirmed in the isolated reproduction; the exact origin of that ignition is still under investigation. These are related concerns, not a fully proven causal chain.

## Environment and configuration

| Component / setting | Reported value |
| --- | --- |
| Home Assistant | 2026.11.0 |
| Versatile Thermostat | 10.6.4 |
| vtherm_pellet_stove | 2.0.0.beta3 |
| Underlying integration | Duepi_EVO, updated for HA 2026.11 compatibility |
| VTherm entity | `climate.vtherm_poele` |
| Stove entity | `climate.poele_pellets` |
| VTherm type / algorithm | `over_switch` / `pellet_regulation` |
| Virtual ON / OFF commands | `climate.set_hvac_mode` with `heat` / `off` |
| Cycle duration | 5 minutes |
| Keep-alive | Disabled (`keep_alive_sec=0`) |
| VTherm internal state repair | Enabled |
| Minimum ON / OFF durations | 120 / 90 minutes |
| Cooldown duration | 5 minutes |
| Hysteresis ON / OFF | 0.05 / 0.7 degrees C |
| Safety room temperature | 26 degrees C |
| Minimum / maximum ON percentage | 0 / 1 |
| Plugin power control | Disabled |
| Duepi automatic error reset | Disabled |

The inspected handler and controller sources match the `2.0.0.beta3` tag. The source files loaded by the remote HA process have not been independently retrieved. The exact previously working version and the first introducing commit have not been established.

## Recorded incident

Times below are in Europe/Paris (UTC+01:00).

| Date and time | Observation |
| --- | --- |
| 2026-11-09 23:46:21 | VTherm switches to OFF. |
| 2026-11-09 23:52:31 | Stove is observed OFF, burner phase `Off`. |
| 2026-11-09 23:55:37 | VTherm logs an internal state repair for the stove. The warning does not identify whether ON or OFF was sent. |
| 2026-11-09 23:56:37 | Stove reports `heat`, burner phase `Ignition starting`, fan `Min`; VTherm is still OFF. |
| 2026-11-10 approximately 07:58 | Reporter disconnects the stove electrically after unexpected overnight operation. |

Around the confirmed ignition, VTherm remained OFF with requested and current HVAC modes OFF, target temperature 10 degrees C, room temperature about 22.5 degrees C, and `on_percent=0`.

The burner phase matters: Duepi can also expose `heat` during `Cooling down`, which alone is not evidence of ignition. The event above is distinguished by `Ignition starting`.

The repair immediately before ignition is a strong investigation lead, not proof that repair issued the ignition command. The repair feature belongs to VTherm core, not this plugin. A companion VTherm issue should cover the independent core guard against repair turning heating ON while the parent is OFF.

## Offline reproduction

No live stove commands or Home Assistant services were invoked.

1. Use the actual `PelletRegulationController` with the configuration above.
2. Set the thermostat mode to `off`, target to 10, and current temperature to 22.5.
3. Make the underlying observation return cycle `ON`, phase `Flame On`, available.
4. Start with no pending command and one underlying whose `turn_on()` and `turn_off()` methods are `AsyncMock` objects.
5. Provide a mocked scheduler with `start_cycle()` and `cancel_cycle()`.
6. Execute the unmodified `PelletRegulationHandler._async_control_heating()` twice.

Observed result:

```text
OFF DISPATCH {
    'vtherm': 'off',
    'observed': 'Flame On',
    'pending': 'OFF',
    'scheduler_orders': 0,
    'direct_OFF_orders': 0
}
```

The probe extracted the handler method through Python's AST and supplied minimal dependencies, while using the real controller. This demonstrates the local branch defect; it is not a full HA integration test or a hardware test.

## Code analysis

Relevant sources:

- [PelletRegulationHandler._async_control_heating](https://github.com/jmcollin78/vtherm_pellet_stove/blob/2.0.0.beta3/custom_components/vtherm_pellet_stove/handler.py)
- [PelletRegulationController.calculate_observed](https://github.com/jmcollin78/vtherm_pellet_stove/blob/2.0.0.beta3/custom_components/vtherm_pellet_stove/pellet/controller.py)

When HVAC mode is OFF and the stove is observed ON, `calculate_observed()` sets `off_priority=True` and returns `"OFF"`, independently of the minimum ON duration.

The handler then sets `state.pending = command` before attempting dispatch. Both available branches are skipped:

- Direct `turn_off()` requires `not state.is_heating`, which is false for a running stove.
- Scheduler dispatch requires `hvac_mode != "off"`, which is also false.

The `finally` block cancels the scheduler, but cancelling a cycle does not itself send OFF. On subsequent iterations, `pending="OFF"` suppresses another OFF decision even though the first command was never sent.

An additional consistency risk is that VTherm repair uses the underlying's internal desired state. Dispatching a direct OFF without updating that desired state would leave another control path free to oppose the plugin's decision.

## Proposed solution: repair priority OFF dispatch and command tracking

1. Provide an unconditional priority-OFF dispatch path for a valid bound target when the controller requests OFF. It must handle an observed running stove, not only an unavailable stove or a previous pending ON.
2. Synchronize the underlying's desired command with OFF through the appropriate supported VTherm path. Do not rely solely on a direct service call that leaves monitoring or repair expecting ON.
3. Distinguish an intended command, an attempted/dispatched command, and an observed acknowledgement. Do not mark a command as successfully dispatched if no dispatch branch ran. On a dispatch error, preserve a retryable stop request and expose the error.
4. Add bounded, rate-limited retries and an explicit diagnostic when a dispatched OFF is not acknowledged. Service acceptance is not physical confirmation. An unavailable target must not be reported as successfully stopped; reconcile again when it becomes available.
5. Keep user OFF and safety OFF higher priority than minimum ON duration. Normal hysteresis-driven transitions must still respect minimum ON/OFF durations and cooldown. OFF means the device's normal stop command, not cutting electrical power during combustion or cooling.
6. Prevent a previous pending ON, delayed callback, or optional power-level update from restarting heating after priority OFF. Do not optimistically rewrite the observed physical state.

Do not fix this by making every `cancel_cycle()` force OFF: the plugin deliberately cancels scheduler timers after sending a one-shot ON command as well.

No Duepi_EVO code change is proposed. The confirmed dispatch defect is upstream of the device integration. Disabling VTherm repair alone does not fix a missing OFF command and is not sufficient to authorize a return to service.

## Acceptance criteria and regression tests

- [ ] VTherm OFF + observed `Flame On` sends an actual OFF command, including within minimum ON duration.
- [ ] The same guarantee holds during `Ignition starting` and for the configured room-temperature safety stop.
- [ ] A priority OFF supersedes a pending ON; no later callback or power command sends ON while OFF remains authoritative.
- [ ] No dispatch branch taken cannot produce a permanently blocking `pending="OFF"` state.
- [ ] Dispatch exceptions, missing acknowledgement, and unavailable/reconnected targets remain observable and retryable with bounded retry frequency.
- [ ] An observed OFF/cooldown acknowledgement completes the stop request according to the existing observation model, without a repeated OFF command flood.
- [ ] After a priority stop, core repair does not see an outdated ON intention from the plugin.
- [ ] Ordinary heating cycles still respect minimum ON/OFF durations, cooldown, and existing power-control behavior when enabled.
- [ ] Cancelling timers immediately after an intentional ON does not itself stop the stove.
- [ ] Add focused tests in the existing handler/controller test modules using mocked services, without energizing physical equipment.

## Evidence limitations

The initial ignition command and the mechanism that might have left a stale ON intention in core are not yet proven. The warning at 23:55:37 does not include command direction. No recorder history was returned for the pellet debug sensor, and an internal VTherm log export covering the incident has not been retrieved. The full HA test suite has not been run successfully in the available local environment; only the isolated reproduction above has passed.