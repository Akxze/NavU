"""One row in the turn-by-turn directions list."""

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDIcon, MDLabel

from . import theme
from .directions import format_distance


class RouteStepRow(MDBoxLayout):
    """A maneuver: icon, instruction and the distance to the next one.

    The row the walker is currently following is filled with gold, matching how
    a navigation app highlights the active instruction.
    """

    def __init__(self, step, active=False, is_last=False, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(60))
        kwargs.setdefault("spacing", "10dp")
        kwargs.setdefault("padding", [0, 0, 0, 0])
        super().__init__(**kwargs)

        self.step = step
        self._active = active

        self.add_widget(self._build_icon(step, active))
        self.add_widget(self._build_text(step, active, is_last))
        self.add_widget(self._build_distance(step, active))

    # ------------------------------------------------------------------
    def _build_icon(self, step, active):
        fill = theme.GOLD_500 if active else theme.PAPER_DIM
        glyph = theme.NAVY_800 if active else theme.NAVY_600

        card = MDCard(
            style="filled",
            size_hint=(None, None),
            size=(dp(38), dp(38)),
            pos_hint={"center_y": 0.5},
            theme_bg_color="Custom",
            md_bg_color=fill,
            radius=[dp(19)] * 4,
            elevation=0,
        )
        card.add_widget(
            MDIcon(
                icon=step.icon,
                halign="center",
                valign="center",
                theme_text_color="Custom",
                text_color=glyph,
                font_size="20sp",
                size_hint=(1, 1),
            )
        )
        return card

    def _build_text(self, step, active, is_last):
        column = MDBoxLayout(
            orientation="vertical",
            spacing="1dp",
            pos_hint={"center_y": 0.5},
        )
        column.add_widget(
            MDLabel(
                text=step.title,
                font_style="Body",
                role="medium",
                bold=True,
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(22),
                theme_text_color="Custom",
                text_color=theme.NAVY_800 if active else theme.INK,
            )
        )
        column.add_widget(
            MDLabel(
                text=step.corridor if is_last else step.instruction,
                font_style="Body",
                role="small",
                halign="left",
                valign="middle",
                size_hint_y=None,
                height=dp(18),
                shorten=True,
                shorten_from="right",
                theme_text_color="Custom",
                text_color=theme.INK_SOFT,
            )
        )
        return column

    def _build_distance(self, step, active):
        return MDLabel(
            text=format_distance(step.distance_meters),
            font_style="Body",
            role="small",
            bold=active,
            halign="right",
            valign="middle",
            size_hint_x=None,
            width=dp(58),
            theme_text_color="Custom",
            text_color=theme.NAVY_700 if active else theme.INK_FAINT,
        )
