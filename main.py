from kivy.config import Config

Config.set("input", "mouse", "mouse,multitouch_on_demand")  # disable multitouch
Config.set("graphics", "borderless", "1")  # remove title bar
Config.set("graphics", "resizable", "0")
Config.set("graphics", "width", "142")
Config.set("graphics", "height", "30")
Config.set("graphics", "always_on_top", "1")
Config.set("graphics", "show_taskbar_icon", "0")

import sys
import ctypes
import asyncio
import websockets

from json import loads
from os.path import join
from pyautogui import position
from unidecode import unidecode

# Miscellaneous Kivy imports
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.network.urlrequest import UrlRequest
from kivy.resources import resource_add_path, resource_find

# Kivy's properties imports
from kivy.properties import ObjectProperty

# Kivy's UI imports
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition

# Change Kivy window background color and opacity
Window.clearcolor = (16 / 255, 23 / 255, 32 / 255, 1)
Window.opacity = 0.9


class IconButton(ButtonBehavior, Image):  # button with icon representation
    pass


# Button to mimic the title bar's drag behaviour for moving the Kivy window around
class DragButton(IconButton):
    def __init__(self, **kwargs):
        self.drag_enabled = False
        self.initial_x = 0  # to store the initial x position of mouse
        self.initial_y = 0  # to store the initial y position of mouse
        self.initial_left = 0  # to store the initial left position of Kivy window
        self.initial_top = 0  # to store the initial top position of Kivy window

        super().__init__(**kwargs)

    def on_press(self):
        pos = position()
        self.initial_x = pos[0]
        self.initial_y = pos[1]
        self.initial_left = Window.left
        self.initial_top = Window.top

        self.drag_enabled = True

    def on_touch_move(self, touch):
        if self.drag_enabled:
            pos = position()
            Window.left = (self.initial_left + pos[0] - self.initial_x)
            Window.top = (self.initial_top + pos[1] - self.initial_y)

    def on_touch_up(self, touch):
        self.drag_enabled = False


# The simple screen to show the synced lyrics and options to move or close the window
class LyricsOverlayScreen(Screen):
    lyric = ObjectProperty()
    drag_button = ObjectProperty()
    exit_button = ObjectProperty()

    def __init__(self):
        super().__init__(name="Lyrics Overlay")

        # Makes the drag and exit buttons visible when window is focused,
        # and turns invisible when window is not in focus
        Clock.schedule_interval(lambda dt: self.handle_button_visibility(), 0.1)

    def handle_button_visibility(self):
        if Window.focus:
            self.drag_button.opacity = 1
            self.exit_button.opacity = 1
        else:
            self.drag_button.opacity = 0
            self.exit_button.opacity = 0

    def on_pre_enter(self, *args):
        self.lyric.texture_update()


class CustomScreenManager(ScreenManager):
    def on_touch_down(self, touch) -> bool:
        # Block clicks from right and middle click
        if touch.button in ["right", "middle"]:
            return True

        super().on_touch_down(touch)


# Backend of the application and other Kivy related stuff are implemented here
# Fetches the lyrics and shows them on LyricsOverlayScreen according to the data sent by Chromium extension
class MusicLawApp(App):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Flag to block lyrics interference if a YT Music tab is sending lyrics data and additional tabs are opened
        self.is_client_connected = False

        self.lyrics = {}  # to store lyrics fetched from the API
        self.lyrics_not_found = False  # flag to handle the case of lyrics not being available

        self.current_song = None  # to keep record of currently playing song and fetch lyrics only when changed
        self.current_duration = None

        self.overlay_screen = None
        self.screen_manager = CustomScreenManager(transition=NoTransition())

    def lyrics_unavailable(self, *args):  # NOQA
        self.lyrics_not_found = True

    def create_lyrics_mappings(self, req, res) -> None:  # NOQA
        for line in res:
            self.lyrics[line["seconds"]] = line["lyrics"]

        current_line = "Music LAW"
        for second in range(list(self.lyrics.keys())[-1]):
            try:
                current_line = self.lyrics[second]
            except KeyError:
                self.lyrics[second] = current_line

    @staticmethod
    def get_lyrics_url(song_name: str, song_info: str) -> str:
        query = []

        if song_name:
            song_name = (song_name
                         .replace("feat.", "")
                         .replace("original motion picture soundtrack", "")
                         .replace("from the original motion picture", ""))
            song_name = "".join(char for char in song_name if char.isalnum() or char.isspace()).split()
            for word in song_name:
                if word not in query:
                    query.append(word)

        if song_info:
            song_info = (song_info
                         .replace("feat.", "")
                         .replace("original motion picture soundtrack", "")
                         .replace("from the original motion picture", ""))
            song_info = "".join(char for char in song_info if char.isalnum() or char.isspace()).split()
            for word in song_info:
                if word not in query:
                    query.append(word)

        if query:
            # https://stackoverflow.com/a/64417359/14113019
            return f"https://api.textyl.co/api/lyrics?q={'%20'.join(query)}"

        return ""

    # Method to fetch the lyrics based on the song details sent by Chromium extension
    def get_lyrics(self, song_details) -> None:
        if None in song_details.values():
            return

        self.current_duration = song_details["currentDuration"]

        song_name = unidecode(song_details["songName"]).lower()
        song_artists_and_album = unidecode(song_details["songArtistsAndAlbum"]).lower()

        song = f"{song_name} - {song_artists_and_album}"
        if song != self.current_song:  # don't fetch lyrics again until the track is changed
            self.current_song = song

            self.lyrics.clear()
            self.lyrics_not_found = False

            lyrics_url = self.get_lyrics_url(song_name, song_artists_and_album)

            if not lyrics_url:
                return

            UrlRequest(lyrics_url, self.create_lyrics_mappings,
                       verify=False,
                       on_cancel=self.lyrics_unavailable,
                       on_error=self.lyrics_unavailable,
                       on_failure=self.lyrics_unavailable)

    def set_lyrics(self) -> None:
        if self.lyrics_not_found:
            self.overlay_screen.lyric.text = "Lyrics not found"
        elif len(self.lyrics) == 0:
            self.overlay_screen.lyric.text = "Music LAW"
        else:
            try:
                lyric = self.lyrics[int(self.current_duration)]
                self.overlay_screen.lyric.text = lyric
            except (KeyError, ValueError, TypeError):
                pass

        self.overlay_screen.lyric.texture_update()

    @staticmethod
    def hide_taskbar_icon(*args):  # NOQA
        hwnd = Window.get_window_info().window

        # Hide the taskbar icon by removing the WS_EX_APPWINDOW style
        # and adding the WS_EX_TOOLWINDOW style
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE = -20
        style = style & ~0x00040000 | 0x00000080  # WS_EX_APPWINDOW = 0x00040000, WS_EX_TOOLWINDOW = 0x00000080
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)

        # Update the window to apply the new style
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                          0x0001 | 0x0002 | 0x0004 | 0x0020)

    def on_start(self):
        self.overlay_screen = self.screen_manager.get_screen("Lyrics Overlay")
        self.hide_taskbar_icon()

    def on_stop(self):
        self.websocket_server_task.cancel()  # NOQA

    def build(self):
        self.icon = "icon.png"
        self.title = "Music LAW - Lyrics AnyWhere"

        self.screen_manager.add_widget(LyricsOverlayScreen())
        return self.screen_manager


async def websocket_handler(websocket, path, app):
    if app.is_client_connected:
        try:
            async for _ in websocket:
                pass

                if not app.is_client_connected:
                    break
        finally:
            if app.is_client_connected:
                return
            else:
                pass

    app.is_client_connected = True
    try:
        async for song_details in websocket:
            app.get_lyrics(loads(song_details))
            app.set_lyrics()
    finally:
        app.is_client_connected = False


async def start_websocket_server(app):
    try:
        server = await websockets.serve(lambda ws, p: websocket_handler(ws, p, app), "localhost", 8765)
        await server.wait_closed()
    except OSError:
        app.stop()


def start_kivy_app(event_loop):
    asyncio.set_event_loop(event_loop)
    app = MusicLawApp()
    app.loop = loop
    app.websocket_server_task = asyncio.run_coroutine_threadsafe(start_websocket_server(app), loop)

    loop.run_until_complete(app.async_run(async_lib='asyncio'))


if __name__ == '__main__':
    if hasattr(sys, '_MEIPASS'):
        resource_add_path(join(sys._MEIPASS))  # NOQA

    loop = asyncio.get_event_loop()

    try:
        start_kivy_app(loop)
    except KeyboardInterrupt:
        pass
