"""NavU design tokens.

One place for the National University Navy-and-Gold palette, spacing scale and
typography so every screen, widget and KV file draws from the same values.

Palette rules
-------------
* Navy blue carries surfaces, text on light backgrounds and the travelled part
  of a route.
* Gold carries the active route, selected states and primary actions.
* White (and the near-white paper tones) carry the light screens and the map.
"""

# --------------------------------------------------------------------------
# Navy
# --------------------------------------------------------------------------
NAVY_900 = (0.043, 0.078, 0.161, 1)
NAVY_800 = (0.063, 0.114, 0.220, 1)
NAVY_700 = (0.082, 0.145, 0.278, 1)
NAVY_600 = (0.106, 0.192, 0.357, 1)
NAVY_500 = (0.145, 0.255, 0.451, 1)
NAVY_400 = (0.259, 0.396, 0.616, 1)
NAVY_300 = (0.478, 0.596, 0.773, 1)

# --------------------------------------------------------------------------
# Gold
# --------------------------------------------------------------------------
GOLD_700 = (0.667, 0.482, 0.078, 1)
GOLD_600 = (0.788, 0.596, 0.110, 1)
GOLD_500 = (0.929, 0.729, 0.161, 1)
GOLD_400 = (0.949, 0.796, 0.310, 1)
GOLD_300 = (0.973, 0.871, 0.561, 1)
GOLD_200 = (0.988, 0.929, 0.749, 1)

# --------------------------------------------------------------------------
# Neutrals
# --------------------------------------------------------------------------
WHITE = (1, 1, 1, 1)
PAPER = (0.976, 0.980, 0.988, 1)
PAPER_DIM = (0.949, 0.957, 0.969, 1)
LINE = (0.878, 0.894, 0.918, 1)
INK = (0.086, 0.106, 0.145, 1)
INK_SOFT = (0.376, 0.408, 0.463, 1)
INK_FAINT = (0.612, 0.639, 0.686, 1)

# --------------------------------------------------------------------------
# Functional (still inside the palette)
# --------------------------------------------------------------------------
ROUTE_ACTIVE = GOLD_500          # line ahead of the walker
ROUTE_TRAVELLED = (0.616, 0.647, 0.702, 1)
ROUTE_CASING = WHITE
USER_DOT = NAVY_600              # the "you are here" puck
USER_RING = WHITE
DESTINATION = NAVY_700
DESTINATION_INNER = GOLD_500

# Translucent helpers used by canvas instructions.
def alpha(color, value):
    """Return ``color`` with a replaced alpha component."""
    return (color[0], color[1], color[2], value)


SHADOW = alpha(NAVY_900, 0.16)
SCRIM = alpha(NAVY_900, 0.55)

# --------------------------------------------------------------------------
# Spacing / metric scale
# --------------------------------------------------------------------------
GUTTER = 16
RADIUS_SM = 10
RADIUS_MD = 16
RADIUS_LG = 22
RADIUS_XL = 28

MAP_MIN_ZOOM = 1.0
MAP_MAX_ZOOM = 4.5
MAP_ZOOM_STEP = 0.5
MAP_INITIAL_ZOOM = MAP_MIN_ZOOM
MAP_ROUTE_MAX_ZOOM = 2.6

BOTTOM_SHEET_PEEK = 168
BOTTOM_SHEET_HALF_RATIO = 0.52
BOTTOM_SHEET_FULL_RATIO = 0.90

# --------------------------------------------------------------------------
# KivyMD theme
# --------------------------------------------------------------------------
PRIMARY_PALETTE = "Gold"
THEME_STYLE = "Light"

# --------------------------------------------------------------------------
# Icon names (Material Design Icons shipped with KivyMD)
# --------------------------------------------------------------------------
ICON = {
    "start": "navigation-variant",
    "straight": "arrow-up-bold",
    "slight-left": "arrow-top-left",
    "slight-right": "arrow-top-right",
    "left": "arrow-left-bold",
    "right": "arrow-right-bold",
    "sharp-left": "arrow-left-top-bold",
    "sharp-right": "arrow-right-top-bold",
    "uturn": "backup-restore",
    "stairs-up": "stairs-up",
    "stairs-down": "stairs-down",
    "elevator": "elevator-passenger",
    "arrive": "map-marker-check",
    "floor": "layers-triple",
    "search": "magnify",
    "close": "close",
    "recenter": "crosshairs-gps",
    "compass": "compass-outline",
    "zoom-in": "plus",
    "zoom-out": "minus",
    "directions": "directions-fork",
    "walk": "walk",
    "clock": "clock-outline",
    "flag": "flag-checkered",
    "arrow-back": "arrow-left",
}
