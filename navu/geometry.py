"""Planar geometry helpers used by the routing and map layers.

All coordinates are normalized plan positions: ``(x, y)`` where both components
are ``0.0..1.0`` across the floor plan image. ``x`` grows east and ``y`` grows
north, which matches Kivy's screen axis so no flipping is needed.
"""

from math import atan2, degrees, hypot

# Turn thresholds in degrees. Anything below STRAIGHT_LIMIT is treated as
# "carry straight on" so tiny corridor jitter does not produce a maneuver.
STRAIGHT_LIMIT = 22.0
SLIGHT_LIMIT = 50.0
SHARP_TURN_LIMIT = 100.0
UTURN_LIMIT = 130.0

TURN_KINDS = (
    "straight",
    "slight-left",
    "slight-right",
    "left",
    "right",
    "sharp-left",
    "sharp-right",
    "uturn",
)


def bearing(origin, target):
    """Compass bearing in degrees from ``origin`` to ``target``.

    ``0`` is north (up on the plan), ``90`` is east (right).
    """
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    return degrees(atan2(dx, dy)) % 360.0


def angle_delta(first, second):
    """Signed shortest rotation from ``first`` to ``second`` in degrees.

    Positive means a clockwise (right) turn.
    """
    difference = (second - first + 180.0) % 360.0 - 180.0
    return difference


def classify_turn(delta):
    """Map a signed turn angle to one of :data:`TURN_KINDS`."""
    magnitude = abs(delta)
    if magnitude < STRAIGHT_LIMIT:
        return "straight"
    if magnitude >= UTURN_LIMIT:
        return "uturn"
    direction = "right" if delta > 0 else "left"
    if magnitude < SLIGHT_LIMIT:
        return f"slight-{direction}"
    return direction


def turn_arrow_kind(delta):
    """Like :func:`classify_turn` but promotes hard turns to sharp turns."""
    kind = classify_turn(delta)
    if kind in ("left", "right") and abs(delta) >= SHARP_TURN_LIMIT:
        return f"sharp-{kind}"
    return kind


def interpolate(origin, target, fraction):
    """Linear interpolation between two plan points."""
    return (
        origin[0] + (target[0] - origin[0]) * fraction,
        origin[1] + (target[1] - origin[1]) * fraction,
    )


def polyline_length(points):
    """Total length of a polyline in plan units."""
    return sum(
        point_distance(first, second)
        for first, second in zip(points, points[1:])
    )


def point_distance(origin, target):
    """Euclidean distance between two plan points."""
    return hypot(target[0] - origin[0], target[1] - origin[1])


def point_at_fraction(points, fraction):
    """Walk ``fraction`` (0..1) of a polyline's length and return a snapshot.

    Returns ``(point, segment_index, segment_fraction)``. When the polyline has
    fewer than two points the first point is returned unchanged.
    """
    if not points:
        return (0.0, 0.0), 0, 0.0
    if len(points) < 2:
        return tuple(points[0]), 0, 0.0

    fraction = min(1.0, max(0.0, fraction))
    lengths = [
        point_distance(first, second)
        for first, second in zip(points, points[1:])
    ]
    total = sum(lengths)
    if total <= 0:
        return tuple(points[0]), 0, 0.0

    travelled = total * fraction
    for index, length in enumerate(lengths):
        if travelled <= length or index == len(lengths) - 1:
            local = 0.0 if length <= 0 else min(1.0, travelled / length)
            return (
                interpolate(points[index], points[index + 1], local),
                index,
                local,
            )
        travelled -= length
    return tuple(points[-1]), len(lengths) - 1, 1.0
