import os
import re


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOORPLANS_DIR = os.path.join(BASE_DIR, "assets", "floorplans")
APP_FLOORPLANS_DIR = os.path.join(
    FLOORPLANS_DIR, "navu_floorplans_v3", "navu", "app"
)
KV_FILES = (
    os.path.join(BASE_DIR, "kv", "campus_card.kv"),
    os.path.join(BASE_DIR, "kv", "home_screen.kv"),
    os.path.join(BASE_DIR, "kv", "campus_screen.kv"),
    os.path.join(BASE_DIR, "kv", "room_search_screen.kv"),
    os.path.join(BASE_DIR, "kv", "route_screen.kv"),
)
FLOOR_CONFIG = {
    "LG": {
        "folder": "lowerground",
        "display": "LG",
        "floorplan": None,
    },
    "lower_ground": {
        "folder": "lowerground",
        "display": "LG",
        "floorplan": None,
    },
    "1": {
        "folder": "1st_floor",
        "display": "1F",
        "floorplan": "1st floor.jpg",
    },
    "2": {
        "folder": "2nd_floor",
        "display": "2F",
        "floorplan": "2nd floor.jpg",
    },
    "3": {
        "folder": "3rd_floor",
        "display": "3F",
        "floorplan": "3rd floor.jpg",
    },
    "4": {
        "folder": "4th_floor",
        "display": "4F",
        "floorplan": "4th floor.jpg",
    },
    "5": {
        "folder": "5th_floor",
        "display": "5F",
        "floorplan": "5th floor.jpg",
    },
}
FLOORPLAN_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
ROOM_PHOTOS_DIR = os.path.join(BASE_DIR, "assets", "room_photos")
FOURTH_FLOOR_PHOTOS_DIR = os.path.join(ROOM_PHOTOS_DIR, "4th_floor")
FIFTH_FLOOR_PHOTOS_DIR = os.path.join(ROOM_PHOTOS_DIR, "5th_floor")
LOWER_GROUND_PHOTOS_DIR = os.path.join(ROOM_PHOTOS_DIR, "lower_ground")
ROOM_PHOTO_FOLDERS = {
    "LG": "lower_ground",
    "lower_ground": "lower_ground",
    "1": "1st_floor",
    "2": "2nd_floor",
    "3": "3rd_floor",
    "4": "4th_floor",
    "5": "5th_floor",
}
ROOM_PHOTO_ROUTE_ALIASES = {
    "1:basketball_court": "107",
    "1:canteen": "104",
    "1:clinic": "103",
    "1:circulation_counter": "CIRC1F",
    "1:library": "LIB1F",
    "1:locker_toilet_a": "RRPE1F",
    "1:locker_toilet_b": "RRPE1F",
    "1:pe_area": "106",
    "1:registrar": "102",
    "1:stair_c": "STAIRS1F",
    "1:stair_n": "FIRE1F",
    "1:function_room_1": "FHAL1F",
    "1:function_room_2": "FHAL2F",
    "2:elevators": "ELEV2F",
    "2:counseling_1": "210",
    "2:counseling_2": "210",
    "2:counseling_3": "210",
    "2:room_ne_a": "210",
    "3:elevators": "ELEV3F",
    "3:room_ne_large": "306",
    "3:room_nw_large": "302",
    "3:room_301": "301",
    "3:room_six_table": "FAC3F",
    "3:stair_c": "STAIRS3F",
    "4:elevators": "ELEV4F",
    "4:avr": "413",
    "4:circuit_lab": "412",
    "4:com_lab_2": "423",
    "4:com_lab_5": "402",
    "4:com_lab_6": "405",
    "4:electrical_401": "401",
    "5:cafe_marianos": "502",
    "5:elevators": "ELEV5F",
    "5:electrical_501": "ELEC5F",
    "5:function_room": "501",
    "5:stair_c": "STAIRS5F",
}
# Reuse this asset for Treasury as requested, despite its 3F source location.
ROOM_PHOTO_ROUTE_OVERRIDES = {
    "1:accounting": "308",
}


def discover_floorplan_image(floor_key):
    if floor_key == "lower_ground":
        floor_key = "LG"
    if floor_key not in ("LG", "1", "2", "3", "4", "5"):
        return ""

    plan_path = os.path.join(APP_FLOORPLANS_DIR, f"app_map_{floor_key}.svg")
    return plan_path if os.path.isfile(plan_path) else ""


def discover_room_photos(floor_key):
    folder = ROOM_PHOTO_FOLDERS.get(floor_key)
    if not folder:
        return []

    floor_path = os.path.join(ROOM_PHOTOS_DIR, folder)
    if not os.path.isdir(floor_path):
        return []

    candidates = []
    for root, _, files in os.walk(floor_path):
        for file_name in files:
            if file_name.lower().endswith(FLOORPLAN_EXTENSIONS):
                candidates.append(os.path.relpath(os.path.join(root, file_name), BASE_DIR))
    return sorted(candidates, key=str.lower)


def _room_photo_floor_matches(room_floor, requested_floor):
    room_folder = ROOM_PHOTO_FOLDERS.get(room_floor)
    requested_folder = ROOM_PHOTO_FOLDERS.get(requested_floor)
    return room_folder is not None and room_folder == requested_folder


def room_photo_code_for_route(floor, room_no="", room_name="", room_id=""):
    """Find a legacy photo record by matching the route room's floor and ID."""
    photo_code = ROOM_PHOTO_ROUTE_ALIASES.get(room_id, "")
    aliased_room = ROOM_DATABASE.get(photo_code)
    if aliased_room and _room_photo_floor_matches(
        aliased_room.get("floor", ""), floor
    ):
        return photo_code

    normalized_name = re.sub(r"[^a-z0-9]+", " ", room_name.casefold()).strip()
    if room_no:
        code = str(room_no)
        room = ROOM_DATABASE.get(code)
        normalized_record_name = (
            re.sub(r"[^a-z0-9]+", " ", room.get("name", "").casefold()).strip()
            if room
            else ""
        )
        if (
            room
            and _room_photo_floor_matches(room.get("floor", ""), floor)
            and code in normalized_name.split()
            and code in normalized_record_name.split()
        ):
            return code

    if not normalized_name:
        return ""

    matches = [
        code
        for code, room in ROOM_DATABASE.items()
        if _room_photo_floor_matches(room.get("floor", ""), floor)
        and re.sub(r"[^a-z0-9]+", " ", room.get("name", "").casefold()).strip()
        == normalized_name
    ]
    return matches[0] if len(matches) == 1 else ""


def resolve_room_photos(room_code, floor=None, room_no="", room_name=""):
    """Return existing room photos, validating route IDs against their floor."""
    override_code = ROOM_PHOTO_ROUTE_OVERRIDES.get(room_code, "")
    room = ROOM_DATABASE.get(override_code or room_code)
    if room is None:
        photo_code = room_photo_code_for_route(
            floor, room_no, room_name, room_id=room_code
        )
        room = ROOM_DATABASE.get(photo_code)
    if not room:
        return []
    if (
        floor is not None
        and not override_code
        and not _room_photo_floor_matches(room.get("floor", ""), floor)
    ):
        return []

    floor_folder = ROOM_PHOTO_FOLDERS.get(room.get("floor", ""))
    floor_path = (
        os.path.join(ROOM_PHOTOS_DIR, floor_folder) if floor_folder else ""
    )
    floor_files = {}
    if floor_path and os.path.isdir(floor_path):
        for root, _, files in os.walk(floor_path):
            for file_name in files:
                floor_files.setdefault(
                    file_name.casefold(),
                    os.path.join(root, file_name),
                )

    resolved = []
    seen_paths = set()
    for photo in room.get("photos", []):
        photo_path = photo if os.path.isabs(photo) else os.path.join(BASE_DIR, photo)
        if os.path.isfile(photo_path):
            candidate = photo_path
        else:
            candidate = floor_files.get(os.path.basename(photo).casefold())
        if candidate:
            canonical_path = os.path.normcase(os.path.realpath(candidate))
            if canonical_path not in seen_paths:
                seen_paths.add(canonical_path)
                resolved.append(candidate)
    return resolved


ROOM_DATABASE = {
    "APPARLG": {
        "floor": "lower_ground",
        "name": "Apparel Laboratory / Garment Studio",
        "directions": "Lower Ground Floor; fashion, apparel, and pattern drafting lab.",
        "keywords": "apparel textile sewing fashion garment pattern drafting lab laboratory clothes",
        "photos": [os.path.join(LOWER_GROUND_PHOTOS_DIR, "apparel_lg.jpg")],
    },
    "CONMATLG": {
        "floor": "lower_ground",
        "name": "Construction Materials Laboratory",
        "directions": "Lower Ground Floor; civil engineering materials and concrete testing lab.",
        "keywords": "construction materials concrete civil engineering testing aggregates lab laboratory",
        "photos": [os.path.join(LOWER_GROUND_PHOTOS_DIR, "construction_mkaterials_lg.jpg")],
    },
    "ELEVLG": {
        "floor": "lower_ground",
        "name": "Elevator Lobby LG",
        "directions": "Lower Ground Floor; main elevators for upper floors and campus connectivity.",
        "keywords": "elevator lift lobby ground floor access",
        "photos": [
            os.path.join(LOWER_GROUND_PHOTOS_DIR, "elevator_lg1.jpg"),
            os.path.join(LOWER_GROUND_PHOTOS_DIR, "elevator_lg2.jpg"),
            os.path.join(LOWER_GROUND_PHOTOS_DIR, "elevator_lg3.jpg"),
            os.path.join(LOWER_GROUND_PHOTOS_DIR, "elevator_lg4.jpg"),
        ],
    },
    "EMERGLG": {
        "floor": "lower_ground",
        "name": "Emergency Exit LG",
        "directions": "Lower Ground Floor; safety emergency exit and exterior evacuation pathway.",
        "keywords": "emergency exit escape evacuation doors exit pathway",
        "photos": [os.path.join(LOWER_GROUND_PHOTOS_DIR, "emergency_exit_lg.jpg")],
    },
    "FIRESTLG": {
        "floor": "lower_ground",
        "name": "Fire Exit Stairs LG",
        "directions": "Lower Ground Floor; fire-rated egress stairwell leading to upper floors and exit.",
        "keywords": "fire exit stairs staircase escape stairway emergency",
        "photos": [os.path.join(LOWER_GROUND_PHOTOS_DIR, "fire_exit_stairs_lg.jpg")],
    },
    "DESKLG": {
        "floor": "lower_ground",
        "name": "Front Desk / Lobby Information",
        "directions": "Lower Ground Floor; main reception, visitor check-in, and student assistance.",
        "keywords": "front desk reception information lobby assistance guard visitor inquiries",
        "photos": [os.path.join(LOWER_GROUND_PHOTOS_DIR, "front_desk.jpg")],
    },
    "ISOLG": {
        "floor": "lower_ground",
        "name": "Isolation Room LG",
        "directions": "Lower Ground Floor; health and medical isolation facility for student care.",
        "keywords": "isolation room medical clinic health first aid nurse sick room",
        "photos": [os.path.join(LOWER_GROUND_PHOTOS_DIR, "isolation_room_lg.jpg")],
    },
    "ENTLG": {
        "floor": "lower_ground",
        "name": "Main Entrance LG",
        "directions": "Lower Ground Floor; primary entrance gate, turnstiles, and foyer.",
        "keywords": "main entrance entrance door gate entry turnstiles access foyer",
        "photos": [os.path.join(LOWER_GROUND_PHOTOS_DIR, "main_entrance.jpg")],
    },
    "UTMLG": {
        "floor": "lower_ground",
        "name": "Universal Testing Machine (UTM) Lab",
        "directions": "Lower Ground Floor; heavy mechanical stress, tensile, and compressive testing laboratory.",
        "keywords": "universal testing machine utm civil mechanical engineering lab laboratory tensile stress compression",
        "photos": [os.path.join(LOWER_GROUND_PHOTOS_DIR, "Universal_testing_machine_lg.jpg")],
    },
    "LG01": {
        "floor": "lower_ground",
        "name": "Cafeteria / Food Court",
        "directions": "Lower Ground level near escalator and main entrance.",
        "keywords": "cafeteria food court canteen dining meals snacks drinks",
    },
    "LG02": {
        "floor": "lower_ground",
        "name": "Chemistry Laboratory",
        "directions": "Lower Ground level, East wing laboratory corridor.",
        "keywords": "chemistry laboratory lab chem science experiments",
    },
    "101": {
        "floor": "1",
        "name": "Admissions Office",
        "directions": "1st Floor, main lobby near entrance.",
        "photos": [
            os.path.join(
                ROOM_PHOTOS_DIR, "1st_floor", "ADMISSIONS_OFFICE_COMPUTER.JPG"
            )
        ],
    },
    "102": {
        "floor": "1",
        "name": "Registrar Office",
        "directions": "1st Floor; exact location needs confirmation.",
        "keywords": "registration registrar registar register",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "REGISTAR.JPG")],
    },
    "103": {
        "floor": "1",
        "name": "Clinic",
        "directions": "1st Floor; exact location needs confirmation.",
        "keywords": "health clinic nurse medical",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "CLINIC_108.JPG")],
    },
    "104": {
        "floor": "1",
        "name": "Canteen / Cafeteria",
        "directions": "1st Floor; exact location needs confirmation.",
        "keywords": "canteen cafeteria food dining",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "CANTEEN.JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "CANTEEN (2).JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "CANTEEN_101.JPG"),
        ],
    },
    "FIRE1F": {
        "floor": "1",
        "name": "Fire Exit 1F",
        "directions": "1st Floor; exact exit locations need confirmation.",
        "keywords": "fire exit escape",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "emergency_exit_1st.JPG")
        ],
    },
    "105": {
        "floor": "1",
        "name": "Printing Shop",
        "directions": "1st Floor; exact location needs confirmation.",
        "keywords": "printing print shop photocopy photocopying",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "paws_and_print_1st.JPG")
        ],
    },
    "106": {
        "floor": "1",
        "name": "PE Area",
        "directions": "1st Floor; exact location needs confirmation.",
        "keywords": "PE physical education",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "PE_AREA.JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "PE_AREA (2).JPG"),
        ],
    },
    "107": {
        "floor": "1",
        "name": "Basketball Court",
        "directions": "1st Floor; exact location needs confirmation.",
        "keywords": "basketball court sports",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "BASKETBALL_COURT.JPG"),
            os.path.join(
                ROOM_PHOTOS_DIR, "1st_floor", "BASKETBALL_COURT_ENTRANCE.JPG"
            ),
        ],
    },
    "RRPE1F": {
        "floor": "1",
        "name": "PE Area Restroom",
        "directions": "1st Floor near the PE area; exact location needs confirmation.",
        "keywords": "PE restroom bathroom toilet comfort room CR washroom",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "PE_AREA_BATHROOM.JPG")
        ],
    },
    "STAIRS1F": {
        "floor": "1",
        "name": "Main Stairs 1st Floor",
        "directions": "1st Floor; exact location needs confirmation.",
        "keywords": "main stairs staircase stairway",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "1STFLOOR_MAIN_STAIRS.JPG")
        ],
    },
    "108": {
        "floor": "1",
        "name": "Function Hall",
        "directions": "1st Floor; exact location needs confirmation.",
        "keywords": "function hall event hall",
    },
    "FHAL1F": {
        "floor": "1",
        "name": "Function Room 1",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "FUNCTION_ROOM1.JPG")
        ],
    },
    "FHAL2F": {
        "floor": "1",
        "name": "Function Room 2",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "FUNCTION_ROOM2.JPG")
        ],
    },
    "LIB1F": {
        "floor": "1",
        "name": "Library (LRC)",
        "directions": "1st Floor; Learning Resource Center.",
        "keywords": "library learning resource center LRC",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "LIBRARY_LRC.JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "LIBRARY_LRC (2).JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "LIBRARY_LRC (3).JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "LIBRARY_LRC (4).JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "LRC.JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "LRC (2).JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "COMPUTER_AREA_LRC.JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "DISCUSSION_ROOMS.JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "DRAWING_BOARD_LRC.JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "STUDY_ROOM_LRC.JPG"),
        ],
    },
    "CIRC1F": {
        "floor": "1",
        "name": "Circulation Counter (LRC)",
        "directions": "1st Floor; Learning Resource Center service counter.",
        "keywords": "library LRC circulation borrower counter",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "1st_floor", "CIRCULATION_COUNTER_LRC.JPG")
        ],
    },
    "201": {
        "floor": "2",
        "name": "Electrical Room 201",
        "directions": "2nd Floor; exact location needs confirmation.",
        "keywords": "electrical electricity power",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_201_electrical.jpg")],
    },
    "301": {
        "floor": "3",
        "name": "Computer Laboratory 1",
        "directions": "3rd Floor, left wing past elevator.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_301.png")],
    },
    "302": {
        "floor": "3",
        "name": "Physics Laboratory",
        "directions": "3rd Floor, right wing.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_302.png")],
    },
    "320": {
        "floor": "3",
        "name": "Room 320 - San Lorenzo Ruiz Chapel",
        "directions": "3rd Floor; exact route location needs confirmation.",
        "keywords": "church chapel san lorenzo ruiz chapel",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "chapel_room_320.png"),
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "chapel.png"),
        ],
    },
    "324": {
        "floor": "3",
        "name": "Room 324 - Campus Research Office / Media Laboratory",
        "directions": "3rd Floor; exact route location needs confirmation.",
        "keywords": (
            "faculty services office marketing offices campus research "
            "office media laboratory media lab"
        ),
        "photos": [
            os.path.join(
                ROOM_PHOTOS_DIR,
                "3rd_floor",
                "campus_research room_324.png",
            ),
            os.path.join(
                ROOM_PHOTOS_DIR,
                "3rd_floor",
                "media_laboratory_324.JPG",
            ),
        ],
        "photo_fit": "cover",
        "show_photo_details": False,
    },
    "FIRE3F": {
        "floor": "3",
        "name": "Fire Exit 3F",
        "directions": "3rd Floor; exact exit locations need confirmation.",
        "keywords": "exit fire escape",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "fire_exit.png"),
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "fire_exit2.png"),
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "fire_exit3.png"),
        ],
    },
    "400": {
        "floor": "4",
        "name": "Physics Storage Room",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "physics_storage_400.png")],
    },
    "401": {
        "floor": "4",
        "name": "Electrical Room",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "electrical_room_401.png")],
    },
    "402": {
        "floor": "4",
        "name": "Computer Laboratory 402",
        "directions": "4th Floor; exact route location needs confirmation.",
        "keywords": "computer lab comp lab",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "computer_lab_402.png")],
    },
    "404": {
        "floor": "4",
        "name": "Room 404",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_404.png")],
    },
    "405": {
        "floor": "4",
        "name": "Computer Laboratory 6 (Room 405)",
        "directions": "4th Floor; exact route location needs confirmation.",
        "keywords": "computer lab comp lab",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "computer_lab_405.png")],
    },
    "406": {
        "floor": "4",
        "name": "Room 406",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_424_room_406.png")],
    },
    "407": {
        "floor": "4",
        "name": "General Physics Laboratory 407",
        "directions": "4th Floor; exact route location needs confirmation.",
        "keywords": "physics lab",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "general_physics_lab_407.png")],
    },
    "409": {
        "floor": "4",
        "name": "General Physics Laboratory 409",
        "directions": "4th Floor; exact route location needs confirmation.",
        "keywords": "physics lab",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "general_physics_lab_409.png")],
    },
    "410": {
        "floor": "4",
        "name": "Room 410",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_410.png")],
    },
    "411": {
        "floor": "4",
        "name": "Server Room 411",
        "directions": "4th Floor; exact route location needs confirmation.",
        "keywords": "server",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "server_room_411.png")],
    },
    "412": {
        "floor": "4",
        "name": "Circuit Laboratory 412",
        "directions": "4th Floor; exact route location needs confirmation.",
        "keywords": "circuit lab",
        "photos": [
            os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "circuit_412.png"),
            os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "circuit_lab_412.png"),
        ],
    },
    "413": {
        "floor": "4",
        "name": "AVR 413",
        "directions": "4th Floor; exact route location needs confirmation.",
        "keywords": "audio visual room",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "AVR_413.png")],
    },
    "414": {
        "floor": "4",
        "name": "Room 414",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_414.png")],
    },
    "415": {
        "floor": "4",
        "name": "Room 415",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_415.png")],
    },
    "416": {
        "floor": "4",
        "name": "Room 416",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_416.png")],
    },
    "417": {
        "floor": "4",
        "name": "Room 417",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_417.png")],
    },
    "418": {
        "floor": "4",
        "name": "Room 418",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_418.png")],
    },
    "419": {
        "floor": "4",
        "name": "Room 419",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_419.png")],
    },
    "420": {
        "floor": "4",
        "name": "Room 420",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_420.png")],
    },
    "421": {
        "floor": "4",
        "name": "Computer Laboratory 1 (Room 421)",
        "directions": "4th Floor; exact route location needs confirmation.",
        "keywords": "computer lab comp lab",
        "photos": [
            os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_421.png"),
            os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "computer_lab_421.png"),
        ],
    },
    "422": {
        "floor": "4",
        "name": "Room 422",
        "directions": "4th Floor; exact route location needs confirmation.",
    },
    "423": {
        "floor": "4",
        "name": "Computer Laboratory 2 (Room 423)",
        "directions": "4th Floor; exact route location needs confirmation.",
        "keywords": "computer lab comp lab",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "computer_lab_423.png")],
    },
    "424": {
        "floor": "4",
        "name": "Room 424",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_424_room_406.png")],
    },
    "425": {
        "floor": "4",
        "name": "Room 425",
        "directions": "4th Floor; exact route location needs confirmation.",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "room_425.png")],
    },
    "ELEV4F": {
        "floor": "4",
        "name": "Elevator 4F",
        "directions": "4th Floor; exact elevator location needs confirmation.",
        "keywords": "lift elevator",
        "photos": [
            os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "4th_floor_elevator.png"),
            os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "IMG_2724.png"),
        ],
    },
    "CHANGING4F": {
        "floor": "4",
        "name": "Changing Room 4F",
        "directions": "4th Floor; exact location needs confirmation.",
        "keywords": "changing locker room",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "changing_room_4th.png")],
    },
    "FIRE4F": {
        "floor": "4",
        "name": "Fire Exit 4F",
        "directions": "4th Floor; exact exit locations need confirmation.",
        "keywords": "exit fire escape",
        "photos": [
            os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "fire_exit.png"),
            os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "fire_exit2.png"),
        ],
    },
    "RR4F": {
        "floor": "4",
        "name": "Restroom 4F",
        "directions": "4th Floor; exact location needs confirmation.",
        "keywords": "restrooms bathroom bathrooms toilet toilets comfort room comfortroom washroom CR",
        "photos": [os.path.join(FOURTH_FLOOR_PHOTOS_DIR, "restroom_4th.png")],
    },
    "501": {
        "floor": "5",
        "name": "Multipurpose Hall",
        "directions": "5th Floor; provisionally mapped to the function-room door.",
        "photos": [
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "function_hall_5th_upright.jpg"),
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "function_hall_5th.JPG"),
        ],
    },
    "502": {
        "floor": "5",
        "name": "Mariano's Cafe",
        "directions": "5th Floor; provisionally mapped to the cafe door.",
        "keywords": "marianos cafe coffee coffee shop",
        "photos": [
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "marianos_cafe_feature_upright.jpg"),
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "mariano's_cafe_feature.JPG"),
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "5th_restaurant_cafe.JPG"),
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "cafe_mariano.jpg"),
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "5th_cafe.JPG"),
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "room_502.png"),
        ],
    },
    "RR1F": {"floor": "1", "name": "Restroom 1F", "directions": "1st Floor; exact location needs confirmation.", "keywords": "restrooms bathroom bathrooms toilet toilets comfort room comfortroom washroom CR"},
    "RR2F": {
        "floor": "2",
        "name": "Restroom 2F",
        "directions": "2nd Floor; exact location needs confirmation.",
        "keywords": "restrooms bathroom bathrooms toilet toilets comfort room comfortroom washroom CR",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "restroom_2f.jpg")],
    },
    "RR3F": {"floor": "3", "name": "Restroom 3F", "directions": "3rd Floor; exact location needs confirmation.", "keywords": "restrooms bathroom bathrooms toilet toilets comfort room comfortroom washroom CR"},
    "RR5F": {
        "floor": "5",
        "name": "Restroom 5F",
        "directions": "5th Floor; exact location needs confirmation.",
        "keywords": "restrooms bathroom bathrooms toilet toilets comfort room comfortroom washroom CR",
    },
    "RRLG": {
        "floor": "lower_ground",
        "name": "Restroom Lower Ground",
        "directions": "Lower Ground; exact location needs confirmation.",
        "keywords": "restroom bathroom toilet comfort room CR washroom",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "lower_ground", "lg_restroom.jpg")],
    },
    "503": {
        "floor": "5",
        "name": "Room 503",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "room_503.jpg")],
    },
    "504": {
        "floor": "5",
        "name": "Room 504",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "room_504.jpg")],
    },
    "505": {
        "floor": "5",
        "name": "Storage Room 505",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "storage_room_505.jpg")],
    },
    "506": {
        "floor": "5",
        "name": "Room 506",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "room_506.jpg")],
    },
    "507": {
        "floor": "5",
        "name": "Chemistry Storage 507",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "chemistry_storage_507.jpg")],
    },
    "508": {
        "floor": "5",
        "name": "Chemistry Laboratory 508",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "keywords": "chemistry lab",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "chem_lab_508.jpg")],
    },
    "509": {
        "floor": "5",
        "name": "Room 509",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "room_509.jpg")],
    },
    "511": {
        "floor": "5",
        "name": "Room 511",
        "directions": "5th Floor; exact location needs confirmation.",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "room_511.jpg")],
    },
    "512": {
        "floor": "5",
        "name": "Baking Kitchen 512",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "keywords": "kitchen baking",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "baking_kitchen_512.jpg")],
    },
    "513": {
        "floor": "5",
        "name": "Cold Kitchen 513",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "keywords": "kitchen cold kitchen",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "cold_kitchen_513.jpg")],
    },
    "514": {
        "floor": "5",
        "name": "Storage Room 514",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "storage3_514.jpg")],
    },
    "515": {
        "floor": "5",
        "name": "Cold Kitchen 515",
        "directions": "5th Floor; exact location needs confirmation.",
        "keywords": "kitchen cold kitchen",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "cold_kitchen_515.jpg")],
    },
    "516": {
        "floor": "5",
        "name": "Storage Room 516",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "storage2_516.jpg")],
    },
    "517": {
        "floor": "5",
        "name": "Hot Chicken Kitchen 517",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "keywords": "kitchen hot chicken",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "hot_chicken3_517.jpg")],
    },
    "519": {
        "floor": "5",
        "name": "Hot Chicken Kitchen 519",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "keywords": "kitchen hot chicken",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "hot_chicken2_519.jpg")],
    },
    "521": {
        "floor": "5",
        "name": "Hot Kitchen 521",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "keywords": "kitchen hot cooking",
        "photos": [
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "room_521_hot_kitchen.JPG")
        ],
    },
    "522": {
        "floor": "5",
        "name": "Demo Kitchen 522",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "keywords": "kitchen demonstration",
        "photos": [
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "demo_kitchen_522.jpg"),
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "room_522.JPG"),
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "room_522 (2).JPG"),
        ],
    },
    "523": {
        "floor": "5",
        "name": "Laundry Room 523",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "keywords": "laundry",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "laundry_523.jpg")],
    },
    "ELEV5F": {
        "floor": "5",
        "name": "Elevator 5F",
        "directions": "5th Floor; elevator approach mapped from the supplied route plan.",
        "keywords": "lift elevator",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "5th_elevator.jpg")],
    },
    "STAIRS5F": {
        "floor": "5",
        "name": "Main Stairs 5F",
        "directions": "5th Floor; main-stair approach mapped from the supplied route plan.",
        "keywords": "stairs staircase stairway",
        "photos": [
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "5th_floor_main_stairs.JPG")
        ],
    },
    "CHANGING5F": {
        "floor": "5",
        "name": "Changing Room 5F",
        "directions": "5th Floor; exact location needs confirmation.",
        "keywords": "changing locker room",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "5th_changing_room.jpg")],
    },
    "FAMILY5F": {
        "floor": "5",
        "name": "Family Suite",
        "directions": "5th Floor; door approach mapped from the supplied route plan.",
        "keywords": "family suite",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "family_suite.jpg")],
    },
    "ELEC5F": {
        "floor": "5",
        "name": "Electrical Room 5F",
        "directions": (
            "5th Floor; photo filename references Room 501, but the room "
            "assignment needs confirmation."
        ),
        "keywords": "electrical electricity 501",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "room_electrical_501.jpg")],
    },
    "HOTKITCHEN5F": {
        "floor": "5",
        "name": "Hot Kitchen 5F",
        "directions": "5th Floor; exact room number needs confirmation.",
        "keywords": "hot kitchen cooking",
        "photos": [os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "hot_kitchen1.jpg")],
    },
    "FIRE5F": {
        "floor": "5",
        "name": "Fire Exit 5F",
        "directions": "5th Floor; northeast stair/exit mapped from the supplied route plan.",
        "keywords": "exit fire escape",
        "photos": [
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "fire_exit_5th.jpg"),
            os.path.join(FIFTH_FLOOR_PHOTOS_DIR, "fire_exit2_5th.jpg"),
        ],
    },
    "303": {
        "floor": "3",
        "name": "Room 303",
        "directions": (
            "3rd Floor; provisionally routed to the west-side hallway. "
            "The exact doorway still needs confirmation."
        ),
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_303.png")],
    },
    "305": {
        "floor": "3",
        "name": "Room 305",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_305.png")],
    },
    "306": {
        "floor": "3",
        "name": "Board Room 306",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "board_room_306.png")],
    },
    "308": {
        "floor": "3",
        "name": "Accounting Room 308",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "accounting_room_308.png")],
    },
    "309": {
        "floor": "3",
        "name": "Room 309",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_309.png")],
    },
    "310": {
        "floor": "3",
        "name": "Room 310",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_310.png"),
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_310.JPG"),
        ],
    },
    "317": {
        "floor": "3",
        "name": "Room 317",
        "directions": "3rd Floor; approximate location from room numbering.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_317.JPG")],
    },
    "311": {
        "floor": "3",
        "name": "Room 311",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_311.png")],
    },
    "313": {
        "floor": "3",
        "name": "Room 313",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_313.png")],
    },
    "314": {
        "floor": "3",
        "name": "Room 314",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_314.png")],
    },
    "318": {
        "floor": "3",
        "name": "Room 318",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_318.png")],
    },
    "319": {
        "floor": "3",
        "name": "Room 319",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_319.png")],
    },
    "321": {
        "floor": "3",
        "name": "Room 321",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_321.png")],
    },
    "322": {
        "floor": "3",
        "name": "Room 322",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_322.png")],
    },
    "323": {
        "floor": "3",
        "name": "Room 323",
        "directions": "3rd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "room_323.png")],
    },
    "327": {
        "floor": "3",
        "name": "Human Resources Office 327",
        "directions": "3rd Floor; exact location needs confirmation.",
        "keywords": "HR human resources office",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "hr_office_327.png")],
    },
    "306BIZ": {
        "floor": "3",
        "name": "Business Simulation Room",
        "directions": "3rd Floor; exact location needs confirmation.",
        "keywords": "business simulation",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "Business_simulation_room.png")],
    },
    "FAC3F": {
        "floor": "3",
        "name": "Faculty Room",
        "directions": "3rd Floor; exact location needs confirmation.",
        "keywords": "faculty staff office",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "faculty_room.png")],
    },
    "ELEV3F": {
        "floor": "3",
        "name": "Elevator 3F",
        "directions": "3rd Floor; approximate location from the floor plan.",
        "keywords": "lift elevator",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "elevator_3rd.JPG"),
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "elevator_3rd1.JPG"),
        ],
    },
    "STAIRS3F": {
        "floor": "3",
        "name": "Main Stairs 3F",
        "directions": "3rd Floor; approximate location from the floor plan.",
        "keywords": "stairs staircase stairway",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "3rd_floor_main_stairs.JPG")
        ],
    },
    "LOCKER3F": {
        "floor": "3",
        "name": "Locker Room 3F",
        "directions": "3rd Floor; exact location needs confirmation.",
        "keywords": "locker lockers",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "3rd_floor", "locker_3rd.JPG")
        ],
    },
    "202": {
        "floor": "2",
        "name": "Room 202",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_202.JPG"),
        ],
    },
    "203": {
        "floor": "2",
        "name": "Room 203",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_203.JPG"),
        ],
    },
    "204": {
        "floor": "2",
        "name": "Room 204",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_204.jpg")],
    },
    "205": {
        "floor": "2",
        "name": "Room 205",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_205.jpg")],
    },
    "206": {
        "floor": "2",
        "name": "Room 206",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_206.jpg")],
    },
    "207": {
        "floor": "2",
        "name": "Room 207",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_207.jpg")],
    },
    "208": {
        "floor": "2",
        "name": "Room 208",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_208.jpg")],
    },
    "209": {
        "floor": "2",
        "name": "Room 209",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_209.jpg")],
    },
    "210": {
        "floor": "2",
        "name": "Guidance Office 210",
        "directions": "2nd Floor; exact location needs confirmation.",
        "keywords": "guidance counselor counselling counseling",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "guidance_office_210.jpg")],
    },
    "211": {
        "floor": "2",
        "name": "Testing Unit 211",
        "directions": "2nd Floor; exact location needs confirmation.",
        "keywords": "testing assessment",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "testing_unit_211.jpg")],
    },
    "212": {
        "floor": "2",
        "name": "Laboratory 212",
        "directions": "2nd Floor; exact location needs confirmation.",
        "keywords": "lab laboratory",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_212_lab.jpg")],
    },
    "213": {
        "floor": "2",
        "name": "Geotechnical Hydraulics Room 213",
        "directions": "2nd Floor; exact location needs confirmation.",
        "keywords": "geotechnical hydraulics laboratory lab",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "geotech_hydralics_room213.jpg")],
    },
    "214": {
        "floor": "2",
        "name": "Laboratory 214",
        "directions": "2nd Floor; exact location needs confirmation.",
        "keywords": "lab laboratory",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_214_lab.jpg")],
    },
    "215": {
        "floor": "2",
        "name": "Room 215",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_215.jpg")],
    },
    "217": {
        "floor": "2",
        "name": "Room 217",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_217.jpg")],
    },
    "218": {
        "floor": "2",
        "name": "Room 218",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_218.JPG"),
        ],
    },
    "219": {
        "floor": "2",
        "name": "Room 219",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_219.JPG"),
        ],
    },
    "220": {
        "floor": "2",
        "name": "Room 220",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_220.jpg")],
    },
    "221": {
        "floor": "2",
        "name": "Room 221",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_221.jpg")],
    },
    "222": {
        "floor": "2",
        "name": "Room 222",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_222.jpg")],
    },
    "223": {
        "floor": "2",
        "name": "Psychology Laboratory 223",
        "directions": "2nd Floor; exact location needs confirmation.",
        "keywords": "psychology lab",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "psychology_lab_223.jpg")],
    },
    "224": {
        "floor": "2",
        "name": "Room 224",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_224.jpg")],
    },
    "225": {
        "floor": "2",
        "name": "Room 225",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_225.JPG"),
        ],
    },
    "226": {
        "floor": "2",
        "name": "Room 226",
        "directions": "2nd Floor; exact location needs confirmation.",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "room_226.jpg")],
    },
    "ELEV2F": {
        "floor": "2",
        "name": "Elevator 2F",
        "directions": "2nd Floor; exact elevator location needs confirmation.",
        "keywords": "lift elevator",
        "photos": [os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "elevator_2nd.jpg")],
    },
    "FIRE2F": {
        "floor": "2",
        "name": "Fire Exit 2F",
        "directions": "2nd Floor; exact exit locations need confirmation.",
        "keywords": "exit fire escape",
        "photos": [
            os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "fire_exit1.jpg"),
            os.path.join(ROOM_PHOTOS_DIR, "2nd_floor", "fire_exit2.jpg"),
        ],
    },
}
