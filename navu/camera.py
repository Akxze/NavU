"""Pan and zoom transform for the floor-plan view.

Kept free of Kivy so the maths can be reasoned about (and tested) on its own.
The camera works in two spaces:

* **plan space** -- normalized ``(x, y)`` in ``0.0..1.0`` across the plan image,
  which is the space the route graph and room positions use.
* **screen space** -- Kivy window pixels.

A floor change swaps the plan underneath, so the camera owns no floor state; it
only knows how to place a plan rectangle on screen.
"""

from .theme import (
    MAP_MAX_ZOOM,
    MAP_MIN_ZOOM,
    MAP_ROUTE_MAX_ZOOM,
    MAP_ZOOM_STEP,
)


class MapCamera:
    """Maps plan coordinates to screen coordinates and back."""

    def __init__(self):
        self.zoom = 1.0
        self.minimum_zoom = MAP_MIN_ZOOM
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.extra_pan_down = 0.0
        self._viewport = (0.0, 0.0, 0.0, 0.0)
        self._plan_fit = (0.0, 0.0, 0.0, 0.0)

    # ------------------------------------------------------------------
    # Viewport
    # ------------------------------------------------------------------
    def set_viewport(self, x, y, width, height):
        """Set the widget rectangle the plan is drawn inside."""
        self._viewport = (x, y, width, height)
        self._clamp_pan()

    @property
    def viewport(self):
        return self._viewport

    def set_plan_fit(self, x, y, width, height):
        """Set where the plan sits inside the viewport at zoom 1."""
        self._plan_fit = (x, y, width, height)
        self._clamp_pan()

    def set_extra_pan_down(self, offset):
        """Allow the plan to pan farther below the viewport's bottom edge."""
        self.extra_pan_down = max(0.0, float(offset))
        self._clamp_pan()

    def set_minimum_zoom(self, zoom):
        """Keep the plan large enough to cover the viewport."""
        self.minimum_zoom = max(
            MAP_MIN_ZOOM,
            min(MAP_MAX_ZOOM, zoom),
        )
        if self.zoom < self.minimum_zoom:
            self.zoom = self.minimum_zoom
        self._clamp_pan()

    @property
    def plan_fit(self):
        return self._plan_fit

    # ------------------------------------------------------------------
    # Derived rectangles
    # ------------------------------------------------------------------
    def plan_rect(self):
        """Screen rectangle ``(x, y, width, height)`` of the plan right now."""
        fit_x, fit_y, fit_width, fit_height = self._plan_fit
        view_x, view_y, view_width, view_height = self._viewport
        origin_x = view_x + view_width / 2.0
        origin_y = view_y + view_height / 2.0

        width = fit_width * self.zoom
        height = fit_height * self.zoom
        x = origin_x + (fit_x - origin_x) * self.zoom + self.pan_x
        y = origin_y + (fit_y - origin_y) * self.zoom + self.pan_y
        return x, y, width, height

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------
    def project(self, point):
        """Plan point to screen point."""
        rect_x, rect_y, rect_width, rect_height = self.plan_rect()
        return (
            rect_x + point[0] * rect_width,
            rect_y + point[1] * rect_height,
        )

    def unproject(self, point):
        """Screen point back to plan point. Returns ``None`` outside the plan."""
        rect_x, rect_y, rect_width, rect_height = self.plan_rect()
        if not rect_width or not rect_height:
            return None
        plan_x = (point[0] - rect_x) / rect_width
        plan_y = (point[1] - rect_y) / rect_height
        if not (0.0 <= plan_x <= 1.0 and 0.0 <= plan_y <= 1.0):
            return None
        return plan_x, plan_y

    def contains(self, point):
        """True when a plan point is inside the visible plan rectangle."""
        rect_x, rect_y, rect_width, rect_height = self.plan_rect()
        screen_x, screen_y = self.project(point)
        return (
            rect_x <= screen_x <= rect_x + rect_width
            and rect_y <= screen_y <= rect_y + rect_height
        )

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------
    def clamp_zoom(self, zoom):
        return max(self.minimum_zoom, min(MAP_MAX_ZOOM, zoom))

    def zoom_by(self, steps, anchor=None):
        """Zoom in or out, keeping ``anchor`` (screen point) fixed."""
        target = self.clamp_zoom(self.zoom + steps * MAP_ZOOM_STEP)
        self.zoom_to(target, anchor)

    def zoom_to(self, zoom, anchor=None):
        """Set an absolute zoom, optionally holding a screen point still."""
        previous = self.zoom
        self.zoom = self.clamp_zoom(zoom)
        if anchor is None or previous == self.zoom:
            return
        # Keep the plan point under `anchor` under `anchor` after zooming.
        plan_point = self._unproject_unclamped(anchor)
        if plan_point is None:
            return
        rect_x, rect_y, rect_width, rect_height = self.plan_rect()
        target_x = anchor[0] - plan_point[0] * rect_width
        target_y = anchor[1] - plan_point[1] * rect_height
        self.pan_x += target_x - rect_x
        self.pan_y += target_y - rect_y
        self._clamp_pan()

    def _unproject_unclamped(self, point):
        """Like :meth:`unproject` but without the inside-the-plan guard."""
        rect_x, rect_y, rect_width, rect_height = self.plan_rect()
        if not rect_width or not rect_height:
            return None
        return (
            (point[0] - rect_x) / rect_width,
            (point[1] - rect_y) / rect_height,
        )

    def pan_by(self, delta_x, delta_y):
        self.pan_x += delta_x
        self.pan_y += delta_y
        self._clamp_pan()

    def reset(self):
        self.zoom = self.clamp_zoom(1.0)
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._clamp_pan()

    # ------------------------------------------------------------------
    # Framing
    # ------------------------------------------------------------------
    def center_on(self, plan_point, zoom=None):
        """Center the view on a plan point."""
        if zoom is not None:
            self.zoom = self.clamp_zoom(zoom)
        view_x, view_y, view_width, view_height = self._viewport
        fit_x, fit_y, fit_width, fit_height = self._plan_fit
        origin_x = view_x + view_width / 2.0
        origin_y = view_y + view_height / 2.0

        desired_x = view_x + view_width / 2.0
        desired_y = view_y + view_height / 2.0
        current_x = (
            origin_x + (fit_x - origin_x) * self.zoom
            + self.pan_x
            + plan_point[0] * fit_width * self.zoom
        )
        current_y = (
            origin_y + (fit_y - origin_y) * self.zoom
            + self.pan_y
            + plan_point[1] * fit_height * self.zoom
        )
        self.pan_x += desired_x - current_x
        self.pan_y += desired_y - current_y
        self._clamp_pan()

    def _clamp_pan(self):
        """Keep the plan over the viewport; center it when smaller than view."""
        rect_x, rect_y, rect_width, rect_height = self.plan_rect()
        view_x, view_y, view_width, view_height = self._viewport

        if rect_width <= view_width:
            self.pan_x += view_x + (view_width - rect_width) / 2 - rect_x
        else:
            base_x = rect_x - self.pan_x
            self.pan_x = min(
                view_x - base_x,
                max(
                    view_x + view_width - base_x - rect_width,
                    self.pan_x,
                ),
            )

        if rect_height <= view_height and self.extra_pan_down <= 0:
            self.pan_y += view_y + (view_height - rect_height) / 2 - rect_y
        else:
            base_y = rect_y - self.pan_y
            self.pan_y = min(
                view_y - base_y,
                max(
                    view_y + view_height - base_y - rect_height
                    - self.extra_pan_down,
                    self.pan_y,
                ),
            )

    def fit_points(
        self,
        points,
        padding_ratio=0.22,
        max_zoom=MAP_ROUTE_MAX_ZOOM,
    ):
        """Frame a set of plan points, the way a map zooms to a route.

        Returns ``True`` when a usable frame was found.
        """
        if not points:
            return False

        min_x = min(point[0] for point in points)
        max_x = max(point[0] for point in points)
        min_y = min(point[1] for point in points)
        max_y = max(point[1] for point in points)

        span_x = max(max_x - min_x, 0.02)
        span_y = max(max_y - min_y, 0.02)
        centre = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

        _, _, view_width, view_height = self._viewport
        _, _, fit_width, fit_height = self._plan_fit
        if not fit_width or not fit_height:
            return False

        usable = 1.0 - padding_ratio
        zoom_x = (view_width * usable) / (span_x * fit_width)
        zoom_y = (view_height * usable) / (span_y * fit_height)
        zoom = min(zoom_x, zoom_y)
        if max_zoom is not None:
            zoom = min(zoom, max_zoom)

        self.pan_x = 0.0
        self.pan_y = 0.0
        self.zoom = self.clamp_zoom(zoom)
        self.center_on(centre)
        return True

    def visible_plan_bounds(self):
        """Plan-space bounds currently visible, clamped to the plan."""
        view_x, view_y, view_width, view_height = self._viewport
        top_left = self._unproject_unclamped((view_x, view_y + view_height))
        bottom_right = self._unproject_unclamped(
            (view_x + view_width, view_y)
        )
        if top_left is None or bottom_right is None:
            return 0.0, 0.0, 1.0, 1.0
        return (
            max(0.0, top_left[0]),
            max(0.0, bottom_right[1]),
            min(1.0, bottom_right[0]),
            min(1.0, top_left[1]),
        )

    def meters_per_pixel(self, floor_width_meters):
        """Ground scale of the current view, for the scale bar."""
        _, _, rect_width, _ = self.plan_rect()
        if rect_width <= 0:
            return floor_width_meters
        return floor_width_meters / rect_width
