# tesla-custom — personal test branch

Personal sunnypilot fork branch for a **Tesla Model 3 Highland (HW4, 2026) + comma 4**.
Based on sunnypilot `master` (2026-07-03). **Not tested on a real car until noted otherwise — use at your own risk.**

Install URL: `installer.comma.ai/RWEnergoo/tesla` (branch `tesla` is an alias of `tesla-custom`).

## Features (all behind default-OFF toggles, sunnylink app → Vehicle → Tesla)

### 1. Cruise Button Toggles Engagement (`TeslaButtonCancels`)
Stock behavior: with sunnypilot longitudinal (alpha) engaged, pressing the cruise/engage button does
nothing — the DI briefly reports `DI_cruiseState = PRE_CANCEL`, but both sunnypilot and the panda
count PRE_CANCEL as "engaged" and sunnypilot keeps commanding `ACC_ON` at 25 Hz, swallowing the press.

With this toggle: **hold either scroll wheel pressed** (0.5–2 s, configurable via
`TeslaButtonCancelHoldDuration`, default 1 s) while engaged to disengage
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

## Changed files
Main repo (this branch) and `opendbc_repo` submodule → `RWEnergoo/opendbc@tesla-custom`
(see `.gitmodules`). Full list: `git log --stat master..tesla-custom` in both repos.

New params: `TeslaButtonCancels`, `TeslaSteerOverridePauses`, `TeslaSteerOverrideResumeDelay`
(`common/params_keys.h`, plumbed via `sunnypilot/selfdrive/car/interfaces.py` →
`opendbc/sunnypilot/car/interfaces.py` → `CarParamsSP.flags`).

## Testing
- opendbc safety suite + mutation tests: **green** (CI via https://github.com/RWEnergoo/opendbc/pull/1,
  new tests in `opendbc/safety/tests/test_tesla.py` and `opendbc/safety/tests/mads_common.py`).
- On-car test order: (1) `TeslaButtonCancels` alone — validates the PRE_CANCEL assumption;
  (2) Steering Mode on Brake Pedal = Remain Active; (3) `TeslaSteerOverridePauses`.

## Updating from upstream sunnypilot
This branch does **not** track upstream automatically. To pull in new sunnypilot master:
merge `sunnypilot/sunnypilot@master` into `tesla-custom` (and rebase the opendbc fork onto the
newly pinned opendbc commit, re-applying the safety changes), re-run CI, then
`git push fork tesla-custom tesla-custom:tesla` — the device updater then picks it up.
