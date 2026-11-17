"""Small shared widgets reused across the NavU screens."""

from kivymd.uix.button import MDButton, MDIconButton

from . import theme


class NavButton(MDButton):
    """Shared app button using KivyMD's native hover and ripple effects."""


class IconButton(MDIconButton):
    """Circular icon button on a white surface, navy glyph by default."""

    def __init__(self, **kwargs):
        kwargs.setdefault("style", "standard")
        kwargs.setdefault("theme_bg_color", "Custom")
        kwargs.setdefault("md_bg_color", theme.WHITE)
        kwargs.setdefault("theme_icon_color", "Custom")
        kwargs.setdefault("icon_color_normal", theme.NAVY_700)
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", ("44dp", "44dp"))
        super().__init__(**kwargs)


class GoldIconButton(IconButton):
    """Primary-action variant filled with the university gold."""

    def __init__(self, **kwargs):
        kwargs.setdefault("style", "filled")
        kwargs.setdefault("md_bg_color", theme.GOLD_500)
        kwargs.setdefault("icon_color_normal", theme.NAVY_800)
        super().__init__(**kwargs)


class NavyIconButton(IconButton):
    """High-contrast variant filled with navy for use over the map."""

    def __init__(self, **kwargs):
        kwargs.setdefault("style", "filled")
        kwargs.setdefault("md_bg_color", theme.NAVY_700)
        kwargs.setdefault("icon_color_normal", theme.WHITE)
        super().__init__(**kwargs)
