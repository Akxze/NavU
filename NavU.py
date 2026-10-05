import traceback

from navu.app import NavUApp


if __name__ == "__main__":
    try:
        NavUApp().run()
    except Exception:
        traceback.print_exc()
        