"""Screens other than navigation, plus the shared photo overlay.

``RouteScreen`` lives in :mod:`navu.route_screen`; this module keeps the rest so
neither file has to carry the whole app.
"""

import os
import re
from functools import partial

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import (
    Color,
    Ellipse,
    PopMatrix,
    PushMatrix,
    Rectangle,
    RoundedRectangle,
    Scale,
    StencilPop,
    StencilPush,
    StencilUnUse,
    StencilUse,
)
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty,
    DictProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image as KivyImage
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButtonIcon, MDButtonText
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogContentContainer,
    MDDialogHeadlineText,
    MDDialogSupportingText,
)
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from . import theme
from .config import (
    BASE_DIR,
    FLOOR_CONFIG,
    ROOM_DATABASE,
    resolve_room_photos,
    room_photo_code_for_route,
)
from .directions import format_distance, format_duration, walk_seconds
from .routing import (
    DEFAULT_TRAVEL_PREFERENCE,
    FLOORS,
    ROOMS_BY_ID,
    route_distance_meters,
    shortest_path,
)
from .widgets import NavButton

OVERLAY_SCRIM = theme.alpha(theme.NAVY_900, 1)
_CAMPUS_BANNER_CANDIDATES = {
    "fairview": ("assets", "gui_assests", "NU_FAIRVIEW_BANNER.png"),
    "manila": ("assets", "gui_assests", "NU_MANILA_BANNER.jpg"),
    "moa": ("assets", "gui_assests", "NU_moa.png"),
    "lipa": ("assets", "gui_assests", "NU_LIPA_BANNER.jpg"),
    "baliwag": ("assets", "gui_assests", "NU_BALIUAG_BANNER.png"),
    "laguna": ("assets", "gui_assests", "NU_LAGUNA_BANNER.jpg"),
}
_CAMPUS_PROFILE_CANDIDATES = {
    "fairview": ("assets", "campuses", "NU_Fairview.jpg"),
    "manila": ("assets", "campuses", "NU_Manila.jpg"),
    "moa": ("assets", "campuses", "NU_MOA.png"),
    "lipa": ("assets", "campuses", "NU_LIPA.png"),
    "baliwag": ("assets", "campuses", "NU_Baliwag.png"),
    "laguna": ("assets", "campuses", "NU_Laguna.png"),
}
CAMPUS_KEYS = tuple(_CAMPUS_BANNER_CANDIDATES)
CAMPUS_BANNER_PATHS = {
    campus: os.path.join(BASE_DIR, *path_parts)
    for campus, path_parts in _CAMPUS_BANNER_CANDIDATES.items()
}
CAMPUS_PROFILE_PATHS = {
    campus: os.path.join(BASE_DIR, *path_parts)
    for campus, path_parts in _CAMPUS_PROFILE_CANDIDATES.items()
}
CAMPUS_IMAGE_PATHS = {
    campus: {
        "banner": CAMPUS_BANNER_PATHS[campus],
        "profile": CAMPUS_PROFILE_PATHS[campus],
    }
    for campus in CAMPUS_KEYS
}
CAMPUS_LOGO_PATH = os.path.join(
    BASE_DIR, "assets", "gui_assests", "NAVU_LOGO.png"
)
_ROUTE_ROOM_ALIASES = {
    "APPARLG": "LG:lg_apparel",
    "CONMATLG": "LG:lg_construction_lab",
    "ELEVLG": "LG:lg_elevators",
    "ENTLG": "LG:lg_main_entrance",
    "FIRESTLG": "LG:lg_fire_exit",
    "RRLG": "LG:lg_restroom",
    "UTMLG": "LG:lg_testing_lab",
}


def _resolve_campus_asset(campus_key, asset_type):
    """Resolve a campus banner or profile photo from its configured asset path."""
    campus = campus_key.strip().casefold()
    configured_path = CAMPUS_IMAGE_PATHS.get(campus, {}).get(asset_type)
    if not configured_path or not os.path.exists(configured_path):
        return ""
    return configured_path


def _resolve_campus_image(campus_key):
    """Resolve the banner image used as a campus card background."""
    return _resolve_campus_asset(campus_key, "banner")


def _resolve_campus_profile(campus_key):
    """Resolve the campus profile photo shown over its banner."""
    return _resolve_campus_asset(campus_key, "profile")


def _search_destinations():
    """Expose only destinations present in the route graph."""
    destinations = []
    legacy_by_route_id = {
        route_id: (code, info)
        for code, info in ROOM_DATABASE.items()
        if (route_id := _ROUTE_ROOM_ALIASES.get(code))
    }
    for code, info in ROOM_DATABASE.items():
        if code.isdigit():
            for room in ROOMS_BY_ID.values():
                if (
                    room.room_no == code
                    and code in re.findall(r"\d+", room.name)
                    and code in re.findall(r"\d+", info["name"])
                    and (room.floor == "LG" and info["floor"] == "lower_ground"
                         or room.floor == info["floor"])
                ):
                    legacy_by_route_id.setdefault(room.room_id, (code, info))

    for floor in FLOORS:
        for room in ROOMS_BY_ID.values():
            if room.floor != floor:
                continue
            floor_label = FLOOR_CONFIG[floor]["display"]
            room_type = room.room_type.replace("_", " ").title()
            legacy = legacy_by_route_id.get(room.room_id)
            if legacy is None:
                legacy_code = room_photo_code_for_route(
                    room.floor,
                    room.room_no,
                    room.name,
                    room_id=room.room_id,
                )
                if legacy_code:
                    legacy = (legacy_code, ROOM_DATABASE[legacy_code])
            legacy_code, legacy_info = legacy if legacy else ("", {})
            if floor == "LG" and not resolve_room_photos(legacy_code):
                continue
            destinations.append(
                (
                    room.room_id,
                    {
                        "floor": floor,
                        "name": room.name,
                        "directions": (
                            legacy_info.get("directions")
                            or f"{floor_label} · {room_type or 'Mapped room'}"
                        ),
                        "keywords": (
                            f"{room.room_id} {room.room_no} {room.room_type} "
                            f"{floor_label} {legacy_code} "
                            f"{legacy_info.get('name', '')} "
                            f"{legacy_info.get('keywords', '')}"
                        ),
                        "room_no": room.room_no,
                        "legacy_code": legacy_code,
                    },
                )
            )
    return destinations


def _search_result_description(room_info):
    """Remove floor prefixes duplicated by the floor badge."""
    description = room_info.get("directions", "").strip()
    return re.sub(
        r"^(?:lower ground(?: floor| level)?|lg|"
        r"[1-5](?:st|nd|rd|th)?(?: floor|f))\s*[;·,–—-]?\s*",
        "",
        description,
        flags=re.IGNORECASE,
    ).strip()


class RoomSearchResultCard(MDCard):
    """Selectable destination card with a name, floor badge, and description."""

    room_code = StringProperty("")
    room_name = StringProperty("")
    floor_display = StringProperty("")
    room_description = StringProperty("")
    room_info = DictProperty({})
    search_screen = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(88))
        kwargs.setdefault("padding", [dp(10), dp(8)])
        kwargs.setdefault("theme_bg_color", "Custom")
        kwargs.setdefault("md_bg_color", theme.WHITE)
        kwargs.setdefault("line_color", theme.alpha(theme.GOLD_500, 0.48))
        kwargs.setdefault("line_width", dp(1))
        kwargs.setdefault("radius", [dp(16)] * 4)
        kwargs.setdefault("elevation", 1)
        super().__init__(**kwargs)

        self._name_label = MDLabel(
            text=self.room_name,
            halign="left",
            valign="middle",
            max_lines=1,
            bold=True,
            font_style="Body",
            role="medium",
            theme_text_color="Custom",
            text_color=theme.NAVY_900,
        )
        self._floor_label = MDLabel(
            text=self.floor_display,
            halign="center",
            valign="middle",
            bold=True,
            font_style="Label",
            role="small",
            theme_text_color="Custom",
            text_color=theme.NAVY_900,
        )
        self._description_label = MDLabel(
            text=self.room_description,
            halign="left",
            valign="top",
            max_lines=2,
            font_style="Body",
            role="small",
            theme_text_color="Custom",
            text_color=theme.INK_SOFT,
        )
        self.bind(
            room_name=lambda _instance, value: setattr(
                self._name_label, "text", value
            ),
            floor_display=lambda _instance, value: setattr(
                self._floor_label, "text", value
            ),
            room_description=lambda _instance, value: setattr(
                self._description_label, "text", value
            ),
            on_release=self._open_preview,
        )

        content = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(10),
        )
        self.add_widget(content)
        content.add_widget(
            MDCard(
                size_hint=(None, 1),
                width=dp(4),
                theme_bg_color="Custom",
                md_bg_color=theme.GOLD_500,
                radius=[dp(2)] * 4,
                elevation=0,
            )
        )
        details = MDBoxLayout(
            orientation="vertical",
            spacing=dp(2),
        )
        content.add_widget(details)
        heading = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(28),
            spacing=dp(8),
        )
        details.add_widget(heading)
        heading.add_widget(self._name_label)
        floor_badge = MDCard(
            size_hint=(None, None),
            size=(dp(44), dp(22)),
            pos_hint={"center_y": 0.5},
            theme_bg_color="Custom",
            md_bg_color=theme.GOLD_500,
            radius=[dp(11)] * 4,
            elevation=0,
        )
        floor_badge.add_widget(self._floor_label)
        heading.add_widget(floor_badge)
        details.add_widget(self._description_label)

    def _open_preview(self, *_args):
        if self.search_screen is not None and self.room_code:
            self.search_screen.show_room_preview(
                self.room_code, self.room_info
            )


class RecycledRoomSearchResultCard(
    RecycleDataViewBehavior, RoomSearchResultCard
):
    """A destination row whose widget is reused while scrolling search results."""


class RouteSheetHandle(Widget):
    """The draggable grabber at the top of the navigation sheet."""

    drag_callback = ObjectProperty(None, allownone=True)
    drag_update_callback = ObjectProperty(None, allownone=True)
    expanded = BooleanProperty(False)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._drag_start_y = touch.y
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            if self.drag_update_callback:
                self.drag_update_callback(touch.dy)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            delta_y = touch.y - self._drag_start_y
            touch.ungrab(self)
            if self.drag_callback:
                if abs(delta_y) >= dp(24):
                    self.drag_callback(delta_y > 0)
                else:
                    self.drag_callback(not self.expanded)
            return True
        return super().on_touch_up(touch)


class RoundedPhotoClip(FloatLayout):
    """Clip preview-image children to the rounded photo frame."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            StencilPush()
            self._clip_mask = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[dp(18)] * 4,
            )
            StencilUse()
        with self.canvas.after:
            StencilUnUse()
            Rectangle(pos=self.pos, size=self.size)
            StencilPop()
        self.bind(pos=self._sync_clip, size=self._sync_clip)

    def _sync_clip(self, *_args):
        self._clip_mask.pos = self.pos
        self._clip_mask.size = self.size


class RoomPreviewOverlay(FloatLayout):
    """Facility photo and graph-backed route preparation overlay."""

    room_name = StringProperty("")
    room_floor = StringProperty("")
    room_description = StringProperty("")
    photo_caption = StringProperty("")
    go_callback = ObjectProperty(None, allownone=True)
    origin_label = StringProperty("From: Current Location")
    origin_hint = StringProperty("Set your start on the map")
    route_distance = StringProperty("--")
    route_time = StringProperty("--")
    floor_changes = StringProperty("Set start")

    def __init__(
        self,
        photos,
        room_name,
        go_callback,
        search_callback,
        room_details="",
        photo_fit="cover",
        show_details=True,
        room_floor="",
        room_description="",
        destination_code="",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.photo_paths = list(photos)
        self.photo_index = 0
        self.room_name = room_name
        self.room_floor = room_floor
        self.room_description = room_description or room_details
        self.go_callback = go_callback
        self.search_callback = search_callback
        self.destination_code = destination_code
        self.selected_origin_room = ""
        self._origin_popup = None
        self.opacity = 0

        with self.canvas.before:
            self._background_color = Color(*theme.NAVY_900)
            self._background = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_background, size=self._update_background)

        self.title_label = MDLabel(
            text=self.room_name,
            font_style="Title",
            role="large",
            bold=True,
            halign="left",
            valign="middle",
            size_hint=(0.76, None),
            height=dp(42),
            theme_text_color="Custom",
            text_color=theme.WHITE,
        )
        self.add_widget(self.title_label)

        self.close_button = NavButton(
            MDButtonText(text="Close"),
            style="tonal",
            size_hint=(None, None),
            size=(dp(72), dp(40)),
            theme_bg_color="Custom",
            md_bg_color=theme.NAVY_700,
            radius=[dp(20)] * 4,
        )
        self.close_button.bind(on_release=lambda *_: self.close())
        self.add_widget(self.close_button)

        self.search_glass = MDCard(
            size_hint=(None, None),
            height=dp(48),
            theme_bg_color="Custom",
            md_bg_color=theme.GOLD_500,
            line_color=theme.GOLD_300,
            line_width=dp(1),
            radius=[dp(24)] * 4,
            elevation=2,
        )
        self.add_widget(self.search_glass)
        self.search_icon = MDIcon(
            icon=theme.ICON["search"],
            theme_text_color="Custom",
            text_color=theme.NAVY_900,
            font_size="21sp",
            size_hint=(None, None),
            size=(dp(28), dp(28)),
        )
        self.add_widget(self.search_icon)
        self.search_field = TextInput(
            hint_text="Search another room or facility",
            hint_text_color=theme.NAVY_600,
            foreground_color=theme.NAVY_900,
            cursor_color=theme.NAVY_900,
            selection_color=theme.alpha(theme.NAVY_900, 0.24),
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            font_size="14sp",
            padding=[0, dp(13), 0, dp(10)],
            multiline=False,
            size_hint=(None, None),
            height=dp(48),
        )
        self.search_field.bind(text=self._update_search_suggestions)
        self.add_widget(self.search_field)

        self.search_suggestions = MDCard(
            padding=dp(6),
            size_hint=(0.90, None),
            height=dp(1),
            theme_bg_color="Custom",
            md_bg_color=theme.WHITE,
            line_color=theme.GOLD_500,
            line_width=dp(1),
            radius=[dp(14)] * 4,
            opacity=0,
            disabled=True,
            elevation=4,
        )
        self.search_suggestion_list = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            spacing=dp(4),
        )
        self.search_suggestions.add_widget(self.search_suggestion_list)
        self.add_widget(self.search_suggestions)

        self.photo_frame = MDCard(
            size_hint=(None, None),
            height=dp(260),
            theme_bg_color="Custom",
            md_bg_color=theme.WHITE,
            line_color=theme.GOLD_500,
            line_width=dp(2),
            radius=[dp(22)] * 4,
            elevation=5,
        )
        self.add_widget(self.photo_frame)
        self.photo_clip = RoundedPhotoClip(size_hint=(None, None))
        self.add_widget(self.photo_clip)
        self.preview_image = KivyImage(
            source=self.photo_paths[0] if self.photo_paths else "",
            fit_mode=photo_fit,
            size_hint=(None, None),
            opacity=0,
        )
        self.photo_clip.add_widget(self.preview_image)
        if not self.photo_paths:
            self.photo_placeholder = MDLabel(
                text="No room photo available",
                halign="center",
                valign="middle",
                size_hint=(0.86, None),
                height=dp(40),
                theme_text_color="Custom",
                text_color=theme.NAVY_700,
                font_style="Body",
                role="medium",
            )
            self.photo_clip.add_widget(self.photo_placeholder)

        self.details_bar = Widget(size_hint=(None, None))
        self._details_gradient = []
        with self.details_bar.canvas.before:
            for index in range(8):
                color = Color(*theme.alpha(theme.NAVY_900, 0.64 + 0.045 * index))
                rect = Rectangle()
                self._details_gradient.append((color, rect))
        self.photo_clip.add_widget(self.details_bar)

        self.location_label = MDLabel(
            text=self.room_name,
            halign="left",
            valign="middle",
            size_hint=(None, None),
            height=dp(30),
            max_lines=1,
            theme_text_color="Custom",
            text_color=theme.GOLD_300,
            font_style="Title",
            role="medium",
            bold=True,
        )
        self.photo_clip.add_widget(self.location_label)
        self.photo_subtitle_label = MDLabel(
            text=self.photo_caption,
            halign="left",
            valign="middle",
            size_hint=(None, None),
            height=dp(22),
            max_lines=1,
            theme_text_color="Custom",
            text_color=theme.WHITE,
            font_style="Body",
            role="small",
        )
        self.photo_clip.add_widget(self.photo_subtitle_label)

        self.previous_button = NavButton(
            MDButtonText(
                text="Previous",
                theme_text_color="Custom",
                text_color=theme.GOLD_300,
            ),
            style="outlined",
            theme_bg_color="Custom",
            md_bg_color=theme.NAVY_800,
            line_color=theme.GOLD_500,
            line_width=dp(1),
            size_hint=(None, None),
            size=(dp(104), dp(40)),
            theme_text_color="Custom",
            disabled=len(self.photo_paths) < 2,
        )
        self.previous_button.bind(on_release=lambda *_: self.move_photo(-1))
        self.add_widget(self.previous_button)

        self.next_button = NavButton(
            MDButtonText(
                text="Next",
                theme_text_color="Custom",
                text_color=theme.NAVY_900,
            ),
            style="filled",
            size_hint=(None, None),
            size=(dp(84), dp(40)),
            theme_bg_color="Custom",
            md_bg_color=theme.WHITE,
            line_color=theme.WHITE,
            disabled=len(self.photo_paths) < 2,
        )
        self.next_button.bind(on_release=lambda *_: self.move_photo(1))
        self.add_widget(self.next_button)

        self.route_card = MDCard(
            size_hint=(None, None),
            height=dp(190),
            padding=dp(10),
            theme_bg_color="Custom",
            md_bg_color=theme.NAVY_800,
            line_color=theme.GOLD_500,
            line_width=dp(1.4),
            radius=[dp(20)] * 4,
            elevation=3,
        )
        self.add_widget(self.route_card)
        route_content = MDBoxLayout(
            orientation="vertical",
            spacing=dp(4),
        )
        self.route_card.add_widget(route_content)
        route_top = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=1,
        )
        route_content.add_widget(route_top)

        route_text = MDBoxLayout(
            orientation="vertical",
            spacing=dp(3),
            size_hint_x=1,
        )
        route_top.add_widget(route_text)
        self.origin_button = NavButton(
            MDButtonText(
                text=self.origin_label,
                font_size="11sp",
                max_lines=1,
            ),
            style="outlined",
            size_hint=(1, None),
            height=dp(38),
            theme_bg_color="Custom",
            md_bg_color=theme.NAVY_700,
            line_color=theme.GOLD_500,
            radius=[dp(12)] * 4,
        )
        self.origin_button_text = self.origin_button.children[0]
        self.origin_button.bind(on_release=self.open_origin_picker)
        route_text.add_widget(self.origin_button)
        route_text.add_widget(
            MDLabel(
                text=f"To: {self.room_name}",
                halign="left",
                valign="middle",
                size_hint_y=1,
                max_lines=2,
                theme_text_color="Custom",
                text_color=theme.WHITE,
                font_style="Body",
                role="small",
                bold=True,
            )
        )
        self.origin_hint_label = MDLabel(
            text=self.origin_hint,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(18),
            theme_text_color="Custom",
            text_color=theme.GOLD_200,
            font_style="Body",
            role="small",
        )
        route_text.add_widget(self.origin_hint_label)

        self.metrics_card = MDCard(
            size_hint=(None, 1),
            width=dp(112),
            padding=[dp(7), dp(5)],
            theme_bg_color="Custom",
            md_bg_color=theme.GOLD_500,
            radius=[dp(14)] * 4,
            elevation=1,
        )
        route_top.add_widget(self.metrics_card)
        metrics = MDBoxLayout(orientation="vertical", spacing=dp(1))
        self.metrics_card.add_widget(metrics)
        for label, value in (
            ("DISTANCE", self.route_distance),
            ("WALK", self.route_time),
            ("FLOORS", self.floor_changes),
        ):
            metric_group = MDBoxLayout(
                orientation="vertical",
                spacing=0,
                size_hint_y=1,
            )
            metrics.add_widget(metric_group)
            metric_group.add_widget(
                MDLabel(
                    text=label,
                    font_style="Label",
                    role="small",
                    bold=True,
                    size_hint_y=0.43,
                    theme_text_color="Custom",
                    text_color=theme.NAVY_700,
                )
            )
            value_label = MDLabel(
                text=value,
                font_style="Body",
                role="small",
                bold=True,
                size_hint_y=0.57,
                theme_text_color="Custom",
                text_color=theme.NAVY_900,
            )
            metric_group.add_widget(value_label)
            if label == "DISTANCE":
                self.distance_label = value_label
            elif label == "WALK":
                self.time_label = value_label
            else:
                self.floor_changes_label = value_label

        self.view_route_button = NavButton(
            MDButtonIcon(
                icon=theme.ICON["directions"],
                theme_text_color="Custom",
                text_color=theme.GOLD_300,
                font_size="18sp",
            ),
            MDButtonText(
                text="View Multi-floor Map & Route",
                theme_text_color="Custom",
                text_color=theme.GOLD_300,
            ),
            MDButtonIcon(
                icon="arrow-top-right",
                theme_text_color="Custom",
                text_color=theme.GOLD_300,
                font_size="16sp",
            ),
            style="outlined",
            size_hint=(1, None),
            height=dp(38),
            theme_bg_color="Custom",
            md_bg_color=theme.NAVY_700,
            line_color=theme.GOLD_500,
            radius=[dp(14)] * 4,
        )
        self.view_route_button.bind(on_release=self._go)
        route_content.add_widget(self.view_route_button)

        self.go_button = NavButton(
            MDButtonIcon(
                icon=theme.ICON["start"],
                theme_text_color="Custom",
                text_color=theme.NAVY_900,
                font_size="20sp",
            ),
            MDButtonText(
                text="Get Route",
                theme_text_color="Custom",
                text_color=theme.NAVY_900,
                bold=True,
            ),
            style="filled",
            theme_bg_color="Custom",
            md_bg_color=theme.GOLD_500,
            size_hint=(None, None),
            size=(dp(152), dp(50)),
            radius=[dp(25)] * 4,
            elevation=8,
            line_color=theme.GOLD_300,
            line_width=dp(1.5),
        )
        self.go_button.bind(on_release=self._go)
        self.add_widget(self.go_button)

        self._entrance_controls = (
            self.search_field,
            self.close_button,
            self.previous_button,
            self.next_button,
            self.route_card,
            self.go_button,
        )
        self.bind(size=self._layout_preview, pos=self._layout_preview)
        self._layout_preview()
        self._update_caption()
        self._update_route_estimate()

    def on_touch_down(self, touch):
        if super().on_touch_down(touch):
            return True
        return self.collide_point(*touch.pos)

    def _update_search_suggestions(self, _field, query):
        self.search_suggestion_list.clear_widgets()
        query_tokens = re.findall(r"[a-z0-9]+", query.lower())
        matches = []
        if query_tokens:
            for room_code, room_info in _search_destinations():
                searchable = " ".join(
                    (
                        room_code,
                        room_info["name"],
                        room_info["directions"],
                        room_info.get("keywords", ""),
                        FLOOR_CONFIG.get(room_info["floor"], {}).get("display", ""),
                    )
                )
                searchable_tokens = re.findall(r"[a-z0-9]+", searchable.lower())
                if all(
                    any(token in candidate for candidate in searchable_tokens)
                    for token in query_tokens
                ):
                    matches.append((room_code, room_info))
                if len(matches) == 5:
                    break

        for room_code, room_info in matches:
            display_code = room_info["room_no"] or room_code.rsplit(":", 1)[-1]
            result_button = NavButton(
                MDButtonText(
                    text=f'{display_code}  ·  {room_info["name"]}',
                    halign="left",
                ),
                style="text",
                size_hint_y=None,
                height=dp(44),
            )
            result_button.bind(
                on_release=lambda *_args, code=room_code, info=room_info:
                self._select_search_result(code, info)
            )
            self.search_suggestion_list.add_widget(result_button)

        self.search_suggestions.height = (
            self.search_suggestion_list.height + dp(12) if matches else 0
        )
        self.search_suggestions.opacity = 1 if matches else 0
        self.search_suggestions.disabled = not matches

    def _select_search_result(self, room_code, room_info):
        if self.search_callback:
            self.search_callback(room_code, room_info)

    def _update_background(self, *_args):
        self._background.pos = self.pos
        self._background.size = self.size

    def _layout_preview(self, *_args):
        if not self.width or not self.height:
            return
        gutter = dp(18)
        photo_width = min(self.width - gutter * 2, dp(520))
        photo_height = min(
            dp(270),
            self.height * 0.32,
            max(dp(140), self.height - dp(450)),
        )
        photo_x = self.center_x - photo_width / 2
        photo_top = self.top - dp(158)
        photo_y = photo_top - photo_height
        self.title_label.pos = (self.x + gutter, self.top - dp(48))
        self.close_button.pos = (self.right - gutter - dp(72), self.top - dp(46))
        self.search_glass.pos = (photo_x, self.top - dp(106))
        self.search_glass.size = (photo_width, dp(48))
        self.search_icon.pos = (photo_x + dp(14), self.top - dp(96))
        self.search_field.size = (photo_width - dp(56), dp(48))
        self.search_field.pos = (
            photo_x + dp(46),
            self.top - dp(106),
        )
        self.search_suggestions.width = photo_width
        self.search_suggestions.pos = (
            self.center_x - self.search_suggestions.width / 2,
            self.top - dp(111) - self.search_suggestions.height,
        )
        self.photo_frame.pos = (photo_x, photo_y)
        self.photo_frame.size = (photo_width, photo_height)
        self.photo_clip.pos = (photo_x + dp(4), photo_y + dp(4))
        self.photo_clip.size = (photo_width - dp(8), photo_height - dp(8))
        self.preview_image.pos = self.photo_clip.pos
        self.preview_image.size = self.photo_clip.size
        if hasattr(self, "photo_placeholder"):
            self.photo_placeholder.pos = (
                self.photo_clip.x + dp(18),
                self.photo_clip.y + self.photo_clip.height / 2 - dp(20),
            )
        band_height = min(dp(96), photo_height * 0.38)
        self.details_bar.pos = self.photo_clip.pos
        self.details_bar.size = (self.photo_clip.width, band_height)
        location_height = min(dp(30), max(dp(22), band_height * 0.38))
        subtitle_height = min(
            dp(22), max(dp(18), band_height - location_height - dp(8))
        )
        self.location_label.height = location_height
        self.location_label.width = self.photo_clip.width - dp(24)
        self.photo_subtitle_label.height = subtitle_height
        self.photo_subtitle_label.width = self.photo_clip.width - dp(26)
        strip_height = band_height / len(self._details_gradient)
        for index, (_, rect) in enumerate(self._details_gradient):
            rect.pos = (
                self.details_bar.x,
                self.details_bar.y + index * strip_height,
            )
            rect.size = (self.details_bar.width, strip_height + dp(1))
        self.location_label.pos = (
            self.photo_clip.x + dp(12),
            self.photo_clip.y + band_height - location_height - dp(3),
        )
        self.photo_subtitle_label.pos = (
            self.photo_clip.x + dp(13),
            self.photo_clip.y + dp(4),
        )
        gallery_y = photo_y - dp(43)
        gallery_width = (
            self.previous_button.width + dp(12) + self.next_button.width
        )
        gallery_x = photo_x + (photo_width - gallery_width) / 2
        self.previous_button.pos = (gallery_x, gallery_y)
        self.next_button.pos = (
            self.previous_button.right + dp(12),
            gallery_y,
        )
        self.route_card.size = (photo_width, min(dp(188), self.height * 0.24))
        self.route_card.pos = (
            photo_x,
            gallery_y - self.route_card.height - dp(12),
        )
        self.go_button.pos = (
            photo_x + photo_width - self.go_button.width,
            self.y + dp(18),
        )
        self.go_button.size = (dp(152), dp(50))

    def open_animation(self, *_args):
        if not self.width or not self.height:
            return
        self._layout_preview()
        thumbnail_size = min(
            dp(56), self.photo_clip.width, self.photo_clip.height
        )
        self.preview_image.size = (thumbnail_size, thumbnail_size)
        self.preview_image.pos = (
            self.photo_clip.center_x - thumbnail_size / 2,
            self.photo_clip.center_y - thumbnail_size / 2,
        )
        Animation.cancel_all(self, "opacity")
        Animation.cancel_all(
            self.preview_image, "x", "y", "width", "height", "opacity"
        )
        Animation(opacity=1, duration=0.18, t="out_quad").start(self)
        Animation(
            x=self.photo_clip.x,
            y=self.photo_clip.y,
            width=self.photo_clip.width,
            height=self.photo_clip.height,
            opacity=1,
            duration=0.38,
            t="out_cubic",
        ).start(self.preview_image)
        Clock.schedule_once(self._animate_entrance_controls, 0.04)

    def _animate_entrance_controls(self, *_args):
        for index, widget in enumerate(self._entrance_controls):
            target_y = widget.y
            widget.y = target_y + dp(24)
            widget.opacity = 0
            Clock.schedule_once(
                lambda _dt, item=widget, final_y=target_y: Animation(
                    y=final_y, opacity=1, duration=0.32, t="out_cubic"
                ).start(item),
                index * 0.045,
            )

    def close(self):
        Animation.cancel_all(self, "opacity")
        animation = Animation(opacity=0, duration=0.16, t="out_quad")
        animation.bind(on_complete=lambda *_: self._remove_from_parent())
        animation.start(self)

    def _remove_from_parent(self):
        if self.parent:
            self.parent.remove_widget(self)

    def move_photo(self, offset):
        if not self.photo_paths:
            return
        self.photo_index = (self.photo_index + offset) % len(self.photo_paths)
        self.preview_image.source = self.photo_paths[self.photo_index]
        self._update_caption()

    def _update_caption(self):
        if self.photo_paths:
            self.photo_caption = (
                f"Photo {self.photo_index + 1} of {len(self.photo_paths)}"
            )
        else:
            self.photo_caption = "No photo available"
        self.photo_subtitle_label.text = self.photo_caption

    def _go(self, *_args):
        if self.go_callback:
            self.go_callback(self.selected_origin_room)

    def open_origin_picker(self, *_args):
        if self._origin_popup is not None:
            self._origin_popup.dismiss()
        content = MDBoxLayout(
            orientation="vertical",
            padding=dp(12),
            spacing=dp(8),
            theme_bg_color="Custom",
            md_bg_color=theme.PAPER,
        )
        search = MDTextField(
            mode="outlined",
            size_hint_y=None,
            height=dp(52),
            theme_bg_color="Custom",
            md_bg_color=theme.WHITE,
        )
        search.add_widget(
            MDTextFieldHintText(
                text="Search by room name or floor",
                text_color_normal=theme.NAVY_400,
            )
        )
        content.add_widget(search)
        scroll = ScrollView(do_scroll_x=False)
        self._origin_options = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(4),
        )
        scroll.add_widget(self._origin_options)
        content.add_widget(scroll)
        search.bind(text=self._filter_origin_options)
        self._origin_popup = Popup(
            title="Choose a starting point",
            content=content,
            size_hint=(0.90, 0.78),
            separator_color=theme.GOLD_500,
            title_color=theme.NAVY_900,
            background_color=theme.PAPER,
            overlay_color=theme.alpha(theme.PAPER, 0.72),
            auto_dismiss=True,
        )
        self._filter_origin_options(search, "")
        self._origin_popup.open()

    def _filter_origin_options(self, _field, query):
        self._origin_options.clear_widgets()
        normalized = query.strip().casefold()
        use_current = NavButton(
            MDButtonText(
                text="Current Location · choose floor and tap the map",
                halign="left",
                theme_text_color="Custom",
                text_color=theme.NAVY_900,
            ),
            style="outlined",
            size_hint_y=None,
            height=dp(48),
            theme_bg_color="Custom",
            md_bg_color=theme.WHITE,
            line_color=theme.GOLD_500,
        )
        use_current.bind(
            on_release=lambda *_: self._select_origin_room("")
        )
        self._origin_options.add_widget(use_current)

        rooms = sorted(
            ROOMS_BY_ID.values(),
            key=lambda item: (FLOORS.index(item.floor), item.name.casefold()),
        )
        matches = 0
        for room in rooms:
            floor_label = "LG" if room.floor == "LG" else f"{room.floor}F"
            label = f"{room.name} · {floor_label}"
            if normalized and normalized not in label.casefold():
                continue
            button = NavButton(
                MDButtonText(
                    text=label,
                    halign="left",
                    theme_text_color="Custom",
                    text_color=theme.NAVY_900,
                ),
                style="outlined",
                size_hint_y=None,
                height=dp(48),
                theme_bg_color="Custom",
                md_bg_color=theme.WHITE,
                line_color=theme.LINE,
                radius=[dp(12)] * 4,
            )
            button.bind(
                on_release=lambda *_args, selected=room.room_id:
                self._select_origin_room(selected)
            )
            self._origin_options.add_widget(button)
            matches += 1
            if matches >= 20:
                break

    def _select_origin_room(self, room_id):
        self.selected_origin_room = room_id
        if self._origin_popup is not None:
            self._origin_popup.dismiss()
            self._origin_popup = None
        if room_id:
            room = ROOMS_BY_ID[room_id]
            floor_label = "LG" if room.floor == "LG" else f"{room.floor}F"
            self.origin_label = f"From: {room.name} · {floor_label}"
            self.origin_button_text.text = self.origin_label
        else:
            self.origin_label = "From: Current Location"
            self.origin_button_text.text = self.origin_label
        self._update_route_estimate()

    def _update_route_estimate(self):
        if not self.selected_origin_room:
            self.origin_hint = "Set your start on the map"
            self.route_distance = "--"
            self.route_time = "--"
            self.floor_changes = "Set start"
        else:
            source = ROOMS_BY_ID[self.selected_origin_room]
            destination = ROOMS_BY_ID[self.destination_code]
            route = shortest_path(
                source.door_nodes[0],
                destination.door_nodes[0],
                preference=DEFAULT_TRAVEL_PREFERENCE,
            )
            if route is None:
                self.origin_hint = "No connected route"
                self.route_distance = "--"
                self.route_time = "--"
                self.floor_changes = "--"
            else:
                distance = route_distance_meters(route)
                changes = sum(
                    first.floor != second.floor
                    for first, second in zip(route, route[1:])
                )
                self.origin_hint = "Route ready · estimates use the map"
                self.route_distance = format_distance(distance)
                self.route_time = f"~{format_duration(walk_seconds(distance))}"
                self.floor_changes = (
                    f"{changes} floor change"
                    f"{'s' if changes != 1 else ''}"
                )
        self.distance_label.text = self.route_distance
        self.time_label.text = self.route_time
        self.floor_changes_label.text = self.floor_changes
        self.origin_hint_label.text = self.origin_hint


class HomeScreen(MDScreen):
    """Landing screen: brand, hero image and the get-started action."""

    def on_enter(self, *args):
        Clock.schedule_once(self._animate_welcome, 0.08)

    def _animate_welcome(self, *_args):
        animated_widgets = (
            self.ids.brand_label,
            self.ids.brand_glow,
            self.ids.brand_mark,
            self.ids.welcome_title,
            self.ids.welcome_subtitle,
            self.ids.start_button,
        )
        for index, widget in enumerate(animated_widgets):
            Animation.cancel_all(widget, "opacity", "y")
            target_y = widget.y
            widget.opacity = 0
            widget.y = target_y - dp(18)
            Clock.schedule_once(
                lambda _dt, item=widget, final_y=target_y: Animation(
                    opacity=1, y=final_y, duration=0.48, t="out_cubic"
                ).start(item),
                index * 0.08,
            )

class VerticalGradientOverlay(Widget):
    """Draw a smooth, three-stop vertical overlay using thin color bands."""

    top_color = ListProperty(theme.alpha(theme.NAVY_900, 0.82))
    middle_color = ListProperty(theme.alpha(theme.NAVY_900, 0.30))
    bottom_color = ListProperty(theme.alpha(theme.NAVY_900, 0.84))
    STRIP_COUNT = 128

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(
            pos=self._redraw,
            size=self._redraw,
            top_color=self._redraw,
            middle_color=self._redraw,
            bottom_color=self._redraw,
        )
        self._redraw()

    @staticmethod
    def _interpolate_color(start, end, progress):
        return tuple(
            start[index] + (end[index] - start[index]) * progress
            for index in range(4)
        )

    @classmethod
    def _color_at(cls, position, bottom, middle, top):
        position = min(1.0, max(0.0, position))
        if position == 0:
            return tuple(bottom)
        if position == 0.5:
            return tuple(middle)
        if position == 1:
            return tuple(top)
        if position < 0.5:
            return cls._interpolate_color(bottom, middle, position * 2)
        return cls._interpolate_color(middle, top, (position - 0.5) * 2)

    def _redraw(self, *_args):
        self.canvas.before.clear()
        if self.width <= 0 or self.height <= 0:
            return

        strip_height = self.height / self.STRIP_COUNT
        with self.canvas.before:
            for index in range(self.STRIP_COUNT):
                progress = (index + 0.5) / self.STRIP_COUNT
                Color(
                    rgba=self._color_at(
                        progress,
                        self.bottom_color,
                        self.middle_color,
                        self.top_color,
                    )
                )
                Rectangle(
                    pos=(self.x, self.y + index * strip_height),
                    size=(self.width, strip_height + 1),
                )


class WelcomeStartButton(NavButton):
    """Gold welcome action with a subtle animated press scale."""

    press_scale = NumericProperty(1.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            PushMatrix()
            self._press_transform = Scale(1, 1, 1)
        with self.canvas.after:
            PopMatrix()
        self.bind(
            center=self._update_press_transform,
            press_scale=self._update_press_transform,
        )
        self.bind(on_press=self._animate_pressed)
        self.bind(on_release=self._animate_released)
        self._update_press_transform()

    def _update_press_transform(self, *_args):
        self._press_transform.x = self.press_scale
        self._press_transform.y = self.press_scale
        self._press_transform.origin = (self.center_x, self.center_y, 0)

    def _animate_pressed(self, *_args):
        Animation.cancel_all(self, "press_scale")
        Animation(
            press_scale=0.96,
            duration=0.09,
            t="out_quad",
        ).start(self)

    def _animate_released(self, *_args):
        Animation.cancel_all(self, "press_scale")
        Animation(
            press_scale=1.0,
            duration=0.16,
            t="out_quad",
        ).start(self)


class CampusCard(MDCard):
    """A campus tile that lifts and casts a shadow under the pointer."""

    campus_name = StringProperty("")
    campus_key = StringProperty("")
    subtitle = StringProperty("")
    logo_source = StringProperty(CAMPUS_LOGO_PATH)
    image_source = StringProperty("")
    banner_source = StringProperty("")
    profile_source = StringProperty("")
    image_loaded = BooleanProperty(False)
    banner_texture = ObjectProperty(None, allownone=True)
    banner_tex_coords = ListProperty([0, 0, 1, 0, 1, 1, 0, 1])
    zoom_scale = NumericProperty(1.0)
    float_scale = NumericProperty(1.0)
    press_scale = NumericProperty(1.0)
    filter_scale = NumericProperty(1.0)
    filter_visible = BooleanProperty(True)
    shadow_opacity = NumericProperty(0.0)
    shadow_offset_x = NumericProperty(0.0)
    shadow_offset_y = NumericProperty(0.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._active_touch_uid = None
        self._pointer_hovered = False
        self._selection_pending = False
        self.bind(
            on_enter=self._on_pointer_enter,
            on_leave=self._on_pointer_leave,
            size=self._update_banner_tex_coords,
            banner_texture=self._update_banner_tex_coords,
        )

    def on_campus_key(self, _instance, campus_key):
        self.image_loaded = False
        self.banner_texture = None
        self.image_source = _resolve_campus_image(campus_key)
        self.banner_source = self.image_source
        self.profile_source = _resolve_campus_profile(campus_key)
        if self.image_source:
            print("Loading campus banner:", self.image_source)
        else:
            print(f"Campus banner not found for {campus_key!r}; using placeholder.")
        if self.profile_source:
            print("Loading campus profile:", self.profile_source)
        else:
            print(f"Campus profile not found for {campus_key!r}.")

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        banner = self.ids.get("campus_banner")
        if banner is not None:
            banner.bind(texture=self._on_campus_image_texture)
            self._banner_background_layout = banner.parent
            with self._banner_background_layout.canvas.before:
                self._banner_background_color = Color(1, 1, 1, 0)
                self._banner_background_rect = Rectangle()
            self._banner_background_layout.bind(
                pos=self._update_banner_background,
                size=self._update_banner_background,
            )
            self._on_campus_image_texture(banner, banner.texture)

    def _on_campus_image_texture(self, image, texture):
        self.image_loaded = texture is not None
        self.banner_texture = texture
        self._update_banner_background()

    def _update_banner_tex_coords(self, *_args):
        texture = self.banner_texture
        if texture is None or self.width <= 0 or self.height <= 0:
            self._update_banner_background()
            return

        source_ratio = texture.width / texture.height
        target_ratio = self.width / self.height
        # Crop the texture coordinates to fill the card without distorting it.
        if source_ratio > target_ratio:
            visible_width = target_ratio / source_ratio
            left = (1 - visible_width) / 2
            self.banner_tex_coords = [
                left, 1, left + visible_width, 1,
                left + visible_width, 0, left, 0,
            ]
        else:
            visible_height = source_ratio / target_ratio
            bottom = (1 - visible_height) / 2
            top = bottom + visible_height
            self.banner_tex_coords = [
                0, top, 1, top,
                1, bottom, 0, bottom,
            ]
        self._update_banner_background()

    def _update_banner_background(self, *_args):
        if not hasattr(self, "_banner_background_rect"):
            return

        layout = self._banner_background_layout
        texture = self.banner_texture
        self._banner_background_color.rgba = (
            1, 1, 1, 1 if texture is not None else 0
        )
        self._banner_background_rect.pos = layout.pos
        self._banner_background_rect.size = layout.size
        self._banner_background_rect.texture = texture
        self._banner_background_rect.tex_coords = self.banner_tex_coords

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._active_touch_uid = touch.uid
            self._selection_pending = False
            self._update_shadow_position(*touch.pos)
            Animation.cancel_all(self, "press_scale")
            Animation(
                press_scale=0.97,
                duration=0.08,
                t="out_quad",
            ).start(self)
            self._animate_lift(True)
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.uid == self._active_touch_uid:
            self._update_shadow_position(*touch.pos)
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        was_active_touch = touch.uid == self._active_touch_uid
        if was_active_touch:
            self._active_touch_uid = None
        handled = super().on_touch_up(touch)
        if was_active_touch:
            self._animate_lift(
                self._pointer_hovered and not self._selection_pending
            )
            if not self._selection_pending:
                Animation.cancel_all(self, "press_scale")
                Animation(
                    press_scale=1.0,
                    duration=0.16,
                    t="out_quad",
                ).start(self)
        return handled

    def _on_pointer_enter(self, *_args):
        self._pointer_hovered = True
        Window.bind(mouse_pos=self._on_mouse_pos)
        if self._active_touch_uid is None:
            self._animate_lift(True)
            self._update_shadow_position(*Window.mouse_pos)

    def _on_pointer_leave(self, *_args):
        self._pointer_hovered = False
        Window.unbind(mouse_pos=self._on_mouse_pos)
        if self._active_touch_uid is None:
            self._animate_lift(False)

    def _on_mouse_pos(self, _window, pos):
        if self._pointer_hovered:
            self._update_shadow_position(*pos)

    def _update_shadow_position(self, x, y):
        Animation.cancel_all(self, "shadow_offset_x", "shadow_offset_y")
        local_x = (x - self.x) / max(self.width, 1)
        local_y = (y - self.y) / max(self.height, 1)
        self.shadow_offset_x = dp(10) * (max(0, min(1, local_x)) - 0.5) * 2
        self.shadow_offset_y = dp(10) * (max(0, min(1, local_y)) - 0.5) * 2

    def _animate_lift(self, lifted):
        Animation.cancel_all(self, "float_scale", "shadow_opacity")
        Animation(
            float_scale=1.035 if lifted and self._active_touch_uid is None else 1.0,
            shadow_opacity=1.0 if lifted else 0.0,
            duration=0.18,
            t="out_cubic",
        ).start(self)
        if not lifted:
            Animation.cancel_all(self, "shadow_offset_x", "shadow_offset_y")
            Animation(
                shadow_offset_x=0.0,
                shadow_offset_y=0.0,
                duration=0.18,
                t="out_cubic",
            ).start(self)


class CampusScreen(MDScreen):
    """Campus picker with live filtering of its campus cards."""

    logo_source = StringProperty(CAMPUS_LOGO_PATH)
    search_focus_progress = NumericProperty(0.0)
    search_icon_scale = NumericProperty(1.0)
    search_icon_angle = NumericProperty(0.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._search_input_bound = False

    def on_enter(self, *_args):
        super().on_enter(*_args)
        if self.children:
            self.children[0].do_layout()
        if not self._search_input_bound and "search_input" in self.ids:
            search_input = self.ids.search_input
            search_input.bind(
                text=self._on_search_text,
                focus=self._on_search_focus,
            )
            self._search_input_bound = True

    def _on_search_text(self, _search_input, query):
        self.filter_campuses(query)

    def _on_search_focus(self, _search_input, focused):
        self.animate_search_focus(focused)

    def filter_campuses(self, query):
        query = re.sub(r"\s+", " ", query).strip().casefold()
        for card in self.ids.campus_grid.children:
            searchable = re.sub(
                r"\s+", " ", f"{card.campus_name} {card.subtitle}"
            ).casefold()
            matches = query in searchable
            card.filter_visible = matches
            card.disabled = not matches
            Animation.cancel_all(
                card, "opacity", "height", "filter_scale"
            )
            Animation(
                opacity=1.0 if matches else 0.0,
                height=dp(188) if matches else 0.0,
                filter_scale=1.0 if matches else 0.95,
                duration=0.25,
                t="out_quad",
            ).start(card)

    def animate_search_focus(self, focused):
        Animation.cancel_all(
            self,
            "search_focus_progress",
            "search_icon_scale",
            "search_icon_angle",
        )
        Animation(
            search_focus_progress=1.0 if focused else 0.0,
            search_icon_scale=1.12 if focused else 1.0,
            search_icon_angle=90.0 if focused else 0.0,
            duration=0.2,
            t="out_quad",
        ).start(self)


class RoomSearchScreen(MDScreen):
    """Search local room data, preview a result, and open its route."""

    selected_floor = StringProperty("LG")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._room_preview = None

    def on_enter(self, *_args):
        self.update_results()

    def update_results(self, *_args):
        if "results_list" not in self.ids or "status_label" not in self.ids:
            return

        query = self.ids.search_input.text.strip().casefold()
        query_tokens = re.findall(r"[a-z0-9]+", query)
        matches = []
        for room_code, room_info in _search_destinations():
            if (
                self.selected_floor != "ALL"
                and room_info["floor"] != self.selected_floor
            ):
                continue
            floor_display = FLOOR_CONFIG.get(
                room_info["floor"], {}
            ).get("display", room_info["floor"])
            searchable = " ".join(
                (
                    room_code,
                    room_info["name"],
                    room_info["directions"],
                    room_info.get("keywords", ""),
                    floor_display,
                )
            ).casefold()
            searchable_tokens = re.findall(r"[a-z0-9]+", searchable)
            if all(
                any(token in candidate for candidate in searchable_tokens)
                for token in query_tokens
            ):
                matches.append((room_code, room_info))

        results_list = self.ids.results_list
        results_list.data = [
            {
                "room_code": room_code,
                "room_name": room_info["name"],
                "floor_display": FLOOR_CONFIG.get(
                    room_info["floor"], {}
                ).get("display", room_info["floor"]),
                "room_description": _search_result_description(room_info),
                "room_info": room_info,
                "search_screen": self,
            }
            for room_code, room_info in matches
        ]

        if matches:
            self.ids.status_label.text = (
                f"{len(matches)} destination"
                f"{'s' if len(matches) != 1 else ''} found."
            )
        elif query_tokens:
            self.ids.status_label.text = "No matching rooms or facilities."
        else:
            self.ids.status_label.text = "Type to search rooms and facilities."

    def select_floor(self, floor):
        self.selected_floor = floor
        self.update_results()

    def show_room_preview(self, room_code, room_info, *_args):
        if self._room_preview and self._room_preview.parent:
            self._room_preview.close()

        floor_display = FLOOR_CONFIG.get(
            room_info["floor"], {}
        ).get("display", room_info["floor"])
        full_floor_name = {
            "LG": "Lower Ground Floor",
            "lower_ground": "Lower Ground Floor",
            "1": "1st Floor",
            "2": "2nd Floor",
            "3": "3rd Floor",
            "4": "4th Floor",
            "5": "5th Floor",
        }.get(room_info["floor"], floor_display)
        photo_paths = resolve_room_photos(
            room_info.get("legacy_code") or room_code,
            floor=room_info.get("floor"),
            room_no=room_info.get("room_no", ""),
            room_name=room_info.get("name", ""),
        )
        self._room_preview = RoomPreviewOverlay(
            photos=photo_paths,
            room_name=room_info["name"],
            room_floor=f"{floor_display} • {full_floor_name}",
            room_description=room_info["directions"],
            destination_code=room_code,
            go_callback=partial(self._open_route, room_code, room_info),
            search_callback=self.show_room_preview,
        )
        self.add_widget(self._room_preview)
        Clock.schedule_once(self._room_preview.open_animation, 0)

    def _open_route(self, room_code, room_info, start_room_id=""):
        if self._room_preview:
            self._room_preview.close()
        app = App.get_running_app()
        if app is None:
            raise RuntimeError("Cannot open a route without a running NavU app.")
        app.open_route(
            room_code,
            room_info["name"],
            room_info,
            start_room_id=start_room_id,
        )
