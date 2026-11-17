# NavU

NavU is a Kivy/KivyMD indoor campus navigation prototype. The app's search, room data, floor plans, photos, and route graph are stored locally in this workspace.

## Run on Windows

Create the environment and install dependencies while online:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

After dependencies are installed, the app can run without internet access. GPS is optional; indoor navigation can use a manually selected floor and a tap on the floor plan.

## Project Map

| Path | Contents |
| --- | --- |
| `main.py` | Desktop and development entry point |
| `NavU.py` | Alternate launcher that prints startup exceptions |
| `navu/` | App startup, screens, room data, location handling, map drawing, and route graph |
| `navu.kv` | Screen manager and root widget tree |
| `kv/` | KivyMD layouts for the home, campus, room search, and route screens |
| `assets/campuses/` | Campus card images |
| `assets/floorplans/navu_floorplans_v3/navu/app/` | Source-of-truth route graph, routing rules, route cases, and six SVG floor plans |
| `assets/room_photos/` | Room photos organized by floor |
| `assets/gui_assests/` | Existing GUI assets; the directory name is retained as-is |
| `assets/source_archives/` | Original source archives, excluded from Android packaging |
| `recipes/` | Buildozer/python-for-android local recipes |
| `ios/` | iOS build notes |
| `buildozer.spec` | Android packaging and permissions configuration |
| `.continue/agents/LOCAL CONFIG.yaml` | Existing workspace Ollama model definitions for Continue |

## Where to Edit or Add Files

| To change or add | Use this location |
| --- | --- |
| Screen appearance and controls | `kv/<screen_name>.kv` |
| Screen behavior and room selection | `navu/screens.py` |
| Floor-plan drawing, taps, markers, and GPS overlay | `navu/map_widget.py` |
| Graph loading, start validation, and weighted multi-floor routing | `navu/routing.py` |
| Room names, floor assignments, and search terms | `assets/floorplans/navu_floorplans_v3/navu/app/route_graph.json` and `navu/screens.py` |
| Floor-plan images and routing data | `assets/floorplans/navu_floorplans_v3/navu/app/` |
| Room photos | `assets/room_photos/<floor>/` |
| Logos and navigation graphics | `assets/` or `assets/gui_assests/` |

Keep the existing folder names and relative asset paths when adding files; the app and Android package configuration load them directly from these locations.

## Offline Ollama Coding Help

Ollama is separate from the NavU app. Install Ollama and the Continue VS Code extension while online, then download the models before going offline:

```powershell
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5vl:7b
ollama list
```

The vision model is optional. Start Ollama locally and select the workspace's local model configuration in Continue. The existing definitions are in `.continue/agents/LOCAL CONFIG.yaml`; if Continue does not list them automatically, import that file through Continue's configuration UI. Model downloads are stored by Ollama and are not copied into this project. Once downloaded, local code assistance does not require an internet connection.

## Navigation Notes

The routing backend and route screen use `assets/floorplans/navu_floorplans_v3/navu/app/route_graph.json` and the matching SVG plans. The map prompt asks **“What floor are you currently on?”**; the user must choose one of LG or 1F–5F and tap their location before a route is calculated. Room search exposes destinations from the same graph, and the map renders the supplied SVG plans and their labels. UG is not part of the supported floor list. Routes use only the graph's weighted edges and vertical links; disconnected starts are rejected rather than joined with a straight line. Routes can exclude stairs or elevators.

The detailed routing rules and reference cases are in `assets/floorplans/navu_floorplans_v3/navu/app/ROUTING_RULES.md` and `route_test_cases.json`. The graph's meter weights are authoritative. The reference cases contain two confirmed inconsistencies: the canteen-to-clinic case records 54.1 m although its graph path sums to 54.3 m, and the room_307 case records 68.4 m while its expected sequence sums to 68.6 m; Dijkstra finds a shorter valid graph path at 68.5 m. Connector positions, room entries, graph labels marked for review, and scale values remain provisional and need field verification before public use.