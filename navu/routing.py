"""Graph-backed indoor routing for the SVG floor plans."""

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
import json
import math
import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOORPLANS_DIR = os.path.join(
    BASE_DIR, "assets", "floorplans", "navu_floorplans_v3", "navu", "app"
)
GRAPH_PATH = os.path.join(FLOORPLANS_DIR, "route_graph.json")
DEFAULT_TRAVEL_PREFERENCE = "elevator"
START_CORRIDOR_LIMIT_UNITS = 60.0
WALKING_SPEED_METERS_PER_SECOND = 1.2
PROVISIONAL_STAIR_WALK_METERS = 8.0

_FLOOR_ALIASES = {
    "lower_ground": "LG",
    "lg": "LG",
}


@dataclass(frozen=True)
class RouteNode:
    node_id: str
    floor: str
    label: str
    position: tuple[float, float]
    node_type: str = "corridor"
    room_id: str = ""


@dataclass(frozen=True)
class RouteSpan:
    """One metered leg of a route."""

    start: tuple[float, float]
    target: tuple[float, float]
    start_floor: str
    end_floor: str
    meters: float

    @property
    def is_vertical(self) -> bool:
        return self.start_floor != self.end_floor


@dataclass(frozen=True)
class RouteRoom:
    room_id: str
    floor: str
    name: str
    room_no: str
    room_type: str
    rect: tuple[float, float, float, float]
    door_nodes: tuple[str, ...]
    open_space: bool
    needs_review: bool


@dataclass(frozen=True)
class GraphEdge:
    a: str
    b: str
    meters: float
    kind: str


@dataclass(frozen=True)
class ResolvedStart:
    floor: str
    node: RouteNode
    tapped_position: tuple[float, float]
    room_id: str = ""


@dataclass(frozen=True)
class RoutePlan:
    start: ResolvedStart
    destination: RouteRoom
    nodes: tuple[RouteNode, ...]
    meters: float


class RoutingDataError(ValueError):
    """Raised when the routing graph is missing or internally inconsistent."""


class InvalidStartLocation(ValueError):
    """Raised when a selected floor or tapped start point is invalid."""


class RouteNotFoundError(ValueError):
    """Raised when valid endpoints have no route under the chosen options."""


def _number(value, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RoutingDataError(f"{context} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise RoutingDataError(f"{context} must be finite")
    return result


def _load_graph(path: str):
    try:
        with open(path, "r", encoding="utf-8") as graph_file:
            return json.load(graph_file)
    except OSError as error:
        raise RoutingDataError(f"Cannot read routing graph at {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise RoutingDataError(f"Invalid routing graph JSON at {path}: {error}") from error


def _build_graph(data):
    if not isinstance(data, dict):
        raise RoutingDataError("Routing graph must be a JSON object")
    level_order = data.get("level_order")
    levels_data = data.get("levels")
    if not isinstance(level_order, list) or not level_order:
        raise RoutingDataError("Routing graph must define level_order")
    if not isinstance(levels_data, dict):
        raise RoutingDataError("Routing graph must define levels")

    floor_order = {}
    levels = {}
    nodes = {}
    rooms = {}
    adjacency = {}
    edges = {}
    floorplan_paths = {}

    def register_edge(edge_data, floor=None):
        first_id = edge_data.get("a")
        second_id = edge_data.get("b")
        if first_id not in nodes or second_id not in nodes:
            raise RoutingDataError(
                f"Edge references unknown nodes: {first_id!r}, {second_id!r}"
            )
        if floor is not None and (
            nodes[first_id].floor != floor or nodes[second_id].floor != floor
        ):
            raise RoutingDataError(
                f"Floor edge endpoints must both belong to {floor}: "
                f"{first_id!r}, {second_id!r}"
            )
        meters = _number(edge_data.get("meters"), "Edge meters")
        kind = edge_data.get("kind")
        if meters <= 0 or not isinstance(kind, str) or not kind:
            raise RoutingDataError(
                f"Edge {first_id!r} to {second_id!r} needs positive meters and a kind"
            )
        key = frozenset((first_id, second_id))
        if key in edges:
            raise RoutingDataError(
                f"Duplicate edge between {first_id!r} and {second_id!r}"
            )
        edge = GraphEdge(first_id, second_id, meters, kind)
        edges[key] = edge
        adjacency[first_id].append((second_id, edge))
        adjacency[second_id].append((first_id, edge))

    for index, floor in enumerate(level_order):
        if not isinstance(floor, str) or floor not in levels_data:
            raise RoutingDataError(f"Unknown floor in level_order: {floor!r}")
        floor_data = levels_data[floor]
        floor_order[floor] = index
        width = _number(floor_data.get("width"), f"{floor} width")
        height = _number(floor_data.get("height"), f"{floor} height")
        meters_per_unit = _number(
            floor_data.get("meters_per_unit"), f"{floor} meters_per_unit"
        )
        if width <= 0 or height <= 0 or meters_per_unit <= 0:
            raise RoutingDataError(f"{floor} dimensions and scale must be positive")
        levels[floor] = {
            "title": floor_data.get("title", floor),
            "width": width,
            "height": height,
            "meters_per_unit": meters_per_unit,
            "svg": floor_data.get("svg", ""),
        }
        svg_name = levels[floor]["svg"]
        if not isinstance(svg_name, str) or os.path.basename(svg_name) != svg_name:
            raise RoutingDataError(f"{floor} has an invalid SVG filename")
        svg_path = os.path.join(FLOORPLANS_DIR, svg_name)
        if not os.path.isfile(svg_path):
            raise RoutingDataError(f"Floor plan is missing: {svg_path}")
        floorplan_paths[floor] = svg_path

        floor_nodes = floor_data.get("nodes")
        if not isinstance(floor_nodes, list):
            raise RoutingDataError(f"{floor} must define a nodes list")
        for item in floor_nodes:
            node_id = item.get("id")
            node_type = item.get("type")
            if not isinstance(node_id, str) or not node_id or node_id in nodes:
                raise RoutingDataError(f"Invalid or duplicate node id: {node_id!r}")
            if node_type not in ("corridor", "door"):
                raise RoutingDataError(f"Unknown node type for {node_id!r}: {node_type!r}")
            x = _number(item.get("x"), f"{node_id} x")
            y = _number(item.get("y"), f"{node_id} y")
            if not (0 <= x <= width and 0 <= y <= height):
                raise RoutingDataError(f"Node {node_id!r} is outside its floor plan")
            room_id = item.get("room", "")
            if node_type == "door" and not isinstance(room_id, str):
                raise RoutingDataError(f"Door node {node_id!r} must identify its room")
            label = node_id.split(":", 1)[-1]
            nodes[node_id] = RouteNode(
                node_id=node_id,
                floor=floor,
                label=label,
                position=(x, y),
                node_type=node_type,
                room_id=room_id,
            )
            adjacency[node_id] = []

        floor_edges = floor_data.get("edges")
        if not isinstance(floor_edges, list):
            raise RoutingDataError(f"{floor} must define an edges list")
        for item in floor_edges:
            register_edge(item, floor)

        floor_rooms = floor_data.get("rooms")
        if not isinstance(floor_rooms, list):
            raise RoutingDataError(f"{floor} must define a rooms list")
        for item in floor_rooms:
            room_id = item.get("id")
            rect = item.get("rect")
            door_nodes = item.get("door_nodes")
            if (
                not isinstance(room_id, str)
                or not room_id
                or room_id in rooms
                or not isinstance(rect, list)
                or len(rect) != 4
                or not isinstance(door_nodes, list)
                or not isinstance(item.get("open_space"), bool)
                or not isinstance(item.get("needs_review"), bool)
            ):
                raise RoutingDataError(f"Invalid room record: {room_id!r}")
            bounds = tuple(_number(value, f"{room_id} rect") for value in rect)
            if bounds[0] > bounds[2] or bounds[1] > bounds[3]:
                raise RoutingDataError(f"Room {room_id!r} has invalid rectangle bounds")
            for door_id in door_nodes:
                door = nodes.get(door_id)
                if door is None or door.node_type != "door" or door.room_id != room_id:
                    raise RoutingDataError(
                        f"Room {room_id!r} has an invalid door node: {door_id!r}"
                    )
            room_no = item.get("room_no")
            rooms[room_id] = RouteRoom(
                room_id=room_id,
                floor=floor,
                name=str(item.get("name") or room_id),
                room_no="" if room_no is None else str(room_no),
                room_type=str(item.get("type") or ""),
                rect=bounds,
                door_nodes=tuple(door_nodes),
                open_space=item["open_space"],
                needs_review=item["needs_review"],
            )

    vertical_links = data.get("vertical_links")
    if not isinstance(vertical_links, list):
        raise RoutingDataError("Routing graph must define vertical_links")
    for item in vertical_links:
        first_id = item.get("a")
        second_id = item.get("b")
        if first_id not in nodes or second_id not in nodes:
            raise RoutingDataError(
                f"Vertical link references unknown nodes: {first_id!r}, {second_id!r}"
            )
        if nodes[first_id].floor == nodes[second_id].floor:
            raise RoutingDataError(
                f"Vertical link must join different floors: {first_id!r}, {second_id!r}"
            )
        if item.get("kind") not in ("stairs", "elevator"):
            raise RoutingDataError(
                f"Unknown vertical link kind: {item.get('kind')!r}"
            )
        register_edge(item)

    for room in rooms.values():
        if not room.door_nodes:
            raise RoutingDataError(f"Room {room.room_id!r} has no door nodes")

    return (
        tuple(level_order),
        floor_order,
        levels,
        floorplan_paths,
        nodes,
        rooms,
        adjacency,
        edges,
    )


GRAPH = _load_graph(GRAPH_PATH)
(
    FLOORS,
    FLOOR_ORDER,
    LEVELS,
    FLOORPLAN_PATHS,
    NODES,
    ROOMS_BY_ID,
    _ADJACENCY,
    _EDGE_BY_PAIR,
) = _build_graph(GRAPH)

FLOOR_SHORT_NAMES = {
    floor: ("LG" if floor == "LG" else f"{floor}F")
    for floor in FLOORS
}
FLOOR_PLAN_METERS_PER_AXIS = {
    floor: (
        LEVELS[floor]["width"] * LEVELS[floor]["meters_per_unit"],
        LEVELS[floor]["height"] * LEVELS[floor]["meters_per_unit"],
    )
    for floor in FLOORS
}
PROVISIONAL_FLOOR_WIDTH_METERS = max(
    axis[0] for axis in FLOOR_PLAN_METERS_PER_AXIS.values()
)

DESTINATION_NODES = {
    room.room_id: room.door_nodes[0] for room in ROOMS_BY_ID.values()
}
_room_numbers = {}
for _room in ROOMS_BY_ID.values():
    if _room.room_no:
        _room_numbers.setdefault(_room.room_no, []).append(_room.room_id)
for _room_no, _room_ids in _room_numbers.items():
    if len(_room_ids) == 1:
        DESTINATION_NODES[_room_no] = ROOMS_BY_ID[_room_ids[0]].door_nodes[0]

def normalize_floor(floor: str) -> str:
    """Normalize existing UI floor aliases to the graph's floor identifiers."""
    normalized = _FLOOR_ALIASES.get(str(floor).casefold(), str(floor))
    if normalized not in LEVELS:
        raise InvalidStartLocation(f"Floor {floor!r} is not in the routing graph")
    return normalized


def room_by_id(room_id: str) -> RouteRoom:
    """Return a room by graph id or an unambiguous room number."""
    room = ROOMS_BY_ID.get(room_id)
    if room is not None:
        return room
    matches = [item for item in ROOMS_BY_ID.values() if item.room_no == str(room_id)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"Room number {room_id!r} is ambiguous")
    raise ValueError(f"Unknown destination room: {room_id!r}")


def floor_plan_distance_meters(
    first: tuple[float, float],
    second: tuple[float, float],
    floor: str,
) -> float:
    """Return straight-line distance between two points on one plan."""
    graph_floor = normalize_floor(floor)
    scale = LEVELS[graph_floor]["meters_per_unit"]
    return math.hypot(second[0] - first[0], second[1] - first[1]) * scale


def plan_distance_meters(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    """Compatibility helper using the first floor's calibrated graph scale."""
    return floor_plan_distance_meters(first, second, FLOORS[0])


def resolve_start(
    floor: str,
    position: tuple[float, float],
) -> ResolvedStart:
    """Resolve a tap to a mapped room door or nearby node on that floor."""
    graph_floor = normalize_floor(floor)
    if (
        not isinstance(position, (tuple, list))
        or len(position) != 2
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in position
        )
    ):
        raise InvalidStartLocation("Tap inside the plan near a hallway")
    x, y = float(position[0]), float(position[1])
    level = LEVELS[graph_floor]
    if not (0 <= x <= level["width"] and 0 <= y <= level["height"]):
        raise InvalidStartLocation("Tap inside the plan near a hallway")

    floor_nodes = [node for node in NODES.values() if node.floor == graph_floor]
    nearest_node = min(
        floor_nodes,
        key=lambda node: math.hypot(node.position[0] - x, node.position[1] - y),
        default=None,
    )
    if nearest_node is not None and math.hypot(
        nearest_node.position[0] - x, nearest_node.position[1] - y
    ) <= 0.01:
        return ResolvedStart(
            graph_floor,
            nearest_node,
            (x, y),
            nearest_node.room_id if nearest_node.node_type == "door" else "",
        )

    for room in ROOMS_BY_ID.values():
        if room.floor != graph_floor:
            continue
        left, top, right, bottom = room.rect
        if left <= x <= right and top <= y <= bottom:
            door = min(
                (NODES[node_id] for node_id in room.door_nodes),
                key=lambda node: math.hypot(
                    node.position[0] - x, node.position[1] - y
                ),
            )
            return ResolvedStart(graph_floor, door, (x, y), room.room_id)

    if (
        nearest_node is None
        or math.hypot(nearest_node.position[0] - x, nearest_node.position[1] - y)
        > START_CORRIDOR_LIMIT_UNITS
    ):
        raise InvalidStartLocation("Tap inside the plan near a hallway")
    return ResolvedStart(graph_floor, nearest_node, (x, y))


def nearest_node(floor: str, position: tuple[float, float]) -> RouteNode | None:
    """Compatibility adapter returning the resolved node for an accepted tap."""
    try:
        return resolve_start(floor, position).node
    except InvalidStartLocation:
        return None


def _route_goals(destination_id: str) -> set[str]:
    if destination_id in NODES:
        return {destination_id}
    return set(room_by_id(destination_id).door_nodes)


def shortest_path(
    start_node_id: str,
    destination_id: str,
    preference: str = "any",
    *,
    accessible: bool = False,
    no_elevators: bool = False,
) -> list[RouteNode] | None:
    """Find the least-meter route using only supplied graph edges."""
    if start_node_id not in NODES:
        raise ValueError(f"Unknown start node: {start_node_id!r}")
    goals = _route_goals(destination_id)
    if not goals:
        return None

    if preference not in ("any", "stairs", "elevator", "accessible", "no_elevators"):
        raise ValueError(f"Unknown route preference: {preference!r}")
    if preference in ("elevator", "accessible"):
        accessible = True
    if preference in ("stairs", "no_elevators"):
        no_elevators = True

    distances = {start_node_id: 0.0}
    previous = {}
    tie_breaker = count()
    queue = [(0.0, next(tie_breaker), start_node_id)]
    goal_id = None

    while queue:
        distance, _, node_id = heappop(queue)
        if distance > distances.get(node_id, math.inf):
            continue
        if node_id in goals:
            goal_id = node_id
            break
        for neighbor_id, edge in _ADJACENCY[node_id]:
            if accessible and edge.kind == "stairs":
                continue
            if no_elevators and edge.kind == "elevator":
                continue
            candidate = distance + edge.meters
            if candidate < distances.get(neighbor_id, math.inf):
                distances[neighbor_id] = candidate
                previous[neighbor_id] = node_id
                heappush(queue, (candidate, next(tie_breaker), neighbor_id))

    if goal_id is None:
        return None

    route_ids = [goal_id]
    while route_ids[-1] != start_node_id:
        route_ids.append(previous[route_ids[-1]])
    route_ids.reverse()
    return [NODES[node_id] for node_id in route_ids]


def calculate_route(
    floor: str,
    position: tuple[float, float],
    destination_room_id: str,
    *,
    accessible: bool = False,
    no_elevators: bool = False,
) -> RoutePlan:
    """Calculate a multi-floor route from the user's selected floor and tap."""
    start = resolve_start(floor, position)
    destination = room_by_id(destination_room_id)
    route = shortest_path(
        start.node.node_id,
        destination.room_id,
        accessible=accessible,
        no_elevators=no_elevators,
    )
    if route is None:
        raise RouteNotFoundError(
            f"No route from {start.node.node_id!r} to {destination.room_id!r} "
            "with the selected travel options"
        )
    return RoutePlan(start, destination, tuple(route), route_distance_meters(route))


def route_between_rooms(
    start_room_id: str,
    destination_room_id: str,
    *,
    accessible: bool = False,
    no_elevators: bool = False,
) -> list[RouteNode] | None:
    """Route from the cheapest source-room door to any destination door node."""
    start_room = room_by_id(start_room_id)
    candidates = [
        route
        for door_id in start_room.door_nodes
        if (
            route := shortest_path(
                door_id,
                destination_room_id,
                accessible=accessible,
                no_elevators=no_elevators,
            )
        )
    ]
    return min(candidates, key=route_distance_meters) if candidates else None


def route_distance_meters(
    route: list[RouteNode] | tuple[RouteNode, ...],
    origin_position: tuple[float, float] | None = None,
    origin_floor: str = "",
) -> float:
    """Sum graph edge weights and, optionally, a same-floor origin lead-in."""
    total = 0.0
    if route and origin_position:
        if normalize_floor(origin_floor) != route[0].floor:
            raise ValueError("Origin and first route node must be on the same floor")
        total += floor_plan_distance_meters(
            origin_position, route[0].position, route[0].floor
        )
    for first, second in zip(route, route[1:]):
        weight = edge_weight(first.node_id, second.node_id)
        if weight <= 0:
            raise ValueError(
                f"Route contains a non-edge segment: {first.node_id!r} to {second.node_id!r}"
            )
        total += weight
    return total


def edge_weight(first_id: str, second_id: str) -> float:
    """Return the supplied weight for an edge, or zero if the nodes are unconnected."""
    edge = _EDGE_BY_PAIR.get(frozenset((first_id, second_id)))
    return edge.meters if edge is not None else 0.0


def edge_kind(first_id: str, second_id: str) -> str | None:
    """Return the source graph's edge kind for a connected node pair."""
    edge = _EDGE_BY_PAIR.get(frozenset((first_id, second_id)))
    return edge.kind if edge is not None else None


def is_vertical_step(first_id: str, second_id: str) -> bool:
    first = NODES.get(first_id)
    second = NODES.get(second_id)
    return bool(first and second and first.floor != second.floor)


def vertical_kind_between(first_id: str, second_id: str) -> str:
    kind = edge_kind(first_id, second_id)
    if kind not in ("stairs", "elevator"):
        raise ValueError(f"{first_id!r} and {second_id!r} are not vertically linked")
    return kind


def vertical_direction(first_floor: str, second_floor: str) -> str:
    first = normalize_floor(first_floor)
    second = normalize_floor(second_floor)
    return "up" if FLOOR_ORDER[second] > FLOOR_ORDER[first] else "down"


def vertical_kind(node_id: str) -> str:
    for _, edge in _ADJACENCY.get(node_id, ()):
        if edge.kind in ("stairs", "elevator"):
            return edge.kind
    return "stairs"


def metered_spans(
    route: list[RouteNode] | tuple[RouteNode, ...],
    origin_position: tuple[float, float] | None = None,
    origin_floor: str = "",
) -> list[RouteSpan]:
    """Build weighted spans in route order without inventing graph connections."""
    spans = []
    if route and origin_position:
        graph_floor = normalize_floor(origin_floor)
        if graph_floor != route[0].floor:
            raise ValueError("Origin and first route node must be on the same floor")
        lead_in = floor_plan_distance_meters(
            origin_position, route[0].position, graph_floor
        )
        if lead_in > 0:
            spans.append(
                RouteSpan(
                    tuple(origin_position),
                    tuple(route[0].position),
                    graph_floor,
                    graph_floor,
                    lead_in,
                )
            )

    for first, second in zip(route, route[1:]):
        meters = edge_weight(first.node_id, second.node_id)
        if meters <= 0:
            raise ValueError(
                f"Route contains a non-edge segment: {first.node_id!r} to {second.node_id!r}"
            )
        spans.append(
            RouteSpan(
                tuple(first.position),
                tuple(second.position),
                first.floor,
                second.floor,
                meters,
            )
        )
    return spans


def positions_on_floor(
    route: list[RouteNode] | tuple[RouteNode, ...],
    floor: str,
    origin_position: tuple[float, float] | None = None,
    origin_floor: str = "",
) -> list[tuple[float, float]]:
    """Return ordered graph points for one floor of a route."""
    graph_floor = normalize_floor(floor)
    points = [
        tuple(node.position)
        for node in route
        if node.floor == graph_floor
    ]
    if points and origin_position and normalize_floor(origin_floor) == graph_floor:
        origin = tuple(origin_position)
        if origin != points[0]:
            points.insert(0, origin)
    return points
