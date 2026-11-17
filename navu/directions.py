"""Turn-by-turn direction building and live navigation progress.

The route graph returns a list of :class:`~navu.routing.RouteNode`. This module
turns that list into the kind of maneuver list a maps app shows: a start step,
a small number of meaningful turns, any floor changes, and an arrival step, each
with the distance the walker covers before reaching the next one.
"""

from dataclasses import dataclass, field

from .geometry import angle_delta, bearing, interpolate, turn_arrow_kind
from .routing import (
    FLOOR_SHORT_NAMES,
    NODES,
    PROVISIONAL_STAIR_WALK_METERS,
    RouteNode,
    WALKING_SPEED_METERS_PER_SECOND,
    edge_weight,
    floor_plan_distance_meters,
    metered_spans,
    vertical_direction,
    vertical_kind_between,
)
from .theme import ICON

MANEUVER_ICONS = {
    "start": ICON["start"],
    "straight": ICON["straight"],
    "slight-left": ICON["slight-left"],
    "slight-right": ICON["slight-right"],
    "left": ICON["left"],
    "right": ICON["right"],
    "sharp-left": ICON["sharp-left"],
    "sharp-right": ICON["sharp-right"],
    "uturn": ICON["uturn"],
    "stairs": ICON["stairs-up"],
    "elevator": ICON["elevator"],
    "arrive": ICON["arrive"],
}

MANEUVER_TITLES = {
    "start": "Start",
    "straight": "Continue straight",
    "slight-left": "Bear left",
    "slight-right": "Bear right",
    "left": "Turn left",
    "right": "Turn right",
    "sharp-left": "Turn sharply left",
    "sharp-right": "Turn sharply right",
    "uturn": "Make a U-turn",
    "arrive": "Arrive at your destination",
}

_ORIGIN_TOLERANCE_METERS = 0.05


def floor_name(floor: str) -> str:
    """Short floor label used on the map, such as ``"3F"``."""
    return FLOOR_SHORT_NAMES.get(floor, floor.upper())


def floor_spoken_name(floor: str) -> str:
    """Floor name as it reads in a spoken instruction."""
    if floor in ("lower_ground", "LG"):
        return "the Lower Ground floor"
    if floor.isdigit() and len(floor) == 1:
        suffix = {"1": "st", "2": "nd", "3": "rd"}.get(floor, "th")
        return f"the {floor}{suffix} floor"
    return f"the {floor_name(floor)} level"


@dataclass(frozen=True)
class RouteStep:
    """A single maneuver in a route."""

    index: int
    kind: str
    title: str
    instruction: str
    corridor: str
    icon: str
    distance_meters: float
    cumulative_meters: float
    floor: str
    position: tuple[float, float]
    node_id: str
    is_vertical: bool = False

    @property
    def floor_label(self) -> str:
        return floor_name(self.floor)


def _maneuver_at(
    previous: tuple[float, float],
    current: tuple[float, float],
    following: tuple[float, float],
) -> str:
    """Turn kind for a bend at ``current`` between two corridor segments."""
    incoming = bearing(previous, current)
    outgoing = bearing(current, following)
    return turn_arrow_kind(angle_delta(incoming, outgoing))


def _corridor_name(node: RouteNode | None) -> str:
    if node is None:
        return "the corridor"
    if node.label == "Nearest corridor":
        return "the corridor"
    return node.label


def _start_corridor(nodes: list[RouteNode | None]) -> str:
    """Name the corridor the walker heads into from the start point."""
    for node in nodes:
        if node is not None and node.label not in (
            "Nearest corridor",
            "Main Entrance",
        ):
            return _corridor_name(node)
    return "the corridor"


def _vertical_instruction(
    connector: str,
    direction: str,
    target_floor: str,
) -> str:
    """Readable floor-change instruction."""
    destination = floor_spoken_name(target_floor)
    if connector == "elevator":
        return f"Take the elevator {direction} to {destination}"
    return f"Take the stairs {direction} to {destination}"


def _build_maneuvers(
    positions: list[tuple[float, float]],
    floors: list[str],
    nodes: list[RouteNode | None],
    last_index: int,
) -> list[dict]:
    """Decide where the walker is told to do something.

    Every entry records ``walk_start``: the position index where that
    instruction begins, so the step list meters each metre exactly once.
    """
    maneuvers: list[dict] = [
        {
            "kind": "start",
            "node": nodes[0],
            "display": 0,
            "walk_start": 0,
            "vertical_end": None,
        }
    ]
    cursor = 0
    index = 1
    while index <= last_index:
        if floors[index] != floors[index - 1]:
            departure = index - 1
            maneuvers.append(
                {
                    "kind": "vertical",
                    "node": nodes[index],
                    "display": index,
                    "walk_start": departure,
                    "vertical_end": index,
                }
            )
            cursor = index
            index += 1
            continue

        if index == last_index:
            maneuvers.append(
                {
                    "kind": "arrive",
                    "node": nodes[index],
                    "display": index,
                    "walk_start": cursor,
                    "vertical_end": None,
                }
            )
            cursor = index
            index += 1
            continue

        if floors[index] != floors[index + 1]:
            # The next leg leaves this floor, so this point is simply where the
            # connected instruction onwards belongs; the walk to it is already
            # metered by the step in progress.
            index += 1
            continue

        kind = _maneuver_at(
            positions[index - 1], positions[index], positions[index + 1]
        )
        if kind == "straight":
            # Carry straight on inside the instruction already in progress
            # rather than adding a step for every bend in the corridor. The
            # cursor stays put so the whole stretch is metered once.
            index += 1
            continue

        maneuvers.append(
            {
                "kind": kind,
                "node": nodes[index],
                "display": index,
                "walk_start": cursor,
                "vertical_end": None,
            }
        )
        cursor = index
        index += 1

    if maneuvers[-1]["kind"] != "arrive":
        maneuvers.append(
            {
                "kind": "arrive",
                "node": nodes[-1],
                "display": last_index,
                "walk_start": cursor,
                "vertical_end": None,
            }
        )
    return maneuvers


def _walk_end(maneuvers: list[dict], order: int, last_index: int) -> int:
    """Position index at which the instruction ``order`` stops applying."""
    vertical_end = maneuvers[order]["vertical_end"]
    if vertical_end is not None:
        return vertical_end
    if order + 1 < len(maneuvers):
        return maneuvers[order + 1]["walk_start"]
    return last_index


def _describe_maneuver(
    kind: str,
    node: RouteNode | None,
    floors: list[str],
    nodes: list[RouteNode | None],
    display: int,
    destination_label: str,
) -> tuple[str, str, str, str, str, bool]:
    """Text and icon for one maneuver.

    Returns ``(title, instruction, corridor, icon, resolved_kind, vertical)``.
    """
    floor = floors[display]

    if kind == "vertical":
        previous_node = nodes[display - 1] if display else None
        connector = vertical_kind_between(
            previous_node.node_id if previous_node else "",
            node.node_id if node else "",
        )
        direction = vertical_direction(floors[display - 1], floor)
        verb = "elevator" if connector == "elevator" else "stairs"
        title = f"Take the {verb} {direction}"
        instruction = _vertical_instruction(connector, direction, floor)
        corridor = f"to {floor_name(floor)}"
        icon = MANEUVER_ICONS.get(connector, ICON["stairs-up"])
        return title, instruction, corridor, icon, connector, True

    if kind == "arrive":
        return (
            MANEUVER_TITLES["arrive"],
            f"Arrive at {destination_label}",
            floor_name(floor),
            MANEUVER_ICONS["arrive"],
            "arrive",
            False,
        )

    if kind == "start":
        corridor = _start_corridor(nodes)
        return (
            MANEUVER_TITLES["start"],
            f"Head along {corridor}",
            corridor,
            MANEUVER_ICONS["start"],
            "start",
            False,
        )

    corridor = _corridor_name(node)
    title = MANEUVER_TITLES.get(kind, "Continue")
    return (
        title,
        f"{title} onto {corridor}",
        corridor,
        MANEUVER_ICONS.get(kind, ICON["straight"]),
        kind,
        False,
    )


def build_steps(
    route: list[RouteNode],
    origin_position: tuple[float, float] | None = None,
    origin_floor: str = "",
    destination_label: str = "your destination",
) -> list[RouteStep]:
    """Turn ``route`` into an ordered maneuver list.

    Consecutive straight segments are merged. Each floor change stays a separate
    instruction so the map can follow the walker floor by floor.
    """
    if not route:
        return []

    # Only prepend the tapped origin when it genuinely sits before the first
    # route node; otherwise that node would be counted twice.
    has_origin = bool(
        origin_position
        and origin_floor == route[0].floor
        and floor_plan_distance_meters(
            tuple(origin_position), route[0].position, origin_floor
        )
        > _ORIGIN_TOLERANCE_METERS
    )

    positions: list[tuple[float, float]] = []
    floors: list[str] = []
    nodes: list[RouteNode | None] = []
    if has_origin:
        positions.append(tuple(origin_position))
        floors.append(origin_floor)
        nodes.append(None)
    for node in route:
        positions.append(tuple(node.position))
        floors.append(node.floor)
        nodes.append(node)

    legs = [0.0]
    for index in range(1, len(positions)):
        if floors[index] == floors[index - 1]:
            previous_node = nodes[index - 1]
            current_node = nodes[index]
            if previous_node is not None and current_node is not None:
                meters = edge_weight(previous_node.node_id, current_node.node_id)
                if meters <= 0:
                    raise ValueError(
                        "A route contains consecutive same-floor nodes without "
                        f"a graph edge: {previous_node.node_id!r} to "
                        f"{current_node.node_id!r}"
                    )
            else:
                meters = floor_plan_distance_meters(
                    positions[index - 1], positions[index], floors[index]
                )
            legs.append(meters)
        else:
            first_node = nodes[index - 1]
            second_node = nodes[index]
            connector_distance = (
                edge_weight(first_node.node_id, second_node.node_id)
                if first_node is not None and second_node is not None
                else 0.0
            )
            legs.append(connector_distance or PROVISIONAL_STAIR_WALK_METERS)

    last_index = len(positions) - 1
    maneuvers = _build_maneuvers(positions, floors, nodes, last_index)
    total = sum(legs)

    steps: list[RouteStep] = []
    for order, maneuver in enumerate(maneuvers):
        display = maneuver["display"]
        walk_start = maneuver["walk_start"]
        walk_end = _walk_end(maneuvers, order, last_index)

        title, instruction, corridor, icon, resolved_kind, is_vertical = (
            _describe_maneuver(
                maneuver["kind"],
                maneuver["node"],
                floors,
                nodes,
                display,
                destination_label,
            )
        )
        node = maneuver["node"]

        steps.append(
            RouteStep(
                index=order,
                kind=resolved_kind,
                title=title,
                instruction=instruction,
                corridor=corridor,
                icon=icon,
                distance_meters=sum(legs[walk_start + 1 : walk_end + 1]),
                cumulative_meters=sum(legs[: walk_end + 1]),
                floor=floors[display],
                position=positions[display],
                node_id=node.node_id if node else "",
                is_vertical=is_vertical,
            )
        )

    if steps:
        last = steps[-1]
        steps[-1] = RouteStep(
            index=last.index,
            kind=last.kind,
            title=last.title,
            instruction=last.instruction,
            corridor=last.corridor,
            icon=last.icon,
            distance_meters=steps[-1].distance_meters,
            cumulative_meters=total,
            floor=last.floor,
            position=last.position,
            node_id=last.node_id,
            is_vertical=last.is_vertical,
        )
    return steps


def format_distance(meters: float) -> str:
    """Short distance label, the way a maps app writes it.

    Indoor legs are short, so the rounding stays fine-grained: one decimal
    below 10 m and whole metres below 100 m.
    """
    if meters <= 0:
        return "0 m"
    if meters < 10:
        return f"{meters:.1f} m"
    if meters < 100:
        return f"{round(meters)} m"
    if meters < 1000:
        return f"{round(meters / 10) * 10} m"
    return f"{meters / 1000:.1f} km"


def format_duration(seconds: float) -> str:
    """Short duration label such as ``"4 min"`` or ``"1 hr 5 min"``."""
    minutes = max(1, round(seconds / 60)) if seconds > 0 else 0
    if minutes <= 0:
        return "0 min"
    if minutes < 60:
        return f"{minutes} min"
    hours, remaining = divmod(minutes, 60)
    if remaining:
        return f"{hours} hr {remaining} min"
    return f"{hours} hr"


def walk_seconds(meters: float) -> float:
    """Estimated walking time for a distance."""
    return meters / WALKING_SPEED_METERS_PER_SECOND


@dataclass
class RouteSession:
    """Live state for one navigation run.

    Progress is measured in metres travelled from the start of the route. The
    session resolves that into the active step, the distance to it and the
    remaining totals, which is everything the navigation banner needs.
    """

    route: list[RouteNode] = field(default_factory=list)
    steps: list[RouteStep] = field(default_factory=list)
    total_meters: float = 0.0
    travelled_meters: float = 0.0

    @property
    def remaining_meters(self) -> float:
        return max(0.0, self.total_meters - self.travelled_meters)

    @property
    def remaining_seconds(self) -> float:
        return walk_seconds(self.remaining_meters)

    @property
    def progress(self) -> float:
        if self.total_meters <= 0:
            return 0.0
        return min(1.0, self.travelled_meters / self.total_meters)

    @property
    def active_step_index(self) -> int:
        """Index of the maneuver the walker is currently following."""
        if not self.steps:
            return -1
        for step in self.steps:
            if step.cumulative_meters > self.travelled_meters + 0.01:
                return step.index
        return len(self.steps) - 1

    @property
    def active_step(self) -> RouteStep | None:
        index = self.active_step_index
        if 0 <= index < len(self.steps):
            return self.steps[index]
        return self.steps[-1] if self.steps else None

    @property
    def up_next_step(self) -> RouteStep | None:
        """The maneuver after the current one, shown as a preview."""
        index = self.active_step_index
        if 0 <= index + 1 < len(self.steps):
            return self.steps[index + 1]
        return None

    @property
    def distance_to_maneuver(self) -> float:
        """Metres left before the next maneuver point."""
        step = self.active_step
        if step is None:
            return 0.0
        return max(0.0, step.cumulative_meters - self.travelled_meters)

    @property
    def has_arrived(self) -> bool:
        return bool(self.steps) and self.remaining_meters <= 0.5


def point_at_distance(
    route: list[RouteNode],
    travelled_meters: float,
    origin_position: tuple[float, float] | None = None,
    origin_floor: str = "",
) -> tuple[tuple[float, float], str, float, bool]:
    """Resolve a travelled distance into a position on the plan.

    Returns ``(position, floor, heading_degrees, arrived)``. A vertical span has
    no meaningful geometry between two different plans, so the walker is held at
    the arrival point of that span rather than sliding between floors.
    """
    spans = metered_spans(route, origin_position, origin_floor)
    if not spans:
        if route:
            return tuple(route[0].position), route[0].floor, 0.0, True
        return (0.0, 0.0), "", 0.0, False

    remaining = max(0.0, travelled_meters)
    for span in spans:
        if span.meters <= 0:
            continue
        if remaining <= span.meters:
            if span.is_vertical:
                return span.start, span.start_floor, 0.0, False
            fraction = remaining / span.meters
            return (
                interpolate(span.start, span.target, fraction),
                span.start_floor,
                bearing(span.start, span.target),
                False,
            )
        remaining -= span.meters

    final = spans[-1]
    heading = 0.0 if final.is_vertical else bearing(final.start, final.target)
    return final.target, final.end_floor, heading, True


def route_length_meters(
    route: list[RouteNode],
    origin_position: tuple[float, float] | None = None,
    origin_floor: str = "",
) -> float:
    """Total walking distance of a route, including any tapped-origin offset."""
    return sum(
        span.meters
        for span in metered_spans(route, origin_position, origin_floor)
    )


def floor_of_node(node_id: str) -> str:
    """Floor of a node id, or ``""`` when the node is unknown."""
    node = NODES.get(node_id)
    return node.floor if node else ""
