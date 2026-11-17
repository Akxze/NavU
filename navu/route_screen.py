"""The indoor navigation screen.

Laid out the way a phone mapping app is: a maneuver banner across the top, the
interactive plan in the middle with floating controls, and a draggable sheet at
the bottom that holds the destination summary and the full step list.
"""

import math
import os
from datetime import datetime, timedelta

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDButtonText
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel

from . import theme
from .config import (
    BASE_DIR,
    FLOOR_CONFIG,
    discover_floorplan_image,
    resolve_room_photos,
)
from .directions import (
    build_steps,
    floor_name,
    route_length_meters,
)
from .location import PhoneLocationTracker
from .navigation import NavigationController
from .routing import (
    DEFAULT_TRAVEL_PREFERENCE,
    NODES,
    FLOORS,
    ROOMS_BY_ID,
    InvalidStartLocation,
    resolve_start,
    shortest_path,
)
from .step_row import RouteStepRow
from .widgets import NavButton

SHEET_STATES = ("peek", "full")
SHEET_COLLAPSED_HEIGHT = dp(36)
SHEET_MIN_HEIGHT = dp(300)
SHEET_MAX_RATIO = 0.75
SHEET_SETTLE_DURATION = 0.38
GPS_ADVANCE_LIMIT_METERS = 25.0


class NavigationSheetCard(MDCard):
    """Draggable navigation card that keeps embedded buttons interactive."""

    drag_callback = ObjectProperty(None, allownone=True)
    drag_update_callback = ObjectProperty(None, allownone=True)

    def on_touch_down(self, touch):
        if Widget.on_touch_down(self, touch):
            return True
        if not self.collide_point(*touch.pos):
            return False
        self._sheet_drag_start_y = touch.y
        self._sheet_drag_last_y = touch.y
        touch.grab(self)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return Widget.on_touch_move(self, touch)
        delta_y = touch.y - self._sheet_drag_last_y
        self._sheet_drag_last_y = touch.y
        if self.drag_update_callback:
            self.drag_update_callback(delta_y)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return Widget.on_touch_up(self, touch)
        delta_y = touch.y - self._sheet_drag_start_y
        touch.ungrab(self)
        if abs(delta_y) >= dp(24) and self.drag_callback:
            self.drag_callback(delta_y > 0)
        return True


class RouteScreen(MDScreen):
    """Destination summary, live guidance and the map, in one screen."""

    logo_source = StringProperty(
        os.path.join(BASE_DIR, "assets", "NAVU_LOGO.png")
    )

    # Destination
    room_code = StringProperty("")
    room_name = StringProperty("")
    room_floor_display = StringProperty("")
    room_directions = StringProperty("")
    room_photo_source = StringProperty("")

    # Map
    current_floor = StringProperty("LG")
    floor_label = StringProperty("")
    map_has_plan = BooleanProperty(True)
    follow_active = BooleanProperty(False)

    # Guidance banner
    maneuver_icon = StringProperty(theme.ICON["start"])
    maneuver_title = StringProperty("What floor are you currently on?")
    maneuver_instruction = StringProperty(
        "Choose your floor, then tap your location on the plan."
    )
    maneuver_distance = StringProperty("--")
    up_next_text = StringProperty("")

    # Summary strip
    remaining_distance = StringProperty("--")
    remaining_time = StringProperty("--")
    arrival_clock = StringProperty("--:--")
    live_clock = StringProperty("")

    # State
    has_route = BooleanProperty(False)
    navigating = BooleanProperty(False)
    arrived = BooleanProperty(False)
    tracking_walk = BooleanProperty(False)

    start_node = StringProperty("")
    gps_status = StringProperty(
        "Choose your current floor to begin."
    )
    next_floor_visible = BooleanProperty(False)
    next_floor_target = StringProperty("")
    next_floor_label = StringProperty("")
    next_floor_instruction = StringProperty("")
    next_floor_icon = StringProperty(theme.ICON["elevator"])

    sheet_height = NumericProperty(0)
    sheet_state = StringProperty("peek")
    travel_preference = StringProperty(DEFAULT_TRAVEL_PREFERENCE)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.navigation = NavigationController(self._refresh_navigation_ui)
        self.latest_gps_coordinates = None
        self.latest_gps_accuracy = None
        self.route = []
        self.location_tracker = None
        self._destination_node_id = ""
        self._start_floor_selected = False
        self._map_pick_dialog = None
        self._manual_floor_override = False
        self._floor_selector_layer_state = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def on_kv_post(self, _base_widget):
        self.ids.route_map.origin_callback = self.set_origin_from_tap
        self.ids.route_map.tap_callback = self.handle_map_tap
        self.bind(sheet_height=self._update_map_pan_bounds)
        floor_panel = self.ids.floor_selector_panel
        map_container = floor_panel.parent
        overlay = map_container.parent if map_container is not None else None
        if overlay is not None and floor_panel.parent is not overlay:
            floor_panel.parent.remove_widget(floor_panel)
            overlay.add_widget(floor_panel)
        self.ids.route_map.tap_blocker = floor_panel
        self.location_tracker = PhoneLocationTracker(
            self._on_gps_location,
            self._set_gps_status,
        )
        self.ids.route_map.set_floor(self.current_floor)
        self._apply_sheet_state("peek", animate=False)
        Clock.schedule_once(self._tick_clock, 0)

    def on_enter(self, *args):
        Clock.schedule_interval(self._tick_clock, 1)
        Clock.schedule_once(self._layout_route_content, 0.5)
        if self.location_tracker is not None:
            self.location_tracker.start()

    def _layout_route_content(self, _dt):
        route_map = self.ids.route_map
        map_container = route_map.parent
        content_layout = map_container.parent if map_container is not None else None
        self.do_layout()
        if content_layout is not None:
            content_layout.do_layout()
        if map_container is not None:
            map_container.do_layout()
        route_map._sync_camera()

    def on_leave(self, *args):
        Clock.unschedule(self._tick_clock)
        if self.location_tracker is not None:
            self.location_tracker.stop()

    def stop_tracking(self):
        """Called when the app closes or the screen is left."""
        self.navigation.stop_walking()
        if self.location_tracker is not None:
            self.location_tracker.stop()

    def on_size(self, *_args):
        self._apply_sheet_state(self.sheet_state, animate=False)

    # ------------------------------------------------------------------
    # Destination setup
    # ------------------------------------------------------------------
    def configure_destination(
        self,
        room_code,
        room_name,
        room_info=None,
        start_room_id="",
    ):
        """Point the screen at a room and rebuild the route."""
        destination_room = ROOMS_BY_ID.get(room_code)
        if destination_room is None:
            raise ValueError(f"Destination is not in the route graph: {room_code}")
        start_room = ROOMS_BY_ID.get(start_room_id) if start_room_id else None
        if start_room_id and start_room is None:
            raise ValueError(
                f"Starting room is not in the route graph: {start_room_id}"
            )

        self.room_code = room_code
        self.room_name = room_name or destination_room.name
        self._destination_node_id = destination_room.door_nodes[0]
        room_info = room_info or {}
        photos = resolve_room_photos(
            room_info.get("legacy_code") or room_code,
            floor=destination_room.floor,
            room_no=destination_room.room_no,
            room_name=destination_room.name,
        )
        self.room_photo_source = photos[0] if photos else ""
        destination_floor = destination_room.floor
        self.room_floor_display = FLOOR_CONFIG.get(
            destination_floor, {"display": "Campus"}
        )["display"]
        self.room_directions = room_info.get(
            "directions", destination_room.room_type.replace("_", " ").title()
        )
        self.navigating = False
        self.navigation.stop_walking()
        self._clear_next_floor_action()
        self._start_node = start_room.door_nodes[0] if start_room else ""
        self.start_node = self._start_node
        self._start_floor_selected = bool(start_room)
        self.route = []
        route_map = self.ids.route_map
        route_map.origin_position = []
        route_map.origin_floor = ""
        route_map.follow_user = False
        if start_room is not None:
            self.current_floor = start_room.floor
            self.gps_status = (
                f"Starting from {start_room.name} on "
                f"{floor_name(start_room.floor)}."
            )
            self.maneuver_title = "Route ready"
            self.maneuver_instruction = (
                f"From {start_room.name} to {self.room_name}"
            )
        else:
            self.gps_status = "Choose your current floor to begin."
            self.maneuver_title = "What floor are you currently on?"
            self.maneuver_instruction = (
                "Choose your floor, then tap your location on the plan."
            )
        self._select_floor(self.current_floor, reset_view=True)
        if start_room is not None:
            start_node = NODES[self._start_node]
            route_map.origin_position = list(start_node.position)
            route_map.origin_floor = start_node.floor
        self._apply_sheet_state("peek", animate=False)
        self._build_route()
        Clock.schedule_once(self._layout_route_content, 0.5)

    def _build_route(self, fit_map=True):
        """Recompute the route from the current start to the destination."""
        destination_id = self._destination_node_id
        destination = NODES.get(destination_id)
        self.start_node = getattr(self, "_start_node", "")
        self.route = []

        if destination is None:
            self._show_unroutable()
            return

        if not discover_floorplan_image(destination.floor):
            self._show_unroutable()
            return

        if not self.start_node:
            self.navigation.clear()
            self.has_route = False
            self.arrived = False
            self.maneuver_icon = theme.ICON["start"]
            self.maneuver_title = "Set your starting point"
            self.maneuver_instruction = (
                f"To {self.room_name} on {self.room_directions_floor()}"
            )
            self.maneuver_distance = "--"
            self.up_next_text = ""
            self.remaining_distance = "--"
            self.remaining_time = "--"
            self.arrival_clock = "--:--"
            self.ids.route_map.set_route(
                [], "", destination_id, self._origin_position(), self._origin_floor()
            )
            self._populate_steps([])
            return

        self.route = shortest_path(
            self.start_node, destination_id, self.travel_preference
        )
        if not self.route:
            self._show_unroutable()
            return

        total = route_length_meters(
            self.route, self._origin_position(), self._origin_floor()
        )
        steps = build_steps(
            self.route,
            self._origin_position(),
            self._origin_floor(),
            destination_label=self.room_name,
        )
        self.has_route = True
        self.arrived = False
        if self.current_floor != self.route[0].floor:
            self.current_floor = self.route[0].floor
            self.floor_label = floor_name(self.current_floor)
            self.map_has_plan = bool(discover_floorplan_image(self.current_floor))
            self.ids.route_map.set_floor(self.current_floor)
        self.ids.route_map.set_route(
            self.route,
            self.start_node,
            destination_id,
            self._origin_position(),
            self._origin_floor(),
        )
        self.navigation.load(self.route, steps, total, self.room_name)
        if fit_map:
            self.ids.route_map.frame_route()
        self._populate_steps(steps)

    def _show_unroutable(self):
        self.route = []
        self.has_route = False
        self.navigation.clear()
        self.maneuver_icon = theme.ICON["floor"]
        self.maneuver_title = "Floor plan unavailable"
        self.maneuver_instruction = (
            f"No mapped route to {self.room_name} ({self.room_floor_display})"
        )
        self.maneuver_distance = "--"
        self.up_next_text = ""
        self.remaining_distance = "--"
        self.remaining_time = "--"
        self.arrival_clock = "--:--"
        self.ids.route_map.set_route(
            [], "", self._destination_node_id
        )
        self._populate_steps([])

    def room_directions_floor(self):
        return self.room_floor_display or "the destination floor"

    def _origin_position(self):
        position = self.ids.route_map.origin_position
        return tuple(position) if len(position) == 2 else None

    def _origin_floor(self):
        return self.ids.route_map.origin_floor

    # ------------------------------------------------------------------
    # Start point
    # ------------------------------------------------------------------
    def set_origin_from_tap(self, position):
        """Snap the manually chosen start onto the nearest mapped hallway."""
        if not self._start_floor_selected:
            self.gps_status = "Choose the floor you are currently on first."
            return False
        try:
            start = resolve_start(self.current_floor, position)
        except InvalidStartLocation:
            self.gps_status = (
                f"No mapped room or point near that location on "
                f"{floor_name(self.current_floor)}. Tap a room or route point."
            )
            return False

        self.navigation.stop_walking()
        self.navigating = False
        node = start.node
        self._start_node = node.node_id
        self.start_node = node.node_id
        route_map = self.ids.route_map
        snapped_position = node.position
        route_map.origin_position = list(snapped_position)
        route_map.origin_floor = self.current_floor
        if self.latest_gps_coordinates is not None:
            latitude, longitude = self.latest_gps_coordinates
            route_map.set_gps_anchor(
                snapped_position, latitude, longitude, self.latest_gps_accuracy
            )
        self.gps_status = (
            f"Start set on {floor_name(self.current_floor)}. "
            "Tap the map to move it."
        )
        self._build_route(fit_map=False)
        return True

    def handle_map_tap(self, position):
        """Offer the resolved room or corridor point as either route endpoint."""
        try:
            selection = resolve_start(self.current_floor, position)
        except InvalidStartLocation as error:
            self.gps_status = (
                f"{error}. Tap a mapped room or route point on "
                f"{floor_name(self.current_floor)}."
            )
            return False

        room = ROOMS_BY_ID.get(selection.room_id)
        place_name = (
            room.name
            if room is not None
            else selection.node.label or "Mapped point"
        )
        if self._map_pick_dialog is not None:
            self._map_pick_dialog.dismiss()

        start_button = NavButton(
            MDButtonText(
                text="Set as Start",
                bold=True,
                theme_text_color="Custom",
                text_color=theme.NAVY_900,
            ),
            style="filled",
            size_hint=(1, None),
            height=dp(46),
            theme_bg_color="Custom",
            md_bg_color=theme.GOLD_500,
            radius=[23, 23, 23, 23],
        )
        destination_button = NavButton(
            MDButtonText(
                text="Set as Destination",
                bold=True,
                theme_text_color="Custom",
                text_color=theme.GOLD_300,
            ),
            style="outlined",
            size_hint=(1, None),
            height=dp(46),
            theme_bg_color="Custom",
            md_bg_color=theme.NAVY_900,
            line_color=theme.GOLD_500,
            radius=[23, 23, 23, 23],
        )
        close_button = NavButton(
            MDButtonText(
                text="Cancel",
                theme_text_color="Custom",
                text_color=theme.WHITE,
            ),
            style="text",
            size_hint=(1, None),
            height=dp(42),
            theme_bg_color="Custom",
            md_bg_color=theme.alpha(theme.WHITE, 0.08),
            radius=[21, 21, 21, 21],
        )
        content = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, 1),
            padding=[dp(20), dp(18), dp(20), dp(16)],
            spacing=dp(10),
        )
        content.add_widget(
            MDLabel(
                text=place_name,
                size_hint_y=None,
                height=dp(34),
                font_size="20sp",
                bold=True,
                halign="center",
                valign="middle",
                theme_text_color="Custom",
                text_color=theme.GOLD_300,
            )
        )
        content.add_widget(
            MDLabel(
                text=f"{floor_name(selection.floor)} · Choose an action",
                size_hint_y=None,
                height=dp(24),
                font_size="14sp",
                halign="center",
                valign="middle",
                theme_text_color="Custom",
                text_color=theme.WHITE,
            )
        )
        for button in (start_button, destination_button, close_button):
            content.add_widget(button)

        card = MDCard(
            size_hint=(1, 1),
            padding=0,
            radius=[dp(22), dp(22), dp(22), dp(22)],
            elevation=0,
            style="filled",
            theme_bg_color="Custom",
            md_bg_color=theme.alpha(theme.NAVY_900, 0.97),
        )
        card_border = MDCard(
            size_hint=(0.88, None),
            height=dp(284),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            padding=dp(1.5),
            radius=[dp(24), dp(24), dp(24), dp(24)],
            elevation=12,
            style="filled",
            theme_bg_color="Custom",
            md_bg_color=theme.GOLD_500,
        )
        card.add_widget(content)
        card_border.add_widget(card)
        dialog = ModalView(
            size_hint=(1, 1),
            auto_dismiss=True,
            background="",
            background_color=(0, 0, 0, 0),
            overlay_color=theme.alpha(theme.NAVY_900, 0.52),
        )
        dialog.add_widget(card_border)
        self._map_pick_dialog = dialog
        close_button.bind(on_release=lambda *_args: dialog.dismiss())
        start_button.bind(
            on_release=lambda *_args: self._set_map_start(selection, dialog)
        )
        destination_button.bind(
            on_release=lambda *_args: self._set_map_destination(
                selection, room, dialog
            )
        )
        dialog.open()
        return True

    def _set_map_start(self, selection, dialog):
        dialog.dismiss()
        self._map_pick_dialog = None
        self._start_floor_selected = True
        if selection.floor != self.current_floor:
            self._select_floor(selection.floor, reset_view=True, manual=True)
        self.set_origin_from_tap(selection.tapped_position)

    def _set_map_destination(self, selection, room, dialog):
        dialog.dismiss()
        self._map_pick_dialog = None
        self.navigation.stop_walking()
        self.navigating = False
        self._manual_floor_override = False
        destination_node = selection.node
        self.room_code = room.room_id if room is not None else destination_node.node_id
        self.room_name = (
            room.name
            if room is not None
            else destination_node.label or "Mapped point"
        )
        self._destination_node_id = destination_node.node_id
        self.room_floor_display = FLOOR_CONFIG.get(
            destination_node.floor, {"display": floor_name(destination_node.floor)}
        )["display"]
        self.room_directions = (
            room.room_type.replace("_", " ").title()
            if room is not None
            else f"Mapped point on {floor_name(destination_node.floor)}"
        )
        photos = (
            resolve_room_photos(
                room.room_id,
                floor=room.floor,
                room_no=room.room_no,
                room_name=room.name,
            )
            if room is not None
            else []
        )
        self.room_photo_source = photos[0] if photos else ""
        if destination_node.floor != self.current_floor:
            self._select_floor(
                destination_node.floor, reset_view=True, manual=True
            )
        else:
            self.ids.route_map.destination_node = destination_node.node_id
        self._start_floor_selected = self._start_floor_selected or bool(
            self.start_node
        )
        self._build_route(fit_map=False)
        self.gps_status = f"Destination set to {self.room_name}."

    # ------------------------------------------------------------------
    # Guidance read-out
    # ------------------------------------------------------------------
    def _refresh_navigation_ui(self):
        """Push the controller's state into the banner and summary strip."""
        controller = self.navigation
        if not controller.is_loaded:
            self.tracking_walk = False
            self._clear_next_floor_action()
            return

        self.tracking_walk = controller.walking
        self.arrived = controller.arrived
        self.remaining_distance = controller.distance_label
        self.remaining_time = controller.remaining_label

        step = controller.active_step
        if self.arrived:
            self.maneuver_icon = theme.ICON["arrive"]
            self.maneuver_title = "You have arrived"
            self.maneuver_instruction = self.room_name
            self.maneuver_distance = "0 m"
            self.up_next_text = ""
        elif step is not None:
            self.maneuver_icon = step.icon
            self.maneuver_title = step.title
            self.maneuver_instruction = step.instruction
            self.maneuver_distance = controller.maneuver_distance_label
            following = controller.next_step
            self.up_next_text = (
                f"Then {following.title.lower()} - "
                f"{following.instruction}"
                if following
                else ""
            )

        self._highlight_active_step(controller.active_step_index)
        self._update_arrival_clock()
        route_map = self.ids.route_map
        route_map.set_progress(
            controller.session.travelled_meters,
            controller.session.total_meters,
        )
        self._update_next_floor_action()
        walker_floor = route_map.walker_floor
        if (
            self.navigating
            and walker_floor
            and walker_floor == self.current_floor
        ):
            self._manual_floor_override = False
        if (
            self.navigating
            and self.arrived
            and not self._manual_floor_override
        ):
            self._follow_route_floor()
        elif (
            self.navigating
            and not self._manual_floor_override
            and walker_floor
            and walker_floor != self.current_floor
        ):
            self._select_floor(walker_floor)
            if route_map.follow_user:
                self.gps_status = (
                    f"Following the route on {floor_name(walker_floor)}."
                )
            else:
                self.gps_status = (
                    f"Route continues on {floor_name(walker_floor)}."
                )
        self.follow_active = route_map.follow_user

    def _update_next_floor_action(self):
        session = self.navigation.session
        travelled = session.travelled_meters
        next_transition = next(
            (
                step
                for step in session.steps
                if step.is_vertical
                and step.cumulative_meters > travelled + 0.01
            ),
            None,
        )
        if next_transition is None:
            self._clear_next_floor_action()
            return

        self.next_floor_visible = True
        self.next_floor_target = next_transition.floor
        self.next_floor_label = (
            f"Jump to Next Floor ({floor_name(next_transition.floor)})"
        )
        self.next_floor_instruction = next_transition.instruction
        self.next_floor_icon = next_transition.icon

    def _clear_next_floor_action(self):
        self.next_floor_visible = False
        self.next_floor_target = ""
        self.next_floor_label = ""
        self.next_floor_instruction = ""
        self.next_floor_icon = theme.ICON["elevator"]

    def _highlight_active_step(self, index):
        grid = self.ids.get("step_list")
        if grid is None:
            return
        for child in grid.children:
            row = getattr(child, "step", None)
            if row is None:
                continue
            is_active = row.index == index
            if is_active == getattr(child, "_active", False):
                continue
            grid.remove_widget(child)
            grid.add_widget(
                RouteStepRow(
                    row,
                    active=is_active,
                    is_last=row.kind == "arrive",
                )
            )
        grid.do_layout()

    def _population_index(self, index):
        """Reorder helper: Kivy's grid children run bottom-up."""
        return index

    def _populate_steps(self, steps):
        grid = self.ids.get("step_list")
        if grid is None:
            return
        grid.clear_widgets()
        if not steps:
            return
        last = len(steps) - 1
        for step in reversed(steps):
            grid.add_widget(
                RouteStepRow(
                    step,
                    active=step.index == 0,
                    is_last=step.index == last,
                )
            )

    # ------------------------------------------------------------------
    # Navigation actions
    # ------------------------------------------------------------------
    def start_navigation(self):
        if not self.has_route:
            return
        self.navigating = True
        self._manual_floor_override = False
        self._apply_sheet_state("peek", animate=True)
        self.ids.route_map.focus_user()
        self.follow_active = True

    def stop_navigation(self):
        self.navigation.stop_walking()
        self.navigating = False
        self._manual_floor_override = False

    def reset_for_exit(self):
        """Discard active navigation state and restore the default map view."""
        self.navigation.stop_walking()
        self.navigating = False
        self.arrived = False
        self.tracking_walk = False
        self.has_route = False
        self.follow_active = False
        self._manual_floor_override = False
        self._start_floor_selected = False
        self._start_node = ""
        self.start_node = ""
        self._destination_node_id = ""
        self.route = []
        self.room_code = ""
        self.room_name = ""
        self.room_floor_display = ""
        self.room_directions = ""
        self.room_photo_source = ""
        self.gps_status = "Choose your current floor to begin."
        self.maneuver_icon = theme.ICON["start"]
        self.maneuver_title = "What floor are you currently on?"
        self.maneuver_instruction = (
            "Choose your floor, then tap your location on the plan."
        )
        self.maneuver_distance = "--"
        self.up_next_text = ""
        self.remaining_distance = "--"
        self.remaining_time = "--"
        self.arrival_clock = "--:--"
        self.navigation.clear()
        self._clear_next_floor_action()
        self._populate_steps([])

        route_map = self.ids.route_map
        route_map.set_route([], "", "")
        route_map.clear_gps_anchor()
        self.current_floor = "LG"
        self._select_floor("LG", reset_view=True)
        self._apply_sheet_state("peek", animate=False)

    def go_back(self):
        from kivymd.app import MDApp

        app = MDApp.get_running_app()
        if app is None:
            raise RuntimeError("Cannot leave the route without a running NavU app.")
        app.return_from_route()

    def toggle_walk_simulation(self):
        if not self.has_route:
            return
        if self.navigation.walking:
            self.navigation.stop_walking()
            self.navigating = False
            return
        self.navigating = True
        self._manual_floor_override = False
        self.ids.route_map.focus_user()
        self.follow_active = True
        self.navigation.start_walking()

    def advance_step(self):
        """The "Next step" button: jump to the following maneuver."""
        if not self.has_route:
            return
        self.navigating = True
        self.navigation.advance_to_next_maneuver()

    def restart_route(self):
        if not self.has_route:
            return
        self.navigation.reset_progress()
        self.ids.route_map.follow_user = False
        self.ids.route_map.frame_route()
        self.follow_active = False
        self._manual_floor_override = False

    # ------------------------------------------------------------------
    # Map controls
    # ------------------------------------------------------------------
    def select_floor(self, floor):
        self._select_floor(floor, reset_view=True, manual=True)
        if floor in FLOORS:
            route_map = self.ids.route_map
            self._manual_floor_override = bool(
                self.navigating and route_map.walker_floor != floor
            )
            if not self.start_node:
                self._start_floor_selected = True
                self.maneuver_title = "Set your starting point"
                self.maneuver_instruction = (
                    f"Tap the {floor_name(floor)} plan where you are, near a hallway."
                )
                self.gps_status = (
                    f"Viewing {floor_name(floor)}. Tap a room or route point to start."
                )
            else:
                self.gps_status = (
                    f"Viewing {floor_name(floor)}. Tap the map to move your start."
                )

    def _select_floor(self, floor, reset_view=False, manual=False):
        if floor not in FLOORS:
            return
        self.current_floor = floor
        self.floor_label = floor_name(floor)
        self.map_has_plan = bool(discover_floorplan_image(floor))
        route_map = self.ids.route_map
        keep_follow = route_map.follow_user and not reset_view and not manual
        if manual:
            route_map.release_follow()
        route_map.set_floor(floor, keep_follow=keep_follow)
        if reset_view and self.route and not manual:
            route_map.frame_route()
        elif reset_view:
            route_map.reset_view()
        elif keep_follow:
            route_map.focus_user()
        self.follow_active = route_map.follow_user

    def recenter_map(self):
        route_map = self.ids.route_map
        self._manual_floor_override = False
        walker_floor = route_map.walker_floor
        if walker_floor and walker_floor != self.current_floor:
            self._select_floor(walker_floor)
        route_map.focus_user()
        self.follow_active = route_map.follow_user

    def jump_to_next_floor(self):
        if not self.has_route or not self.next_floor_visible:
            return
        target_floor = self.next_floor_target
        walker_floor = self.ids.route_map.walker_floor
        self._select_floor(target_floor, reset_view=True)
        self._manual_floor_override = bool(
            self.navigating and walker_floor != target_floor
        )
        self.gps_status = (
            f"Showing route continuation on {floor_name(target_floor)}."
        )

    def zoom_in(self):
        self.ids.route_map.zoom_in()

    def zoom_out(self):
        self.ids.route_map.zoom_out()

    def reset_map_view(self):
        self.ids.route_map.reset_view()
        self.follow_active = False

    def set_travel_preference(self, preference):
        if preference not in ("any", "stairs", "elevator"):
            return
        self.travel_preference = preference
        self._build_route(fit_map=False)

    # ------------------------------------------------------------------
    # Sheet
    # ------------------------------------------------------------------
    def set_sheet_state(self, state):
        self._apply_sheet_state(state, animate=True)

    def _sheet_height_for(self, state):
        if state == "full":
            available_height = self.height or Window.height
            if Window.height > 0:
                available_height = min(available_height, Window.height)
            maximum_height = available_height * SHEET_MAX_RATIO
            ids = getattr(self, "ids", None)
            content = (
                ids.get("navigation_sheet_content")
                if ids is not None and hasattr(ids, "get")
                else None
            )
            if content is not None:
                content.do_layout()
                natural_height = content.minimum_height + dp(18)
            else:
                natural_height = SHEET_MIN_HEIGHT
            return min(maximum_height, max(SHEET_MIN_HEIGHT, natural_height))
        return SHEET_COLLAPSED_HEIGHT

    @staticmethod
    def _critical_damped(progress):
        """Critically damped easing for a spring-like, non-overshooting settle."""
        progress = min(1.0, max(0.0, progress))
        stiffness = 7.0
        end = 1.0 - (1.0 + stiffness) * math.exp(-stiffness)
        value = 1.0 - (1.0 + stiffness * progress) * math.exp(
            -stiffness * progress
        )
        return value / end if end else progress

    def _update_map_pan_bounds(self, *_args):
        route_map = self.ids.get("route_map")
        if route_map is not None:
            route_map.set_extra_pan_down(
                max(0.0, self.sheet_height - SHEET_COLLAPSED_HEIGHT)
            )

    def _sync_floor_selector_layer(self):
        """Keep floor controls touchable, but behind the expanded sheet."""
        if self._floor_selector_layer_state == self.sheet_state:
            return
        ids = getattr(self, "ids", None)
        floor_panel = ids.get("floor_selector_panel") if ids is not None else None
        if floor_panel is None:
            return
        parent = floor_panel.parent
        if parent is None:
            return
        parent.remove_widget(floor_panel)
        index = len(parent.children) if self.sheet_state == "full" else 0
        parent.add_widget(floor_panel, index=index)
        self._floor_selector_layer_state = self.sheet_state

    def _apply_sheet_state(self, state, animate=True):
        if state not in SHEET_STATES:
            state = "peek"
        self.sheet_state = state
        self._sync_floor_selector_layer()
        target = self._sheet_height_for(state)
        Animation.cancel_all(self, "sheet_height")
        if not animate:
            self.sheet_height = target
            return
        Animation(
            sheet_height=target,
            duration=SHEET_SETTLE_DURATION,
            t=self._critical_damped,
        ).start(self)

    def drag_sheet(self, dragged_up):
        """Handle a drag on the sheet grabber."""
        index = SHEET_STATES.index(self.sheet_state)
        if dragged_up:
            index = min(len(SHEET_STATES) - 1, index + 1)
        else:
            index = max(0, index - 1)
        self._apply_sheet_state(SHEET_STATES[index], animate=True)

    def update_destination_sheet_drag(self, delta_y):
        """Track the grabber while it is dragged, then settle on release."""
        Animation.cancel_all(self, "sheet_height")
        collapsed = self._sheet_height_for("peek")
        expanded = self._sheet_height_for("full")
        self.sheet_height = min(
            expanded, max(collapsed, self.sheet_height + delta_y)
        )
        self.sheet_state = (
            "full"
            if self.sheet_height >= (collapsed + expanded) / 2
            else "peek"
        )
        self._sync_floor_selector_layer()

    # ------------------------------------------------------------------
    # Jump to a step
    # ------------------------------------------------------------------
    def jump_to_step(self, step):
        if not self.has_route:
            return
        self.navigating = True
        self.navigation.jump_to_step(step.index)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def open_search(self):
        self.navigation.stop_walking()
        self.navigating = False
        from kivymd.app import MDApp

        app = MDApp.get_running_app()
        if app is not None:
            app.switch_screen("room_search")

    # ------------------------------------------------------------------
    # Floor following
    # ------------------------------------------------------------------
    def _follow_route_floor(self):
        """On arrival, show the destination's own floor."""
        destination = NODES.get(self._destination_node_id)
        if destination is not None and destination.floor != self.current_floor:
            self._select_floor(destination.floor)
            self.gps_status = (
                f"Arrived on {floor_name(destination.floor)}."
            )

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------
    def _tick_clock(self, *_args):
        now = datetime.now()
        self.live_clock = now.strftime("%I:%M:%S %p")
        self._update_arrival_clock(now)

    def _update_arrival_clock(self, now=None):
        if not self.navigation.is_loaded:
            self.arrival_clock = "--:--"
            return
        now = now or datetime.now()
        arrival = now + timedelta(
            seconds=self.navigation.session.remaining_seconds
        )
        self.arrival_clock = arrival.strftime("%I:%M %p")

    # ------------------------------------------------------------------
    # GPS (best effort; the tapped start is the reliable path)
    # ------------------------------------------------------------------
    def _set_gps_status(self, message):
        self.gps_status = message

    def _on_gps_location(self, location):
        try:
            latitude = float(location["lat"])
            longitude = float(location["lon"])
        except (KeyError, TypeError, ValueError):
            self.gps_status = "GPS returned an invalid location fix."
            return
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            self.gps_status = "GPS returned an invalid location fix."
            return

        accuracy = location.get("accuracy")
        try:
            accuracy_meters = float(accuracy) if accuracy is not None else None
        except (TypeError, ValueError):
            accuracy_meters = None
        if accuracy_meters is not None and accuracy_meters < 0:
            accuracy_meters = None

        self.latest_gps_coordinates = (latitude, longitude)
        self.latest_gps_accuracy = accuracy_meters
        self.ids.route_map.update_gps_position(
            latitude, longitude, accuracy_meters
        )
        self.gps_status = (
            "GPS is approximate indoors. Tap your position on the plan for "
            "an accurate starting point."
        )

    def step_towards_destination(self):
        """Advance the route as if the walker took one GPS-sized step."""
        if not self.has_route:
            return
        self.navigating = True
        self.navigation.push_progress(GPS_ADVANCE_LIMIT_METERS)

    # ------------------------------------------------------------------
    # Legacy-compatible helpers kept for the KV layer
    # ------------------------------------------------------------------
    def select_floor_by_key(self, *_args):
        return None

    def recenter_to_user(self):
        self.recenter_map()

    def advance_navigation_step(self):
        self.advance_step()

    def set_destination_sheet_expanded(self, expanded):
        self.set_sheet_state("full" if expanded else "peek")
