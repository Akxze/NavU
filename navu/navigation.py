"""Live navigation state for the route screen.

``RouteScreen`` is presentation; this controller owns progress. It can be moved
either by a simulated walk (the demo mode, which is what makes the turn-by-turn
banner actually animate during a presentation) or by real GPS fixes, and it
exposes everything the banner and the step list need to render.
"""

from kivy.clock import Clock

from .directions import (
    RouteSession,
    format_distance,
    format_duration,
)
from .routing import WALKING_SPEED_METERS_PER_SECOND

WALK_TICK_SECONDS = 0.1


class NavigationController:
    """Drives a :class:`RouteSession` forward."""

    def __init__(self, on_update):
        self.session = RouteSession()
        self.destination_label = ""
        self.walking = False
        self._event = None
        self._on_update = on_update

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load(self, route, steps, total_meters, destination_label):
        """Start a fresh navigation run."""
        self._cancel_timer()
        self.session = RouteSession(
            route=list(route),
            steps=list(steps),
            total_meters=max(0.0, total_meters),
            travelled_meters=0.0,
        )
        self.destination_label = destination_label
        self._on_update()

    def clear(self):
        self.load([], [], 0.0, "")

    @property
    def is_loaded(self):
        return bool(self.session.steps)

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------
    def set_progress(self, meters):
        self.session.travelled_meters = max(
            0.0, min(meters, self.session.total_meters)
        )
        self._on_update()

    def reset_progress(self):
        self.set_progress(0.0)

    def push_progress(self, meters):
        """Advance by ``meters``, as a GPS fix would."""
        self.set_progress(self.session.travelled_meters + meters)

    def advance_to_next_maneuver(self):
        """Step to the next maneuver point, the way "Next step" behaves."""
        step = self.session.active_step
        if step is None:
            return
        if step.kind != "arrive":
            self.set_progress(step.cumulative_meters + 0.01)
            return
        self.set_progress(self.session.total_meters)

    def jump_to_step(self, index):
        if 0 <= index < len(self.session.steps):
            self.set_progress(self.session.steps[index].cumulative_meters)

    # ------------------------------------------------------------------
    # Simulated walking (demo mode)
    # ------------------------------------------------------------------
    def start_walking(self):
        if self.walking or not self.session.total_meters:
            return
        if self.session.has_arrived:
            return
        self.walking = True
        self._event = Clock.schedule_interval(
            self._walk_tick, WALK_TICK_SECONDS
        )
        self._on_update()

    def stop_walking(self):
        had_timer = self._cancel_timer()
        self.walking = False
        if had_timer:
            self._on_update()

    def toggle_walking(self):
        if self.walking:
            self.stop_walking()
        else:
            self.start_walking()

    def _cancel_timer(self):
        if self._event is None:
            return False
        self._event.cancel()
        self._event = None
        return True

    def _walk_tick(self, elapsed):
        travelled = (
            self.session.travelled_meters
            + WALKING_SPEED_METERS_PER_SECOND * elapsed
        )
        self.session.travelled_meters = min(
            travelled, self.session.total_meters
        )
        if self.session.has_arrived:
            self._cancel_timer()
            self.walking = False
        self._on_update()

    # ------------------------------------------------------------------
    # Read-out
    # ------------------------------------------------------------------
    @property
    def active_step(self):
        return self.session.active_step

    @property
    def next_step(self):
        return self.session.up_next_step

    @property
    def arrived(self):
        return self.session.has_arrived and bool(self.session.steps)

    @property
    def remaining_label(self):
        return format_duration(self.session.remaining_seconds)

    @property
    def distance_label(self):
        return format_distance(self.session.remaining_meters)

    @property
    def maneuver_distance_label(self):
        return format_distance(self.session.distance_to_maneuver)

    @property
    def progress(self):
        return self.session.progress

    @property
    def active_step_index(self):
        return self.session.active_step_index
