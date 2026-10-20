"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

# Tesla: follow the speed limit the car itself reads, pulse-triggered.
#
# The driver's set speed is the CEILING: we only ever lower from it, never raise above it.
# A change of the car's own set speed can only be the driver (we never transmit), so that
# value is adopted as the new ceiling and simply followed - "manual wins".
#
# Only a CHANGE of the read limit acts (a pulse). Holding a limit does nothing, which is what
# makes this usable where a sign is stale: scroll up once and nothing fights you, because no
# new pulse arrives until the car reads a different limit.
#
# Above the motorway cut-off the feature does nothing at all: Tesla ignores motorway signs,
# and braking from 120 to a slip-road sign is exactly what must not happen.

MOTORWAY_CUTOFF_KPH = 100.0

# The speed limit resolver freezes its value while cruise is off and only refreshes a moment
# after engaging (measured: ~0.8 s). That refresh looks exactly like a sign change, so without
# a settling window the very first pulse of every drive fires on the PREVIOUS zone's limit.
# While settling we keep re-baselining instead of acting, so the driver's own set speed stands.
SETTLE_CALLS = 200  # ~2 s at the 100 Hz card loop


class SpeedLimitPulse:
  def __init__(self, enabled: bool):
    self.enabled = enabled
    self.reset()

  def reset(self) -> None:
    self.ceiling_kph = 0.0
    self.target_kph = 0.0
    self.limit_prev_kph = 0.0
    self.car_set_prev_kph = 0.0
    self.settle_calls = 0
    self.active = False

  def update(self, cruise_enabled: bool, car_set_speed_kph: float, speed_limit_kph: float,
             offset_kph: float = 0.0) -> float | None:
    """Returns the set speed openpilot should hold, or None to leave it alone."""
    if not self.enabled or not cruise_enabled or car_set_speed_kph <= 0.0:
      self.reset()
      return None

    if not self.active:
      # first frame of this engagement: the car's set speed is the ceiling
      self.active = True
      self.ceiling_kph = car_set_speed_kph
      self.target_kph = car_set_speed_kph
      self.limit_prev_kph = speed_limit_kph
      self.car_set_prev_kph = car_set_speed_kph
      self.settle_calls = SETTLE_CALLS
      return self.target_kph

    if car_set_speed_kph != self.car_set_prev_kph:
      # the driver turned the scroll wheel: follow them and take it as the new ceiling.
      # limit_prev is deliberately NOT refreshed, so a limit we just overrode cannot pulse again.
      self.car_set_prev_kph = car_set_speed_kph
      self.ceiling_kph = car_set_speed_kph
      self.target_kph = car_set_speed_kph
      return self.target_kph

    if self.settle_calls > 0:
      # let the resolver catch up after engaging before any limit change counts as a pulse
      self.settle_calls -= 1
      self.limit_prev_kph = speed_limit_kph
      return self.target_kph

    if speed_limit_kph != self.limit_prev_kph:
      self.limit_prev_kph = speed_limit_kph
      # a limit of 0 means "none known" - never act on that
      if speed_limit_kph > 0.0 and self.ceiling_kph < MOTORWAY_CUTOFF_KPH:
        self.target_kph = min(self.ceiling_kph, speed_limit_kph + offset_kph)

    return self.target_kph
