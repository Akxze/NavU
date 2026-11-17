"""The interactive floor-plan view.

Drawing happens in Python canvas instructions rather than KV because the route
needs per-turn rotated chevrons, a travelled/remaining split and a heading cone,
none of which KV expresses comfortably. KV still supplies the floor-plan image
and the floating labels on top.
"""

import math
import re
import xml.etree.ElementTree as ET

from kivy.animation import Animation
from kivy.core.text import Label as CoreLabel
from kivy.graphics import (
    ClearBuffers,
    ClearColor,
    Color,
    Ellipse,
    Fbo,
    InstructionGroup,
    Line,
    PopMatrix,
    PushMatrix,
    Rectangle,
    Rotate,
    StencilPop,
    StencilPush,
    StencilUnUse,
    StencilUse,
    Translate,
)
from kivy.graphics.svg import Svg
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.floatlayout import FloatLayout

from . import theme
from .camera import MapCamera
from .config import discover_floorplan_image
from .directions import point_at_distance
from .routing import (
    FLOOR_PLAN_METERS_PER_AXIS,
    LEVELS,
    NODES,
    PROVISIONAL_FLOOR_WIDTH_METERS,
    vertical_kind_between,
)

# Touch tuning.
TAP_SLOP = dp(9)
DOUBLE_TAP_ZOOM_STEP = 1
FOLLOW_ZOOM = 2.2
STRAIGHT_TURN_LIMIT = math.radians(20)
CHEVRON_SPREAD_ANGLE = math.radians(150)

USER_DOT_RADIUS = dp(9)
USER_RING_WIDTH = dp(3)
DESTINATION_RADIUS = dp(11)
CHEVRON_LENGTH = dp(11)
CHEVRON_SPREAD = dp(6)
SCALE_BAR_MAX_WIDTH = dp(96)
_FLOORPLAN_TEXTURES = {}


def _svg_number(value):
    match = re.search(r"-?\d+(?:\.\d+)?", value or "")
    return float(match.group()) if match else None


def _render_floorplan_texture(source, floor):
    """Rasterize an SVG floor plan and its text using Kivy's bundled renderer."""
    cached = _FLOORPLAN_TEXTURES.get(source)
    if cached is not None:
        return cached

    # Keep only the active floor texture; retaining every visited floor uses
    # unnecessary graphics memory on lower-memory Android devices.
    _FLOORPLAN_TEXTURES.clear()
    width = int(LEVELS[floor]["width"])
    height = int(LEVELS[floor]["height"])
    fbo = Fbo(size=(width, height))
    with fbo:
        ClearColor(0, 0, 0, 0)
        ClearBuffers()
        Svg(source=source)

        root = ET.parse(source).getroot()
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "text":
                continue
            text = "".join(element.itertext()).strip()
            x = _svg_number(element.get("x"))
            y = _svg_number(element.get("y"))
            if not text or x is None or y is None:
                continue

            translate = re.search(
                r"translate\(\s*(-?\d+(?:\.\d+)?)"
                r"(?:[ ,]+(-?\d+(?:\.\d+)?))?\s*\)",
                element.get("transform", ""),
            )
            if translate:
                x += float(translate.group(1))
                y += float(translate.group(2) or 0)

            font_size = _svg_number(element.get("font-size")) or 12
            fill = element.get("fill", "#16213E")
            color_match = re.fullmatch(
                r"#([0-9a-fA-F]{6})", fill.strip()
            )
            if color_match:
                value = color_match.group(1)
                color = tuple(
                    int(value[index:index + 2], 16) / 255
                    for index in (0, 2, 4)
                ) + (1,)
            else:
                color = (0.086, 0.106, 0.145, 1)

            label = CoreLabel(
                text=text,
                font_size=font_size,
                color=color,
            )
            label.refresh()
            texture = label.texture
            anchor = element.get("text-anchor", "start")
            label_x = x
            if anchor == "middle":
                label_x -= texture.width / 2
            elif anchor == "end":
                label_x -= texture.width

            baseline_y = height - y
            label_y = baseline_y - texture.height * 0.82
            rotate = re.search(
                r"rotate\(\s*(-?\d+(?:\.\d+)?)", element.get("transform", "")
            )
            if rotate:
                fbo.add(PushMatrix())
                fbo.add(
                    Rotate(
                        angle=-float(rotate.group(1)),
                        origin=(x, baseline_y),
                    )
                )
            fbo.add(Color(*color))
            fbo.add(
                Rectangle(
                    texture=texture,
                    pos=(label_x, label_y),
                    size=texture.size,
                )
            )
            if rotate:
                fbo.add(PopMatrix())

    fbo.draw()
    _FLOORPLAN_TEXTURES[source] = fbo.texture
    return fbo.texture


def _svg_to_plan(point, floor):
    """Convert graph/SVG coordinates (origin at top left) to camera coordinates."""
    level = LEVELS[floor]
    return point[0] / level["width"], 1 - point[1] / level["height"]


def _plan_to_svg(point, floor):
    """Convert camera coordinates back to graph/SVG coordinates."""
    level = LEVELS[floor]
    return point[0] * level["width"], (1 - point[1]) * level["height"]


class RouteMap(FloatLayout):
    """Pannable, zoomable floor plan with a live navigation overlay."""

    current_floor = StringProperty("1")
    floorplan_source = StringProperty("")

    route_nodes = ListProperty([])
    origin_node = StringProperty("")
    origin_position = ListProperty([])
    origin_floor = StringProperty("")
    destination_node = StringProperty("")

    travelled_meters = NumericProperty(0.0)
    total_meters = NumericProperty(0.0)

    follow_user = BooleanProperty(False)
    origin_callback = ObjectProperty(None, allownone=True)
    tap_callback = ObjectProperty(None, allownone=True)
    tap_blocker = ObjectProperty(None, allownone=True)

    compass_angle = NumericProperty(0.0)
    scale_label = StringProperty("")
    scale_bar_width = NumericProperty(0.0)
    zoom_level = NumericProperty(1.0)
    origin_pulse_scale = NumericProperty(1.0)
    origin_pulse_alpha = NumericProperty(0.28)
    route_line_pulse_alpha = NumericProperty(1.0)

    def __init__(self, **kwargs):
        self.camera = MapCamera()
        self._chevron_lines = []
        self._gps_position = None
        self._gps_anchor = None
        self._gps_anchor_coordinates = None
        self._gps_accuracy_meters = None
        self._active_touches = {}
        self._pinch_start = None
        self._pan_start = None
        self._drag_distance = 0.0
        self._double_tap = False
        self._origin_dragging = False
        self._origin_drag_candidate = None
        self._origin_drag_original = None
        self._origin_pulse_animation = None
        self._route_line_pulse_animation = None
        self._transition_markers = []
        super().__init__(**kwargs)
        self._build_canvas()
        self.bind(
            current_floor=self._on_current_floor_changed,
            origin_pulse_scale=self._on_origin_pulse_changed,
            origin_pulse_alpha=self._on_origin_pulse_changed,
            route_line_pulse_alpha=self._on_route_line_pulse_changed,
            follow_user=self._on_follow_user_changed,
        )

    # ------------------------------------------------------------------
    # Canvas plumbing
    # ------------------------------------------------------------------
    def _build_canvas(self):
        with self.canvas.before:
            self._background_color = Color(*theme.PAPER_DIM)
            self._background = Rectangle(pos=self.pos, size=self.size)
            StencilPush()
            self._stencil_rect_before = Rectangle(pos=self.pos, size=self.size)
            StencilUse()
        self.bind(pos=self._sync_background, size=self._sync_background)

        with self.canvas.after:
            StencilPush()
            self._plan_clip_rect = Rectangle(pos=(0, 0), size=(0, 0))
            StencilUse()

            self._route_line_group = InstructionGroup()
            self.canvas.after.add(self._route_line_group)
            self._route_line_casings = []
            self._route_lines = []
            self._route_line_colors = []
            self._route_line_casing_colors = []
            self._ensure_route_line_count(1)

            self._route_chevrons = InstructionGroup()
            self.canvas.after.add(self._route_chevrons)

            # Map markers use RouteMap-local coordinates, then translate into
            # the canvas space shared with the floor-plan image.
            PushMatrix()
            self._user_marker_transform = Translate(x=self.x, y=self.y)
            self._transition_marker_group = InstructionGroup()
            self.canvas.after.add(self._transition_marker_group)

            # GPS uncertainty halo.
            self._accuracy_color = Color(*theme.alpha(theme.NAVY_500, 0.18))
            self._accuracy = Ellipse(pos=(0, 0), size=(0, 0))

            # Destination pin: shadow, body, inner disc.
            self._pin_shadow_color = Color(*theme.alpha(theme.NAVY_900, 0.22))
            self._pin_shadow = Ellipse(pos=(0, 0), size=(0, 0))
            self._pin_color = Color(*theme.DESTINATION)
            self._pin_body = Ellipse(pos=(0, 0), size=(0, 0))
            self._pin_inner_color = Color(*theme.DESTINATION_INNER)
            self._pin_inner = Ellipse(pos=(0, 0), size=(0, 0))

            # The selected start stays marked while the navigation puck moves.
            self._origin_pulse_color = Color(
                *theme.alpha(theme.GOLD_500, self.origin_pulse_alpha)
            )
            self._origin_pulse = Ellipse(pos=(0, 0), size=(0, 0))
            self._origin_ring_color = Color(*theme.WHITE)
            self._origin_ring = Ellipse(pos=(0, 0), size=(0, 0))
            self._origin_color = Color(*theme.GOLD_500)
            self._origin_dot = Ellipse(pos=(0, 0), size=(0, 0))

            # The walker: white ring, navy puck, heading chevron.
            self._user_ring_color = Color(*theme.alpha(theme.USER_RING, 0.92))
            self._user_ring = Ellipse(pos=(0, 0), size=(0, 0))
            self._user_color = Color(*theme.USER_DOT)
            self._user_dot = Ellipse(pos=(0, 0), size=(0, 0))
            self._heading_color = Color(*theme.GOLD_500)
            self._heading = Line(points=[], width=dp(3.4), joint="round", cap="round")
            PopMatrix()

            StencilUnUse()
            self._plan_unclip_rect = Rectangle(pos=(0, 0), size=(0, 0))
            StencilPop()

            StencilUnUse()
            self._stencil_rect_after = Rectangle(pos=self.pos, size=self.size)
            StencilPop()

        self._hide_all()

    def _hide_all(self):
        """Collapse every overlay so nothing is drawn before a route exists."""
        self._set_route_lines([])
        self._update_chevrons([])
        for ellipse in (
            self._accuracy,
            self._pin_shadow,
            self._pin_body,
            self._pin_inner,
            self._origin_pulse,
            self._origin_ring,
            self._origin_dot,
            self._user_ring,
            self._user_dot,
        ):
            ellipse.size = (0, 0)
            ellipse.pos = (0, 0)
        self._heading.points = []
        for marker in self._transition_markers:
            marker["ring"].pos = (0, 0)
            marker["ring"].size = (0, 0)
            marker["badge"].pos = (0, 0)
            marker["badge"].size = (0, 0)
            for icon_line in marker["icon_lines"]:
                icon_line.points = []

    def _clear_route_canvas(self):
        """Remove old route instructions without touching the floor-plan canvas."""
        self._set_route_lines([])
        self._route_line_group.clear()
        self._route_line_casings.clear()
        self._route_lines.clear()
        self._route_line_colors.clear()
        self._route_line_casing_colors.clear()
        self._ensure_route_line_count(1)
        self._route_chevrons.clear()
        self._chevron_lines.clear()

    def _on_current_floor_changed(self, _instance, _floor):
        self._clear_route_canvas()
        self._build_transition_markers(_floor)
        self._hide_all()
        self._gps_anchor = None
        self._gps_anchor_coordinates = None
        self._gps_accuracy_meters = None
        self._gps_position = None

    def _on_origin_pulse_changed(self, *_args):
        self._redraw()

    def _on_route_line_pulse_changed(self, *_args):
        for color in self._route_line_colors:
            color.a = self.route_line_pulse_alpha

    def _on_follow_user_changed(self, *_args):
        self._set_origin_pulse_active(
            not self.follow_user
            and bool(self.origin_position)
            and bool(self.origin_floor)
        )
        self._redraw()

    def _sync_background(self, *_args):
        self._background.pos = self.pos
        self._background.size = self.size
        self._user_marker_transform.x = self.x
        self._user_marker_transform.y = self.y
        self._stencil_rect_before.pos = self.pos
        self._stencil_rect_before.size = self.size
        self._stencil_rect_after.pos = self.pos
        self._stencil_rect_after.size = self.size
        self._sync_plan_clip()
        if self._background_color:
            self._background_color.rgba = theme.PAPER_DIM

    def _sync_plan_clip(self):
        viewport = (self.pos, self.size)
        self._plan_clip_rect.pos = viewport[0]
        self._plan_clip_rect.size = viewport[1]
        self._plan_unclip_rect.pos = viewport[0]
        self._plan_unclip_rect.size = viewport[1]

    # ------------------------------------------------------------------
    # Layout -> camera sync
    # ------------------------------------------------------------------
    def on_size(self, *_args):
        self._sync_camera()
        self._redraw()

    def on_pos(self, *_args):
        self._sync_camera()
        self._redraw()

    def _sync_camera(self):
        """Refit the camera to the widget and the current plan image."""
        self.camera.set_viewport(self.x, self.y, self.width, self.height)
        self._fit_plan_rect()
        self.zoom_level = self.camera.zoom

    def set_extra_pan_down(self, offset):
        """Expose additional downward map travel while the sheet is raised."""
        self.camera.set_extra_pan_down(offset)
        self._redraw()

    def _fit_plan_rect(self):
        """Fit the entire floor plan inside the viewport at the base zoom."""
        image = self.ids.get("floorplan_image")
        texture = image.texture if image is not None else None
        if texture is None or not texture.width or not texture.height:
            self.camera.set_plan_fit(self.x, self.y, self.width, self.height)
            self.camera.set_minimum_zoom(theme.MAP_MIN_ZOOM)
            return

        if not self.width or not self.height:
            return

        image_ratio = texture.width / texture.height
        viewport_ratio = self.width / self.height
        if image_ratio > viewport_ratio:
            width = self.width
            height = width / image_ratio
        else:
            height = self.height
            width = height * image_ratio
        self.camera.set_plan_fit(
            self.center_x - width / 2,
            self.center_y - height / 2,
            width,
            height,
        )
        _, _, fit_width, fit_height = self.camera.plan_fit
        minimum_zoom = max(
            self.width / fit_width,
            self.height / fit_height,
        )
        self.camera.set_minimum_zoom(minimum_zoom)

    def on_kv_post(self, _base_widget):
        image = self.ids.get("floorplan_image")
        if image is not None:
            image.bind(texture=self._on_texture_ready)

    def _on_texture_ready(self, *_args):
        self._sync_camera()
        self._redraw()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_floor(self, floor, keep_follow=False):
        """Swap floor imagery and reset the camera/overlays as one update."""
        if floor == "lower_ground":
            floor = "LG"
        floor_changed = floor != self.current_floor
        if floor_changed:
            self.camera.set_minimum_zoom(theme.MAP_MIN_ZOOM)
            self.camera.reset()
            image = self.ids.get("floorplan_image")
            if image is not None:
                image.texture = None
        self.current_floor = floor
        self.floorplan_source = discover_floorplan_image(floor)
        image = self.ids.get("floorplan_image")
        if image is not None:
            image.source = ""
            image.texture = (
                _render_floorplan_texture(self.floorplan_source, floor)
                if self.floorplan_source
                else None
            )
        self.follow_user = keep_follow
        self._sync_camera()
        if keep_follow and self.walker_floor == floor:
            self._focus_user()
        self._redraw()

    def set_route(self, nodes, origin_node, destination_node, origin_position=None, origin_floor=""):
        """Give the map the route to draw."""
        self.route_nodes = list(nodes or [])
        self.origin_node = origin_node or ""
        self.destination_node = destination_node or ""
        self.origin_position = list(origin_position or [])
        self.origin_floor = origin_floor or ""
        self.travelled_meters = 0.0
        self._build_transition_markers(self.current_floor)
        self._set_origin_pulse_active(
            bool(self.origin_position) and bool(self.origin_floor)
        )
        self._redraw()

    def _build_transition_markers(self, floor=None):
        self._transition_marker_group.clear()
        self._transition_markers.clear()
        for first, second in zip(self.route_nodes, self.route_nodes[1:]):
            if first.floor == second.floor:
                continue
            kind = vertical_kind_between(first.node_id, second.node_id)
            for node in (first, second):
                if floor is not None and node.floor != floor:
                    continue
                ring_color = Color(*theme.WHITE)
                ring = Ellipse(pos=(0, 0), size=(0, 0))
                badge_color = Color(*theme.GOLD_500)
                badge = Ellipse(pos=(0, 0), size=(0, 0))
                icon_color = Color(*theme.NAVY_900)
                icon_lines = (
                    [Line(points=[], width=dp(2), cap="round", joint="round")]
                    if kind == "stairs"
                    else [
                        Line(points=[], width=dp(1.8), cap="round", joint="round")
                        for _ in range(3)
                    ]
                )
                for instruction in (
                    ring_color,
                    ring,
                    badge_color,
                    badge,
                    icon_color,
                    *icon_lines,
                ):
                    self._transition_marker_group.add(instruction)
                self._transition_markers.append(
                    {
                        "floor": node.floor,
                        "position": node.position,
                        "kind": kind,
                        "ring": ring,
                        "badge": badge,
                        "icon_lines": icon_lines,
                    }
                )

    def _set_origin_pulse_active(self, active):
        if self._origin_pulse_animation is not None:
            self._origin_pulse_animation.cancel(self)
            self._origin_pulse_animation = None
        self.origin_pulse_scale = 1.0
        self.origin_pulse_alpha = 0.28
        if active:
            self._origin_pulse_animation = Animation(
                origin_pulse_scale=1.7,
                origin_pulse_alpha=0.0,
                duration=1.0,
                t="out_quad",
            )
            self._origin_pulse_animation.repeat = True
            self._origin_pulse_animation.start(self)

    def set_progress(self, travelled_meters, total_meters):
        """Move the walker along the route."""
        self.travelled_meters = max(0.0, min(travelled_meters, total_meters))
        self.total_meters = max(0.0, total_meters)
        if self.follow_user:
            self._focus_user()
        self._redraw()

    def frame_route(self):
        """Zoom so the whole visible part of the route fits, like a maps app."""
        if not self.floorplan_source:
            self.camera.reset()
            self.camera.zoom_to(theme.MAP_INITIAL_ZOOM)
            self.zoom_level = self.camera.zoom
            self._redraw()
            return

        points = [
            point
            for segment in self._plan_segments_on_floor()
            for point in segment
        ]
        if not points:
            self.camera.reset()
        else:
            self.camera.fit_points(points, max_zoom=theme.MAP_ROUTE_MAX_ZOOM)
        self.zoom_level = self.camera.zoom
        self._redraw()

    def focus_user(self):
        """Enable follow mode and centre the walker."""
        self.follow_user = True
        self._focus_user()
        self._redraw()

    def release_follow(self):
        """Stop following, which happens as soon as the user pans away."""
        self.follow_user = False

    def zoom_in(self, *_args):
        self._zoom_and_redraw(1)

    def zoom_out(self, *_args):
        self._zoom_and_redraw(-1)

    def reset_view(self):
        self.follow_user = False
        self.camera.reset()
        self.camera.zoom_to(theme.MAP_INITIAL_ZOOM)
        self.zoom_level = self.camera.zoom
        self._redraw()

    def _zoom_and_redraw(self, steps, anchor=None):
        self.follow_user = False
        self.camera.zoom_by(steps, anchor)
        self.zoom_level = self.camera.zoom
        self._redraw()

    def _focus_user(self):
        point = self._user_plan_point()
        if point is not None:
            self.camera.center_on(point, zoom=max(self.camera.zoom, FOLLOW_ZOOM))

    # ------------------------------------------------------------------
    # GPS anchoring (unchanged behaviour, new plumbing)
    # ------------------------------------------------------------------
    def set_gps_anchor(self, position, latitude, longitude, accuracy=None):
        self._gps_anchor = tuple(position)
        self._gps_anchor_coordinates = (latitude, longitude)
        self._gps_accuracy_meters = accuracy
        self._gps_position = tuple(position)
        self._redraw()

    def update_gps_position(self, latitude, longitude, accuracy=None):
        if self._gps_anchor is None or self._gps_anchor_coordinates is None:
            return
        anchor_x, anchor_y = self._gps_anchor
        anchor_latitude, anchor_longitude = self._gps_anchor_coordinates

        meters_per_degree = 111_320
        east_meters = (
            (longitude - anchor_longitude)
            * meters_per_degree
            * math.cos(math.radians(anchor_latitude))
        )
        north_meters = (latitude - anchor_latitude) * meters_per_degree

        meters_per_unit = LEVELS[self.current_floor]["meters_per_unit"]
        self._gps_position = (
            anchor_x + east_meters / meters_per_unit,
            anchor_y - north_meters / meters_per_unit,
        )
        self._gps_accuracy_meters = accuracy
        self._redraw()

    def clear_gps_anchor(self):
        self._gps_anchor = None
        self._gps_anchor_coordinates = None
        self._gps_accuracy_meters = None
        self._gps_position = None
        self._redraw()

    # ------------------------------------------------------------------
    # Touch: drag the start marker, pan the plan, pinch to zoom, tap to set start
    # ------------------------------------------------------------------
    def on_touch_down(self, touch):
        # Let the floating controls on top claim the touch first.
        if super().on_touch_down(touch):
            return True
        if self.tap_blocker is not None and self.tap_blocker.collide_point(*touch.pos):
            return True
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)

        if touch.is_mouse_scrolling:
            steps = 1 if touch.button == "scrollup" else -1
            self._zoom_and_redraw(steps, touch.pos)
            return True

        if (
            len(self.origin_position) == 2
            and self.origin_floor == self.current_floor
            and self.travelled_meters <= 0.01
        ):
            marker = self.camera.project(
                _svg_to_plan(self.origin_position, self.origin_floor)
            )
            marker_radius = USER_DOT_RADIUS * 2.5
            if (
                (touch.x - marker[0]) ** 2 + (touch.y - marker[1]) ** 2
                <= marker_radius**2
            ):
                self._active_touches[touch.uid] = touch
                self._origin_dragging = True
                self._origin_drag_candidate = tuple(self.origin_position)
                self._origin_drag_original = tuple(self.origin_position)
                self._pan_start = None
                self._drag_distance = 0.0
                return True

        self._active_touches[touch.uid] = touch
        if len(self._active_touches) == 2:
            self._pinch_start = self._pinch_geometry()
            self._pan_start = None
            return True

        self._pan_start = (touch.x, touch.y)
        self._drag_distance = 0.0
        self._double_tap = bool(touch.is_double_tap)
        return True

    def on_touch_move(self, touch):
        if touch.uid not in self._active_touches:
            return super().on_touch_move(touch)

        if self._origin_dragging:
            self._drag_distance += abs(touch.dx) + abs(touch.dy)
            candidate = self.camera.unproject(touch.pos)
            if candidate is not None:
                svg_point = _plan_to_svg(candidate, self.current_floor)
                self._origin_drag_candidate = svg_point
                self.origin_position = list(svg_point)
                self._redraw()
            return True

        if len(self._active_touches) >= 2:
            self._handle_pinch()
            return True

        if self._pan_start is None:
            return True
        delta_x = touch.x - self._pan_start[0]
        delta_y = touch.y - self._pan_start[1]
        self._drag_distance += abs(delta_x) + abs(delta_y)
        self.camera.pan_by(delta_x, delta_y)
        self._pan_start = (touch.x, touch.y)
        if self._drag_distance > TAP_SLOP:
            self.release_follow()
        self._redraw()
        return True

    def on_touch_up(self, touch):
        if touch.uid not in self._active_touches:
            return super().on_touch_up(touch)

        if self._origin_dragging:
            candidate = self._origin_drag_candidate
            original = self._origin_drag_original
            self._origin_dragging = False
            self._origin_drag_candidate = None
            self._origin_drag_original = None
            del self._active_touches[touch.uid]
            self._pan_start = None
            self._drag_distance = 0.0
            accepted = (
                self.origin_callback(candidate)
                if self.origin_callback is not None and candidate is not None
                else False
            )
            if accepted is False and original is not None:
                self.origin_position = list(original)
            self._redraw()
            return True

        was_tap = self._drag_distance <= TAP_SLOP
        double_tapped = getattr(self, "_double_tap", False)
        del self._active_touches[touch.uid]
        if len(self._active_touches) < 2:
            self._pinch_start = None
        self._pan_start = None
        self._drag_distance = 0.0

        if was_tap and not self._active_touches:
            if double_tapped:
                self._zoom_and_redraw(1, touch.pos)
            else:
                self._emit_origin(touch.pos)
        return True

    def _emit_origin(self, screen_point):
        if (
            (self.tap_callback is None and self.origin_callback is None)
            or not self.floorplan_source
        ):
            return
        plan_point = self.camera.unproject(screen_point)
        if plan_point is not None:
            position = _plan_to_svg(plan_point, self.current_floor)
            callback = self.tap_callback or self.origin_callback
            callback(position)

    def _pinch_geometry(self):
        touches = list(self._active_touches.values())
        if len(touches) < 2:
            return None
        first, second = touches[0], touches[1]
        centre = ((first.x + second.x) / 2.0, (first.y + second.y) / 2.0)
        spread = max(
            dp(1),
            ((first.x - second.x) ** 2 + (first.y - second.y) ** 2) ** 0.5,
        )
        return centre, spread

    def _handle_pinch(self):
        current = self._pinch_geometry()
        if current is None or self._pinch_start is None:
            return
        centre, spread = current
        _, start_spread = self._pinch_start
        if start_spread <= 0:
            return
        ratio = spread / start_spread
        if abs(ratio - 1.0) < 0.02:
            return
        self.follow_user = False
        self.camera.zoom_to(self.camera.zoom * ratio, centre)
        self._pinch_start = current
        self.zoom_level = self.camera.zoom
        self._redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _redraw(self):
        self.camera.set_viewport(self.x, self.y, self.width, self.height)
        if not self.width or not self.height:
            self._hide_all()
            return
        self._sync_plan_clip()
        self._move_plan_image()
        self._draw_route()
        self._draw_transition_markers()
        self._draw_origin_marker()
        self._draw_user()
        self._draw_destination()
        self._update_scale_bar()

    def _draw_transition_markers(self):
        diameter = dp(31)
        badge_size = dp(26)
        for marker in self._transition_markers:
            ring = marker["ring"]
            badge = marker["badge"]
            icon_lines = marker["icon_lines"]
            if (
                not self.floorplan_source
                or marker["floor"] != self.current_floor
            ):
                ring.size = (0, 0)
                badge.size = (0, 0)
                for icon_line in icon_lines:
                    icon_line.points = []
                continue

            center = self._project_to_local(
                _svg_to_plan(marker["position"], marker["floor"])
            )
            ring.pos = (
                center[0] - diameter / 2,
                center[1] - diameter / 2,
            )
            ring.size = (diameter, diameter)
            badge.pos = (
                center[0] - badge_size / 2,
                center[1] - badge_size / 2,
            )
            badge.size = (badge_size, badge_size)
            if marker["kind"] == "stairs":
                icon_lines[0].points = [
                    center[0] - dp(6), center[1] - dp(5),
                    center[0] - dp(2), center[1] - dp(5),
                    center[0] - dp(2), center[1] - dp(1),
                    center[0] + dp(2), center[1] - dp(1),
                    center[0] + dp(2), center[1] + dp(3),
                    center[0] + dp(6), center[1] + dp(3),
                ]
            else:
                left, bottom = center[0] - dp(4), center[1] - dp(6)
                right, top = center[0] + dp(4), center[1] + dp(6)
                icon_lines[0].points = [
                    left, bottom, left, top, right, top, right, bottom,
                ]
                icon_lines[1].points = [
                    center[0], center[1] - dp(4),
                    center[0], center[1] + dp(1),
                    center[0] - dp(2), center[1] - dp(1),
                    center[0], center[1] + dp(1),
                    center[0] + dp(2), center[1] - dp(1),
                ]
                icon_lines[2].points = [
                    center[0], center[1] + dp(4),
                    center[0], center[1] - dp(1),
                    center[0] - dp(2), center[1] + dp(1),
                    center[0], center[1] - dp(1),
                    center[0] + dp(2), center[1] + dp(1),
                ]

    def _draw_origin_marker(self):
        self._origin_pulse_color.rgba = theme.alpha(
            theme.GOLD_500, self.origin_pulse_alpha
        )
        if (
            not self.floorplan_source
            or self.follow_user
            or len(self.origin_position) != 2
            or self.origin_floor != self.current_floor
        ):
            for marker in (
                self._origin_pulse,
                self._origin_ring,
                self._origin_dot,
            ):
                marker.pos = (0, 0)
                marker.size = (0, 0)
            return

        centre = self._project_to_local(
            _svg_to_plan(self.origin_position, self.origin_floor)
        )
        base_size = (USER_DOT_RADIUS + USER_RING_WIDTH) * 2
        pulse_size = base_size * self.origin_pulse_scale
        self._origin_pulse.pos = (
            centre[0] - pulse_size / 2,
            centre[1] - pulse_size / 2,
        )
        self._origin_pulse.size = (pulse_size, pulse_size)
        self._origin_ring.pos = (
            centre[0] - base_size / 2,
            centre[1] - base_size / 2,
        )
        self._origin_ring.size = (base_size, base_size)
        dot_size = USER_DOT_RADIUS * 1.5
        self._origin_dot.pos = (
            centre[0] - dot_size / 2,
            centre[1] - dot_size / 2,
        )
        self._origin_dot.size = (dot_size, dot_size)

    def _move_plan_image(self):
        """Keep the floor-plan image exactly under the camera transform."""
        image = self.ids.get("floorplan_image")
        if image is None:
            return
        rect_x, rect_y, rect_width, rect_height = self.camera.plan_rect()
        image.pos = (rect_x, rect_y)
        image.size = (rect_width, rect_height)

    def _plan_segments_on_floor(self):
        """Return connected route segments belonging only to the active floor."""
        segments = []
        segment = []
        for node in self.route_nodes:
            if node.floor == self.current_floor:
                segment.append(tuple(node.position))
            elif segment:
                segments.append(segment)
                segment = []
        if segment:
            segments.append(segment)

        if (
            segments
            and self.route_nodes
            and self.route_nodes[0].floor == self.current_floor
            and len(self.origin_position) == 2
            and self.origin_floor == self.current_floor
        ):
            origin = tuple(self.origin_position)
            if origin != segments[0][0]:
                segments[0].insert(0, origin)

        return [
            [_svg_to_plan(point, self.current_floor) for point in points]
            for points in segments
        ]

    def _plan_points_on_floor(self):
        """Return active-floor points for fitting the camera to the route."""
        return [
            point
            for segment in self._plan_segments_on_floor()
            for point in segment
        ]

    def _walker_state(self):
        """``(plan_point, floor, heading, arrived)`` for the current progress."""
        if not self.route_nodes:
            return None
        origin = (
            tuple(self.origin_position) if len(self.origin_position) == 2 else None
        )
        walker = point_at_distance(
            self.route_nodes, self.travelled_meters, origin, self.origin_floor
        )
        if walker is None:
            return None
        point, floor, heading, arrived = walker
        return _svg_to_plan(point, floor), floor, heading, arrived

    @property
    def walker_floor(self):
        """Floor currently occupied by the route-progress marker."""
        walker = self._walker_state()
        return walker[1] if walker is not None else ""

    def _user_plan_point(self):
        """Where the walker is, preferring route progress over raw GPS."""
        walker = self._walker_state()
        if walker is not None and walker[1] == self.current_floor:
            return walker[0]
        if self._gps_position is not None:
            point = _svg_to_plan(self._gps_position, self.current_floor)
            if _inside_plan(point):
                return point
        return None

    def _draw_route(self):
        if self._origin_dragging:
            self._set_route_line([])
            self._update_chevrons([])
            return

        segments = self._plan_segments_on_floor()
        if not self.floorplan_source:
            self._set_route_lines([])
            self._update_chevrons([])
            return

        screen_segments = [
            [self.camera.project(point) for point in segment]
            for segment in segments
            if len(segment) >= 2
        ]
        self._set_route_lines(screen_segments)
        self._update_chevrons(
            [
                chevron
                for screen in screen_segments
                for chevron in _chevron_segments(screen)
                if all(
                    self.x <= chevron[index] <= self.right
                    and self.y <= chevron[index + 1] <= self.top
                    for index in range(0, len(chevron), 2)
                )
            ]
        )

    def _set_route_line(self, points):
        self._set_route_lines([points] if points else [])

    def _ensure_route_line_count(self, count):
        while len(self._route_lines) < count:
            casing_color = Color(*theme.WHITE)
            casing = Line(points=[], width=dp(8), joint="round", cap="round")
            line_color = Color(*theme.GOLD_500)
            line = Line(points=[], width=dp(4.5), joint="round", cap="round")
            self._route_line_group.add(casing_color)
            self._route_line_group.add(casing)
            self._route_line_group.add(line_color)
            self._route_line_group.add(line)
            self._route_line_casing_colors.append(casing_color)
            self._route_line_casings.append(casing)
            self._route_line_colors.append(line_color)
            self._route_lines.append(line)
        self._route_line_casing = self._route_line_casings[0]
        self._route_line = self._route_lines[0]
        self._route_line_casing_color = self._route_line_casing_colors[0]
        self._route_line_pulse_color = self._route_line_colors[0]

    def _set_route_lines(self, segments):
        self._ensure_route_line_count(max(1, len(segments)))
        for index, casing in enumerate(self._route_line_casings):
            points = segments[index] if index < len(segments) else []
            casing.points = points
            self._route_lines[index].points = points

        for color in self._route_line_colors:
            color.a = self.route_line_pulse_alpha

        if any(len(points) >= 2 for points in segments):
            if self._route_line_pulse_animation is None:
                self.route_line_pulse_alpha = 1.0
                self._route_line_pulse_animation = (
                    Animation(route_line_pulse_alpha=0.3, duration=0.65)
                    + Animation(route_line_pulse_alpha=1.0, duration=0.65)
                )
                self._route_line_pulse_animation.repeat = True
                self._route_line_pulse_animation.start(self)
            return

        if self._route_line_pulse_animation is not None:
            self._route_line_pulse_animation.cancel(self)
            self._route_line_pulse_animation = None
        self.route_line_pulse_alpha = 1.0

    def _update_chevrons(self, chevrons):
        """Chevron arrowheads, one Line each so they never join up."""
        while len(self._chevron_lines) < len(chevrons):
            self._route_chevrons.add(Color(*theme.WHITE))
            line = Line(points=[], width=dp(2.6), joint="round", cap="round")
            self._route_chevrons.add(line)
            self._chevron_lines.append(line)

        for index, line in enumerate(self._chevron_lines):
            line.points = chevrons[index] if index < len(chevrons) else []

    def _draw_user(self):
        if not self.floorplan_source:
            self._user_ring.size = (0, 0)
            self._user_dot.size = (0, 0)
            self._accuracy.size = (0, 0)
            self._heading.points = []
            return

        walker = self._walker_state()
        on_route = walker is not None and walker[1] == self.current_floor

        point = None
        if on_route:
            point = walker[0]
        elif self._gps_position is not None:
            gps_point = _svg_to_plan(self._gps_position, self.current_floor)
            if _inside_plan(gps_point):
                point = gps_point

        if point is None:
            self._user_ring.size = (0, 0)
            self._user_dot.size = (0, 0)
            self._accuracy.size = (0, 0)
            self._heading.points = []
            return

        centre = self._project_to_local(point)
        ring_size = (USER_DOT_RADIUS + USER_RING_WIDTH) * 2
        dot_size = USER_DOT_RADIUS * 2
        self._user_ring.pos = (
            centre[0] - ring_size / 2,
            centre[1] - ring_size / 2,
        )
        self._user_ring.size = (ring_size, ring_size)
        self._user_dot.pos = (
            centre[0] - dot_size / 2,
            centre[1] - dot_size / 2,
        )
        self._user_dot.size = (dot_size, dot_size)

        if on_route and not walker[3]:
            # Bearing 0 is north, which is up on the plan.
            angle = math.radians(90.0 - walker[2])
            tip_x = centre[0] + math.cos(angle) * USER_DOT_RADIUS * 2.0
            tip_y = centre[1] + math.sin(angle) * USER_DOT_RADIUS * 2.0
            self._heading.points = [centre[0], centre[1], tip_x, tip_y]
        else:
            self._heading.points = []

        accuracy = self._gps_accuracy_meters
        if not on_route and accuracy:
            _, _, rect_width, _ = self.camera.plan_rect()
            scale_x, _ = FLOOR_PLAN_METERS_PER_AXIS.get(
                self.current_floor,
                (PROVISIONAL_FLOOR_WIDTH_METERS, PROVISIONAL_FLOOR_WIDTH_METERS),
            )
            radius = (
                accuracy / scale_x * rect_width
            )
            self._accuracy.pos = (centre[0] - radius, centre[1] - radius)
            self._accuracy.size = (radius * 2, radius * 2)
        else:
            self._accuracy.size = (0, 0)

    def _draw_destination(self):
        node = NODES.get(self.destination_node)
        if (
            not self.floorplan_source
            or node is None
            or node.floor != self.current_floor
        ):
            self._pin_shadow.size = (0, 0)
            self._pin_body.size = (0, 0)
            self._pin_inner.size = (0, 0)
            return

        centre = self._project_to_local(
            _svg_to_plan(node.position, node.floor)
        )
        size = DESTINATION_RADIUS * 2
        self._pin_shadow.pos = (centre[0] - size / 2, centre[1] - size * 0.8)
        self._pin_shadow.size = (size, size * 0.4)
        self._pin_body.pos = (centre[0] - size / 2, centre[1] - size / 2)
        self._pin_body.size = (size, size)
        inner = size * 0.40
        self._pin_inner.pos = (centre[0] - inner / 2, centre[1] - inner / 2)
        self._pin_inner.size = (inner, inner)

    def _project_to_local(self, point):
        """Project a plan point into coordinates local to this map widget."""
        screen_x, screen_y = self.camera.project(point)
        return screen_x - self.x, screen_y - self.y

    def _update_scale_bar(self):
        if not self.floorplan_source:
            self.scale_label = ""
            self.scale_bar_width = 0.0
            return

        scale_x, _ = FLOOR_PLAN_METERS_PER_AXIS.get(
            self.current_floor,
            (PROVISIONAL_FLOOR_WIDTH_METERS, PROVISIONAL_FLOOR_WIDTH_METERS),
        )
        meters_per_pixel = self.camera.meters_per_pixel(scale_x)
        if meters_per_pixel <= 0:
            self.scale_label = ""
            self.scale_bar_width = 0.0
            return
        nice = _nice_distance(SCALE_BAR_MAX_WIDTH * meters_per_pixel)
        self.scale_label = f"{nice:.0f} m"
        self.scale_bar_width = nice / meters_per_pixel


# ----------------------------------------------------------------------
# Small helpers kept outside the widget: they are pure functions of the
# points handed to them, so they are easy to reason about in isolation.
# ----------------------------------------------------------------------
def _chevron_segments(points):
    """One chevron polyline per real bend, pointing along the outgoing leg."""
    chevrons = []
    if len(points) < 3:
        return chevrons

    for index in range(1, len(points) - 1):
        previous = points[index - 1]
        current = points[index]
        following = points[index + 1]
        incoming = math.atan2(
            current[1] - previous[1], current[0] - previous[0]
        )
        outgoing = math.atan2(
            following[1] - current[1], following[0] - current[0]
        )
        turn = (outgoing - incoming + math.pi) % (2 * math.pi) - math.pi
        if abs(turn) < STRAIGHT_TURN_LIMIT:
            continue
        chevrons.append(_chevron_points(current, outgoing))
    return chevrons


def _chevron_points(origin, angle):
    """A ``V`` shaped arrowhead at ``origin`` pointing along ``angle``."""
    tip_x = origin[0] + math.cos(angle) * CHEVRON_LENGTH
    tip_y = origin[1] + math.sin(angle) * CHEVRON_LENGTH
    left_x = origin[0] + math.cos(angle + CHEVRON_SPREAD_ANGLE) * CHEVRON_SPREAD * 2
    left_y = origin[1] + math.sin(angle + CHEVRON_SPREAD_ANGLE) * CHEVRON_SPREAD * 2
    right_x = origin[0] + math.cos(angle - CHEVRON_SPREAD_ANGLE) * CHEVRON_SPREAD * 2
    right_y = origin[1] + math.sin(angle - CHEVRON_SPREAD_ANGLE) * CHEVRON_SPREAD * 2
    return [left_x, left_y, tip_x, tip_y, right_x, right_y]


def _inside_plan(point):
    """True when a plan point actually falls on the plan image."""
    return 0.0 <= point[0] <= 1.0 and 0.0 <= point[1] <= 1.0


def _nice_distance(value):
    """Round a distance up to a readable 1/2/5 x power-of-ten value."""
    if value <= 0:
        return 1.0
    exponent = 10 ** math.floor(math.log10(value))
    for factor in (1, 2, 5, 10):
        candidate = exponent * factor
        if candidate >= value:
            return float(candidate)
    return float(exponent * 10)
