# tesla-custom — personal test branch

Personal sunnypilot fork branch for a **Tesla Model 3 Highland (HW4, 2026) + comma 4**.
Based on sunnypilot `master` (2026-07-03). **Not tested on a real car until noted otherwise — use at your own risk.**

Install URL: `installer.comma.ai/RWEnergoo/tesla` (branch `tesla` is an alias of `tesla-custom`).

## Features (all behind default-OFF toggles, sunnylink app → Vehicle → Tesla)

### 1. Cruise Button Toggles Engagement (`TeslaButtonCancels`)
Stock behavior: with sunnypilot longitudinal (alpha) engaged, pressing the cruise/engage button does
nothing — the DI briefly reports `DI_cruiseState = PRE_CANCEL`, but both sunnypilot and the panda
count PRE_CANCEL as "engaged" and sunnypilot keeps commanding `ACC_ON` at 25 Hz, swallowing the press.

With this toggle the right scroll wheel button becomes an on/off switch. The trigger is
hardware-determined (no user setting): with the vehicle bus, a plain right-wheel click disengages
instantly; without it, hold either wheel pressed for 0.5 s
everything (openpilot longitudinal via `buttonCancel` → `USER_DISABLE`, and MADS lateral via the
`sunnypilot/mads/mads.py` cancel branch). Implemented in
`opendbc/sunnypilot/car/tesla/carstate_ext.py`:
- Trigger: `UI_warning.scrollWheelPressed` held for `CANCEL_HOLD_FRAMES` (1 s). Road testing showed
  this signal also fires on scroll ticks and on the left (volume) wheel click, so a short click or
  scroll does nothing — only a deliberate hold cancels. (`DI_cruiseState = PRE_CANCEL` kept as a
  complementary trigger.)
- Anti-bounce (causal, not timed): the car can treat the tail of the cancel click as an engage
  command, which would re-engage everything immediately (observed on the road — dangerous). After a
  cancel, `blockPcmEnable` stays set until the press is fully released (200 ms debounce) AND a
  fresh press begins. During that whole rearm window the carcontroller sends a standing
  `ACC_CANCEL_GENERIC_SILENT` instead of `ACC_ON`, so the DI never completes the click-tail engage
  and no engage/disengage chime sounds. Re-engaging is simply clicking again — no waiting period.
  (UI copy is deliberately end-user-simple; the vehicle-bus/fallback details live here instead.)

Side effect (intentional): enabling this lifts the "limited MADS" restriction for Tesla without the
vehicle bus (`sunnypilot/mads/helpers.py`), unlocking **Steering Mode on Brake Pedal**
(Remain Active / Pause / Disengage) — the button now provides a consistent lateral disengage path.

> History (road + protocol tests 2026-07-03):
> v1: PRE_CANCEL detection only — button press never reaches the DI (the AP computer that normally
> translates it is replaced by openpilot). No disengage.
> v2: cancel on scrollWheelPressed rising edge — worked, but that bit fires on BOTH wheels for
> clicks, scroll ticks and holds (labeled protocol test), so volume clicks and scrolling canceled
> too, and rapid re-clicks re-engaged (toggle ping-pong). Dangerous.
> v3: hold-to-cancel + causal re-engage block (press must be fully released and a fresh press
> started before PCM may re-engage).
> v4 (current): right-wheel-only trigger via VCLEFT_switchStatus.swcRightPressed on the VEHICLE
> bus (multiplexed; read index-1 frames only) — scroll ticks, volume clicks and the left
> chill-mode hold can never cancel, and Instant hold duration is safe. Cars without the vehicle
> bus fall back to the shared bit with Instant clamped to 0.5 s.

### 2. Steering Override Pauses Steering (`TeslaSteerOverridePauses` + `TeslaSteerOverrideResumeDelay`)
Stock behavior: a hard steering override (`EPAS3S_handsOnLevel >= 3`, common below the ~23 km/h EPS
limit of Cooperative Steering) disengages **everything**, including longitudinal.

With this toggle, mirroring stock Tesla (override kills Autosteer, TACC keeps driving):
- **Longitudinal keeps running** through the override. Firmware: the generic
  `controls_allowed = false` on `steering_disengage` in `opendbc/safety/safety.h` is gated behind a
  new alternative-experience bit `ALT_EXP_MADS_STEER_OVERRIDE_PAUSE_LATERAL` (8192). Userspace: the
  `steerDisengage` event is suppressed in `selfdrive/selfdrived/selfdrived.py`.
- **Lateral pauses and auto-resumes.** Firmware: MADS re-allows lateral on the override's falling
  edge (`opendbc/safety/sunnypilot/mads.h`, mirrors the pause-on-brake pattern). Userspace: MADS
  transitions to paused during the override (`sunnypilot/mads/mads.py`); the carcontroller delays the
  actual resume (`opendbc/sunnypilot/car/tesla/steer_override_pause.py`) until the driver has released
  the wheel for the configured delay (0.5/1/1.5/2 s) **and** the commanded angle is within 10° of the
  actual angle (no snap-back mid-corner).

### Unchanged on purpose
- **Brake always disengages longitudinal**, on every layer (hardcoded in safety firmware). The brake
  is the unconditional emergency escape. Combine with Steering Mode on Brake Pedal = *Remain Active*
  for "brake kills speed control only, steering stays, one button press to resume".
- Cooperative Steering's ~23 km/h minimum is a Tesla EPS firmware limit (control type 2), not
  addressable in software.

### Hard rule: we never filter or block a car message
This branch only ever **adds** frames to the bus. No message the car itself sends is dropped,
delayed or rewritten on its way through, and no forwarding rule in `tesla_fwd_hook` is weakened
for a feature. The ISA chime mute is the test case for this rule: suppressing the chime by
blocking the stock `DAS_status` would work, but that message also carries blind spot, forward
collision and lane departure warnings - and this branch is public, so whoever installs it does
not know which of its features silently took a safety message away. Injecting alongside keeps
the failure mode harmless: if our copy stops, the car's own copy simply takes over.

If a feature can only be built by filtering, it does not get built.

## Changed files
Main repo (this branch) and `opendbc_repo` submodule → `RWEnergoo/opendbc@tesla-custom`
(see `.gitmodules`). Full list: `git log --stat master..tesla-custom` in both repos.

New params: `TeslaButtonCancels`, `TeslaSteerOverridePauses`, `TeslaSteerOverrideResumeDelay`
(`common/params_keys.h`, plumbed via `sunnypilot/selfdrive/car/interfaces.py` →
`opendbc/sunnypilot/car/interfaces.py` → `CarParamsSP.flags`).

## Testing
- opendbc safety suite + mutation tests: **green** (CI via https://github.com/RWEnergoo/opendbc/pull/1,
  new tests in `opendbc/safety/tests/test_tesla.py` and `opendbc/safety/tests/mads_common.py`).

Road test status (Model 3 Highland HW4, comma 4, WITH vehicle bus):

| Feature | Status |
|---|---|
| Button toggle, instant click (vehicle bus path) | ✅ **Stable** — "works perfectly, zero faults" over many rides |
| Button toggle 0.5 s hold fallback + runtime failover | ✅ validated via the (since removed) Simulate Vehicle Bus Loss dev toggle; the `TeslaSimVehicleBusLoss` param still exists for future regression tests, set it manually |
| Park = all-off pulse | ✅ validated |
| Steering Mode on Brake Pedal = Remain Active | ✅ in daily use |
| Steering override pause (v2 conditions + MADS-flap persistence + standstill block) | ✅ **Stable** — "can't make it fail" |
| Following distance / Experimental via right-wheel tilt | ✅ **Beta** — right = more aggressive / Experimental ON, left = more relaxed / OFF, both confirmed on the road |
| Upstream merge (423 + 135 commits, `openpilot/` package restructure, fork flags renumbered off upstream's MADS screen-button bits) | ✅ validated on the road |
| Soft gas threshold + proportional brake blend (20% window, 17.2% release) | ✅ **Stable** — two long drives actively trying to provoke it after the hysteresis fix; the on/off point is audible and feels right, no difference in driving behaviour, re-engages cleanly on release |

## Tried and dropped: muting the EU ISA speed chime

Built, road tested twice, measured, and **removed** (2026-10-05). Written down so nobody
repeats it.

**What the community does.** Three codebases implement this
([lenfien/tesla-open-can-mod-release](https://github.com/lenfien/tesla-open-can-mod-release),
[hypery11/flipper-tesla-fsd](https://github.com/hypery11/flipper-tesla-fsd),
[ev-open-can-tools](https://github.com/ev-open-can-tools/ev-open-can-tools); the other repos
that show up in a search are mirrors or vendored copies of those). All three do the same
thing: on every `0x399` (921) frame, set byte 1 bit 5 (`ISA_speedLimitSoundActive`),
recompute the Tesla additive checksum over bytes 0..6 with id 921, and re-send. hypery11
calls `0x399` "the trap": on HW3/Legacy it is `DAS_status`, on HW4 it is the ISA message,
while `DAS_status` moves to `0x39B`.

**Why it cannot work on this car.** `0x399` does not exist here. Scanned a full drive on all
three buses: 481 distinct addresses, bus 1 alone carries 378 (so it is a complete vehicle CAN,
not a gateway-forwarded subset), and `0x399` shows up only on bus 1 as a 3-byte all-zero stub.
Not on the party bus, never 8 bytes. No Highland owner in those projects' issue trackers
reports the feature working either - the confirmations all come from pre-Highland HW4 and
Juniper.

**Why the obvious substitute is not the control.** `DAS_suppressSpeedWarning` (0x39B bit 13)
looks right and even correlates with speed-limit events, but across 18 drives the car sets it
**only** while `DAS_fusedSpeedLimit` is 0 - it means "no limit known, do not warn". Evidence:

- Route `00000215`: 872 frames with the bit set, every one of them at limit 0.
- Route `00000212`, the drive where the on-screen mute button was pressed repeatedly: the bit
  stayed 0 for all 13 segments.
- 18 drives with Tesla FSD engaged (`DAS_autopilotState` = 6): the bit is never set, and
  `DAS_fusedSpeedLimit` is 0 in **0.0%** of 10130 engaged frames - the car always knows the
  limit while FSD drives, which matches the speed limit sign staying on screen.
- In those same drives the car was up to **15 km/h over a known limit while FSD steered, with
  no chime**, and chimed in the same drives when the driver was over the limit manually.

So the suppression is real but is not carried on any bus the comma taps. The display already
receives `DAS_autopilotState` (it needs it to draw the FSD visualisation) and almost certainly
decides for itself. Spoofing that state would tell the car and the driver that Tesla's FSD is
steering when it is not, so it is out of scope.

**Also learned along the way.** Injecting a copy of a message the car already sends on a free
running timer does not work: two 2 Hz streams with a drifting phase alternate perfectly and the
stock frame is the most recently received one ~50% of the time (measured: delta 0-493 ms
uniform, 49.7%). Echo on arrival of each stock frame instead. That fix was correct and is worth
remembering, even though the feature it served is gone.

**If you have a pre-Highland HW4 or a Juniper**, `0x399` probably does exist on your car and the
community implementations should work - but this branch will not ship it, because it cannot be
validated here.

## Fixed: the car's cruise controller faulting mid-drive

Reported as "the comma crashes while driving": red alert, loud takeover alarm, openpilot dead
until the next drive. It was never a crash. The log says `Cruise Fault: Restart the Car`
(`accFaulted/immediateDisable`) - the car's own cruise controller faulted and openpilot
disengaged correctly, and it stays down because the car wants a restart.

**Cause.** The soft gas threshold had no hysteresis. With the pedal resting exactly on it,
oscillating between 20.0% and 20.4% - raw 50 and 51, one bit apart - `gasPressed` toggled at the
sample rate, so `longActive` flipped 13 times in 1.5 s and `DAS_accelMin` jumped between 0 and
-1.2 m/s2 with `DAS_setSpeed` moving along, until the DI gave up. Not specific to the 20% window:
the same cliff sat at 10% before, which is why it predated widening it. Evidence: routes
`0000024f` segment 12 and `0000024e` segment 1.

**Fix.** Press at 20% (raw 50), release only below 17.2% (raw 43). Both land exactly on a bit at
0.4 %/bit, so `carstate.py` and the safety firmware agree bit for bit - checked over all 256 raw
values rising, falling, both boundary oscillations and 2000 random values. The logged oscillation
now gives one transition instead of twenty. Hysteresis latches `gasPressed` longer, never
shorter, so openpilot stops actuating sooner - the conservative direction.

**Diagnosed entirely from public comma-connect routes**, with the device unreachable:
`api.comma.ai/v1/route/<dongle>%7C<route>/files` needs no auth for a public route and returns
rlogs plus qlogs (qlogs upload over cellular, so they cover the whole drive). Alert strings and
swaglog lines are plain text in those files, so grepping the decompressed bytes finds the segment
and the event without any capnp.

## Following the car's read speed limit (pulse-triggered)

Investigated 2026-10-17, built 2026-10-20. Option `TeslaSpeedLimitPulse`, flag
`SPEED_LIMIT_PULSE = 4096`. Tesla-style automatic set-speed changes when the car reads a new
sign, **without transmitting anything new**.

**The design, in the driver's words.** The scroll wheel sets the ceiling; we only ever lower
from it, never raise above it. Only a *change* of the read limit acts (a pulse) - holding a
limit does nothing, so one scroll up settles a stale sign and nothing fights you afterwards.
A change of the car's own set speed can only be the driver, so that value is adopted as the new
ceiling and followed: manual always wins. Above `MOTORWAY_CUTOFF_KPH = 100` the feature does
nothing at all, because Tesla ignores motorway signs and braking from 120 to a slip-road sign is
exactly what must not happen.

**How it takes the set speed without transmitting.** Enabling the option also sets
`CP_SP.pcmCruiseSpeed = False`, which hands ownership of the set speed to openpilot:
`cruise.py` then stops copying `CS.cruiseState.speed` every cycle and our hook writes
`v_cruise_kph` instead. The car keeps its own set speed on its own screen - we never tell it
anything - and openpilot simply plans to a lower number. `pcmCruise` itself stays `True`.

**The settling window, and why it exists.** The speed limit resolver *freezes* its value while
cruise is off and only refreshes roughly 0.8 s **after** engaging. Measured on route
`00000266`: engaged at 55 with the resolver still holding 30 from the previous zone, 0.8 s later
it corrected to 50 and the pulse fired on that correction. Proof of the freeze in the same
drive: between t=118 and t=138 the car drove out of a 50 zone into a 30 zone with cruise off and
the resolver stayed on 50 the whole time. That refresh is indistinguishable from a sign change,
so for `SETTLE_CALLS = 200` (~2 s at the 100 Hz card loop) after engaging we keep re-baselining
`limit_prev` instead of acting. Without it, every single engagement immediately overrode the
driver's set speed with the *previous* zone's limit.

**The set speed stays on screen while we hold a different one.** The comma 4 reports its device
type as `mici`, so `ui/mici/onroad/hud_renderer.py` draws the HUD, and it fades the set speed out
`SET_SPEED_PERSISTENCE = 2.5` s after it last changed. That hid exactly the number the driver
needs to see. It now also stays up whenever `vCruiseCluster` differs from the car's own
`cruiseState.speedCluster` by more than 0.5 km/h. Side effect worth knowing: the set speed box
and the DMoji share the top-left corner (`drawing_top_icons()` gates the DMoji), so the driver
monitoring face is hidden for as long as a lowered speed is being held.

**Why not injection.** The only way to move the car's *own* set speed would be injecting scroll
ticks on bus 1. `VCLEFT_swcRightScrollTicks` (0x3C2 mux 1, bit 24, 6 bits signed) carries the
detent count and the DI does its own arithmetic on it - measured: ticks of 3 and 5 within 0.2 s
of each step. But `0x3C2` is not the steering wheel message, it is the whole left switch pack,
carrying window switches, seat adjustment, mirror tilt and the buckle switch in mux 0.
Transmitting there for a convenience feature is a different risk class from
`DAS_steeringControl`, it needs a new TX permission on a bus we never transmit on, and our own
button and tilt features read the same message. Nothing else carries it either: scanning 10 real
set-speed steps against every address on all three buses found no message whose bytes track the
set speed, and the statistical front-runners were artifacts (scroll clicks come 0.3 s apart, so
one unrelated 1 Hz message lands in every window). `DAS_setSpeed`, which we already send in
`DAS_control` every cycle as `(v_ego + accel)`, is not adopted as the set speed.

**Trap worth remembering:** `cruiseState.speed` comes from `DI_state.DI_digitalSpeed`, which is a
display field - with cruise off it tracks the current speed, with cruise on it is the set speed.
Any analysis of "set speed steps" must filter on `cruiseState.enabled` or the mode switches look
like driver input.

**Reading the pulse back out of a drive.** The temporary `SPEEDLIMITPULSE` line in
`cruise_ext.py` goes to `cloudlog`, which ends up as `logMessage` events **inside the rlog**, not
in `/data/log/swaglog.*` - grepping swaglog for it finds nothing even while it is running. The
device's capnp and zstandard live in `/usr/local/venv/bin/python3`, not in `/usr/bin/python3`.

## Fixed: a press-only cancel killing the whole non-pcm branch

Found 2026-10-22, while the speed limit pulse worked on some drives and not at all on others -
all or nothing, for a whole drive at a time. Two defects, one symptom.

**A cancel event that is never released.** `carstate_ext` synthesizes
`ButtonEvent(pressed=True, type=cancel)` and no matching release. `CRUISE_BUTTON_TIMER` in
`cruise_ext.py` tracked `cancel`, and `update_manual_button_timers` only clears a timer on a
`pressed=False` event, so that one press left the timer running forever. `update_enabled_state`
then kept `enabled_prev` at `False` for the rest of the drive, `cruise.py` took the pcm branch,
and everything behind `not pcmCruiseSpeed` - the speed limit pulse included - was simply never
called again. Cancel is now out of that timer: it can never be the engaging button, which is the
only question those timers answer. The cancel's own disengage path is untouched, because
`car_events.py` and `mads.py` read `buttonEvents` directly and match on type regardless of
`pressed`.

**A stray cancel at every cold wake in Park.** The first CAN frames of a drive report
`gearShifter == unknown`, so the next frame read `unknown -> park` as a shift into Park and
fired the all-off cancel pulse at t=0.00. Guarded on `unknown` now.

**The measurement that settled it**, per route: first `carParamsSP`, every `cancel` event, and
the time span of the `SPEEDLIMITPULSE` lines.

```
00000267  flags=6757  cancel op 0s (park)        pulselog: geen
00000268  flags=6757  cancel op 798s, 944s       pulselog: 25s .. 793s
0000026a  flags=6757  cancel op 567s, 820s       pulselog: 172s .. 566s
0000026b  flags=6757  cancel op 0s (park)        pulselog: geen
```

The flags are identical on working and dead drives, and every log span ends at the first cancel.
That pair of facts is what rules out the parameters and points at the gate.

**Worth remembering:** a press-only button event is an abuse of the protocol and it breaks any
timer-based consumer silently and permanently. There are two of them in this tree
(`VCruiseHelperSP` and the ICBM controller) and they live in different processes, so the shared
module-level `CRUISE_BUTTON_TIMER` dict they both alias never actually collides at runtime.

## Updating from upstream sunnypilot
This branch does **not** track upstream automatically. To pull in new sunnypilot master:
merge `sunnypilot/sunnypilot@master` into `tesla-custom` (and rebase the opendbc fork onto the
newly pinned opendbc commit, re-applying the safety changes), re-run CI, then
`git push fork tesla-custom tesla-custom:tesla` — the device updater then picks it up.
