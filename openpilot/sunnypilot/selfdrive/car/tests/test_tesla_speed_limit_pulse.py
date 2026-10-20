"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.sunnypilot.selfdrive.car.tesla_speed_limit_pulse import SpeedLimitPulse, SETTLE_CALLS


def settle(pulse, car_set, limit):
  """Run the settling window out at a steady limit."""
  for _ in range(SETTLE_CALLS):
    pulse.update(True, car_set, limit)


class TestSpeedLimitPulse:
  def test_disabled_never_acts(self):
    pulse = SpeedLimitPulse(False)
    assert pulse.update(True, 70.0, 50.0) is None

  def test_cruise_off_releases(self):
    pulse = SpeedLimitPulse(True)
    assert pulse.update(False, 70.0, 50.0) is None
    assert pulse.update(True, 0.0, 50.0) is None

  def test_engage_keeps_the_cars_set_speed(self):
    pulse = SpeedLimitPulse(True)
    assert pulse.update(True, 55.0, 30.0) == 55.0

  def test_resolver_refresh_after_engaging_is_ignored(self):
    # measured on the car: the resolver holds the previous zone's limit while cruise is off and
    # refreshes ~0.8 s after engaging. That refresh must not count as a sign change.
    pulse = SpeedLimitPulse(True)
    assert pulse.update(True, 55.0, 30.0) == 55.0
    for _ in range(80):  # 0.8 s at 100 Hz
      assert pulse.update(True, 55.0, 30.0) == 55.0
    assert pulse.update(True, 55.0, 50.0) == 55.0
    assert pulse.update(True, 55.0, 50.0) == 55.0

  def test_sign_change_after_settling_lowers(self):
    pulse = SpeedLimitPulse(True)
    pulse.update(True, 55.0, 50.0)
    settle(pulse, 55.0, 50.0)
    assert pulse.update(True, 55.0, 30.0) == 30.0

  def test_sign_change_never_raises_above_the_ceiling(self):
    pulse = SpeedLimitPulse(True)
    pulse.update(True, 55.0, 50.0)
    settle(pulse, 55.0, 50.0)
    assert pulse.update(True, 55.0, 70.0) == 55.0

  def test_holding_a_limit_does_nothing(self):
    pulse = SpeedLimitPulse(True)
    pulse.update(True, 55.0, 50.0)
    settle(pulse, 55.0, 50.0)
    assert pulse.update(True, 55.0, 30.0) == 30.0
    for _ in range(1000):
      assert pulse.update(True, 55.0, 30.0) == 30.0

  def test_scroll_wheel_wins_and_sets_the_new_ceiling(self):
    pulse = SpeedLimitPulse(True)
    pulse.update(True, 55.0, 50.0)
    settle(pulse, 55.0, 50.0)
    assert pulse.update(True, 55.0, 30.0) == 30.0
    # driver scrolls up: follow them, and the limit we just overrode cannot pulse again
    assert pulse.update(True, 60.0, 30.0) == 60.0
    for _ in range(1000):
      assert pulse.update(True, 60.0, 30.0) == 60.0

  def test_motorway_ceiling_does_nothing(self):
    pulse = SpeedLimitPulse(True)
    pulse.update(True, 120.0, 120.0)
    settle(pulse, 120.0, 120.0)
    assert pulse.update(True, 120.0, 70.0) == 120.0

  def test_unknown_limit_does_nothing(self):
    pulse = SpeedLimitPulse(True)
    pulse.update(True, 55.0, 50.0)
    settle(pulse, 55.0, 50.0)
    assert pulse.update(True, 55.0, 0.0) == 55.0

  def test_offset_is_applied_to_the_limit(self):
    pulse = SpeedLimitPulse(True)
    pulse.update(True, 55.0, 50.0)
    for _ in range(SETTLE_CALLS):
      pulse.update(True, 55.0, 50.0, 5.0)
    assert pulse.update(True, 55.0, 30.0, 5.0) == 35.0

  def test_re_engage_settles_again(self):
    pulse = SpeedLimitPulse(True)
    pulse.update(True, 55.0, 50.0)
    settle(pulse, 55.0, 50.0)
    assert pulse.update(True, 55.0, 30.0) == 30.0
    assert pulse.update(False, 55.0, 30.0) is None
    # re-engaged at 35: the stale 30 refreshing to 25 must not act during the window
    assert pulse.update(True, 35.0, 30.0) == 35.0
    assert pulse.update(True, 35.0, 25.0) == 35.0
    settle(pulse, 35.0, 25.0)
    assert pulse.update(True, 35.0, 20.0) == 20.0
