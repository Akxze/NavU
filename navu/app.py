import os
import sys
import time
import math

from kivy import platform
from kivy.config import Config

PHONE_PREVIEW_SIZE = (393, 852)
Config.set("graphics", "width", str(PHONE_PREVIEW_SIZE[0]))
Config.set("graphics", "height", str(PHONE_PREVIEW_SIZE[1]))
if platform not in ("android", "ios"):
    Config.set("graphics", "resizable", "0")

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.uix.widget import Widget
from kivy.uix.screenmanager import SlideTransition
from kivymd.app import MDApp
from kivymd.uix.button import MDButtonText
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogHeadlineText,
    MDDialogSupportingText,
)

from . import map_widget, route_screen, screens
from .config import BASE_DIR, KV_FILES
from .theme import PRIMARY_PALETTE
from .widgets import NavButton

LIVE_RELOAD_FILES = (
    os.path.join(BASE_DIR, "NavU.py"),
    __file__,
    os.path.join(BASE_DIR, "navu", "config.py"),
    os.path.join(BASE_DIR, "navu", "map_widget.py"),
    os.path.join(BASE_DIR, "navu", "routing.py"),
    os.path.join(BASE_DIR, "navu", "route_screen.py"),
    os.path.join(BASE_DIR, "navu", "location.py"),
    os.path.join(BASE_DIR, "navu", "screens.py"),
    os.path.join(BASE_DIR, "navu", "widgets.py"),
    os.path.join(BASE_DIR, "navu.kv"),
    *KV_FILES,
)


class SpringSlideTransition(SlideTransition):
    """Slide screens with a damped, non-overshooting spring curve."""

    def on_progress(self, progression):
        start = progression
        eased = 1 - (1 + 8 * start) * math.exp(-8 * start)
        end = 1 - 9 * math.exp(-8)
        progress = eased / end if end else start

        incoming = self.screen_in
        outgoing = self.screen_out
        manager = self.manager
        x, y = manager.pos
        width, height = manager.size
        if self.direction == "left":
            incoming.y = outgoing.y = y
            incoming.x = x + width * (1 - progress)
            outgoing.x = x - width * progress
        elif self.direction == "right":
            incoming.y = outgoing.y = y
            outgoing.x = x + width * progress
            incoming.x = x - width * (1 - progress)
        elif self.direction == "down":
            incoming.x = outgoing.x = x
            incoming.y = y + height * (1 - progress)
            outgoing.y = y - height * progress
        else:
            incoming.x = outgoing.x = x
            outgoing.y = y + height * progress
            incoming.y = y - height * (1 - progress)


class NavUApp(MDApp):
    title = "NavU"
    dialog = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._route_return_screen = "room_search"

    def load_kv(self, filename=None):
        widget_classes = (
            map_widget.RouteMap,
            screens.HomeScreen,
            screens.VerticalGradientOverlay,
            screens.WelcomeStartButton,
            screens.CampusCard,
            screens.CampusScreen,
            screens.RoomSearchScreen,
            route_screen.RouteScreen,
            route_screen.NavigationSheetCard,
            screens.RouteSheetHandle,
            screens.RoomPreviewOverlay,
            NavButton,
        )
        for widget_class in widget_classes:
            Factory.register(widget_class.__name__, cls=widget_class)
        for kv_file in KV_FILES:
            Builder.load_file(kv_file)
        root_kv = filename or os.path.join(BASE_DIR, "navu.kv")
        return super().load_kv(filename=root_kv)

    def build(self):
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = PRIMARY_PALETTE
        if self.root:
            self.root.transition = SlideTransition(duration=0.34)

        if platform not in ("android", "ios"):
            Window.set_icon(os.path.join(BASE_DIR, "assets", "NAVU_LOGO.png"))

    def on_start(self):
        if platform not in ("android", "ios"):
            Window.size = PHONE_PREVIEW_SIZE
            self._source_mtimes = self._get_source_mtimes()
            self._restart_at = None
            Clock.schedule_interval(self._check_for_source_updates, 0.5)

    def on_stop(self):
        if self.root:
            self.root.get_screen("route").stop_tracking()

    def on_pause(self):
        return True

    def _get_source_mtimes(self):
        return {
            path: os.stat(path).st_mtime_ns
            for path in LIVE_RELOAD_FILES
            if os.path.isfile(path)
        }

    def _check_for_source_updates(self, elapsed):
        changed = False
        for path in LIVE_RELOAD_FILES:
            try:
                modified_at = os.stat(path).st_mtime_ns
            except OSError:
                continue
            if self._source_mtimes.get(path) != modified_at:
                self._source_mtimes[path] = modified_at
                changed = True

        if changed:
            self._restart_at = time.monotonic() + 1.0

        if self._restart_at is not None and time.monotonic() >= self._restart_at:
            print("Source file changed; restarting NavU...")
            os.execv(sys.executable, [sys.executable, *sys.argv])

    def switch_screen(self, screen_name):
        if self.root:
            if self.root.transition.is_active:
                self.root.transition.stop()
            screen_order = {
                "home": 0,
                "campus": 1,
                "room_search": 2,
                "route": 3,
            }
            current_order = screen_order.get(self.root.current, 0)
            target_order = screen_order.get(screen_name, current_order)
            self.root.transition.direction = (
                "left" if target_order >= current_order else "right"
            )
            self.root.transition = SpringSlideTransition(
                direction=self.root.transition.direction,
                duration=0.42,
            )
            self.root.current = screen_name

    def open_route(
        self,
        room_code,
        room_name,
        room_info=None,
        start_room_id="",
    ):
        if self.root.current != "route":
            self._route_return_screen = self.root.current
        route_screen = self.root.get_screen("route")
        route_screen.configure_destination(
            room_code,
            room_name,
            room_info,
            start_room_id=start_room_id,
        )
        self.switch_screen("route")

    def return_from_route(self):
        if self.root is None:
            raise RuntimeError("Cannot exit a route without a screen manager.")

        route_screen = self.root.get_screen("route")
        route_screen.reset_for_exit()
        return_screen = self._route_return_screen
        if return_screen not in ("home", "campus", "room_search"):
            return_screen = "room_search"
        self._route_return_screen = "room_search"
        self.switch_screen(return_screen)

    def select_campus(self, campus_name, coming_soon=False, card=None):
        if card is not None:
            card._selection_pending = True
            Animation.cancel_all(card, "press_scale")
            animation = Animation(
                press_scale=0.97, duration=0.06, t="out_quad"
            ) + Animation(press_scale=1.0, duration=0.16, t="out_quad")
            animation.bind(
                on_complete=lambda *_: self._finish_campus_selection(
                    campus_name, coming_soon, card
                )
            )
            animation.start(card)
            return

        self._finish_campus_selection(campus_name, coming_soon)

    def _finish_campus_selection(self, campus_name, coming_soon, card=None):
        if card is not None:
            card._selection_pending = False
            card.press_scale = 1.0
        if coming_soon:
            self.show_coming_soon_dialog(campus_name)
        else:
            self.switch_screen("room_search")

    def show_coming_soon_dialog(self, campus_name):
        if self.dialog:
            self.dialog.dismiss()

        close_button = NavButton(
            MDButtonText(text="OK"),
            style="text",
        )
        self.dialog = MDDialog(
            MDDialogHeadlineText(text="Coming soon"),
            MDDialogSupportingText(
                text=f"Navigation map for {campus_name} is currently under development."
            ),
            MDDialogButtonContainer(
                Widget(),
                close_button,
                spacing="8dp",
            ),
        )
        close_button.bind(on_release=lambda *_: self.dialog.dismiss())
        self.dialog.open()
