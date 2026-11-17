import importlib

from kivy.clock import Clock
from kivy.utils import platform


class PhoneLocationTracker:
    def __init__(self, on_location, on_status):
        self._on_location = on_location
        self._on_status = on_status
        self._gps = None
        self._active = False
        self._requested = False

    def start(self):
        if platform not in ("android", "ios"):
            self._on_status(
                "Phone GPS is available in Android and iOS builds; "
                "use the map to set your start on this device."
            )
            return

        if platform == "ios":
            self._start_gps()
            return

        try:
            permission_module = importlib.import_module("android.permissions")
        except ImportError as error:
            self._on_status(f"Android location permissions unavailable: {error}")
            return

        permissions = [
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.ACCESS_COARSE_LOCATION",
        ]
        self._requested = True
        self._on_status("Requesting phone location permission...")
        permission_module.request_permissions(
            permissions,
            self._on_permissions_result,
        )

    def stop(self):
        self._requested = False
        self._active = False
        if self._gps is not None:
            self._gps.stop()
            self._gps = None

    def _on_permissions_result(self, _permissions, grant_results):
        if not self._requested:
            return
        if not grant_results or all(result != 0 for result in grant_results):
            self._requested = False
            Clock.schedule_once(
                lambda _dt: self._on_status(
                    "Location permission denied. Set your start on the floor map."
                ),
                0,
            )
            return

        self._start_gps()

    def _start_gps(self):
        try:
            from plyer import gps

            gps.configure(
                on_location=self._receive_location,
                on_status=self._receive_status,
            )
            gps.start(minTime=1000, minDistance=1)
        except (ImportError, NotImplementedError, RuntimeError) as error:
            self._requested = False
            Clock.schedule_once(
                lambda _dt, detail=str(error): self._on_status(
                    f"Phone GPS could not start: {detail}"
                ),
                0,
            )
            return

        self._gps = gps
        self._active = True
        Clock.schedule_once(
            lambda _dt: self._on_status(
                "Waiting for GPS fix. Indoor accuracy may be poor."
            ),
            0,
        )

    def _receive_location(self, **location):
        if not self._active:
            return
        Clock.schedule_once(
            lambda _dt, fix=dict(location): self._on_location(fix),
            0,
        )

    def _receive_status(self, status_type, status):
        if not self._active:
            return
        message = f"GPS {status_type}: {status}"
        Clock.schedule_once(
            lambda _dt: self._on_status(message),
            0,
        )
