from kivy.config import Config
import sys
import ctypes
import asyncio
import unicodedata
import websockets
from json import loads
from os.path import join
from pyautogui import position
from unidecode import unidecode
from ytmusicapi import YTMusic

# Miscellaneous Kivy imports
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.logger import Logger
from kivy.resources import resource_add_path

# Kivy's properties imports
from kivy.properties import ObjectProperty

# Kivy's UI imports
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition


Config.set("input", "mouse", "mouse,multitouch_on_demand")  # disable multitouch
Config.set("graphics", "borderless", "1")  # remove title bar
Config.set("graphics", "resizable", "0")
Config.set("graphics", "width", "142")
Config.set("graphics", "height", "30")
Config.set("graphics", "always_on_top", "1")
Config.set("graphics", "show_taskbar_icon", "0")


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
            Window.left = self.initial_left + pos[0] - self.initial_x
            Window.top = self.initial_top + pos[1] - self.initial_y

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
        self.lyrics_not_found = (
            False  # flag to handle the case of lyrics not being available
        )

        self.current_song = None  # to keep record of currently playing song and fetch lyrics only when changed
        self.current_duration = None
        self.ytmusic = YTMusic()
        self.current_video_id = None
        self.last_displayed_lyric = None

        self.overlay_screen = None
        self.screen_manager = CustomScreenManager(transition=NoTransition())

    def lyrics_unavailable(self, *args):  # NOQA
        self.lyrics_not_found = True

    @staticmethod
    def sanitize_lyric_text(text: str) -> str:
        sanitized = unicodedata.normalize("NFKC", text or "")
        sanitized = sanitized.replace("�", "")
        for symbol in ["♪", "♫", "♬", "♩"]:
            sanitized = sanitized.replace(symbol, "")

        # Remove non-printable/control characters that often render as invalid glyphs.
        return "".join(char for char in sanitized if char.isprintable()).strip()

    def create_lyrics_mappings(self, lyrics_data) -> None:
        if not isinstance(lyrics_data, dict):
            self.lyrics_not_found = True
            return

        timed_lyrics = lyrics_data.get("lyrics")
        if lyrics_data.get("hasTimestamps") and isinstance(timed_lyrics, list):
            for line in timed_lyrics:
                lyric_text = self.sanitize_lyric_text(getattr(line, "text", ""))
                start_time = getattr(line, "start_time", None)

                if not lyric_text or not isinstance(start_time, int):
                    continue

                self.lyrics[max(0, start_time // 1000)] = lyric_text
        elif isinstance(timed_lyrics, str):
            # Fallback for tracks without synced lyrics.
            lines = [
                self.sanitize_lyric_text(line)
                for line in timed_lyrics.splitlines()
                if line.strip()
            ]
            for index, line in enumerate(lines):
                if not line:
                    continue
                self.lyrics[index * 4] = line

        if len(self.lyrics) == 0:
            self.lyrics_not_found = True
            return

        current_line = "Music LAW"
        end_second = max(self.lyrics.keys())
        try:
            end_second = max(end_second, int(float(self.current_duration)) + 1)
        except (ValueError, TypeError):
            pass

        for second in range(end_second + 1):
            try:
                current_line = self.lyrics[second]
            except KeyError:
                self.lyrics[second] = current_line

        preview = [self.lyrics[key] for key in sorted(self.lyrics.keys())[:5]]
        Logger.info(
            f"MusicLAW: Lyrics loaded total={len(self.lyrics)} has_timestamps={lyrics_data.get('hasTimestamps')} preview={preview}"
        )

    @staticmethod
    def get_search_query(song_name: str, song_info: str) -> tuple[str, str]:
        clean_song_name = ""
        clean_song_info = ""

        if song_name:
            song_name = (
                song_name.replace("feat.", "")
                .replace("original motion picture soundtrack", "")
                .replace("from the original motion picture", "")
            )
            clean_song_name = "".join(
                char for char in song_name if char.isalnum() or char.isspace()
            )

        if song_info:
            song_info = (
                song_info.replace("feat.", "")
                .replace("original motion picture soundtrack", "")
                .replace("from the original motion picture", "")
            )
            clean_song_info = "".join(
                char for char in song_info if char.isalnum() or char.isspace()
            )

        clean_song_name = unidecode(clean_song_name).strip()
        clean_song_info = unidecode(clean_song_info).strip()

        for sep in ["•", "|", "-"]:
            if sep in clean_song_info:
                clean_song_info = clean_song_info.split(sep, 1)[0].strip()
                break

        if clean_song_name and clean_song_info:
            title_words = set(clean_song_name.lower().split())
            info_words = [
                word
                for word in clean_song_info.split()
                if word.lower() not in title_words
                and word.lower() not in {"remix", "remixes"}
            ]
            cleaned_artist = " ".join(info_words).strip()
            if cleaned_artist:
                clean_song_info = cleaned_artist

        return clean_song_name, clean_song_info

    @staticmethod
    def choose_song_result(results, song_name: str, song_artist: str):
        if not isinstance(results, list) or len(results) == 0:
            return None

        song_name = song_name.lower().strip()
        song_artist = song_artist.lower().strip()

        best_result = results[0]
        best_score = -1

        for result in results:
            score = 0
            title = str(result.get("title", "")).lower()
            artists = " ".join(
                artist.get("name", "")
                for artist in result.get("artists", [])
                if isinstance(artist, dict)
            ).lower()

            if song_name and (song_name in title or title in song_name):
                score += 3
            if song_artist and song_artist in artists:
                score += 2

            if score > best_score:
                best_result = result
                best_score = score

        return best_result

    def get_lyrics_by_video_id(self, video_id: str):
        watch_playlist = self.ytmusic.get_watch_playlist(videoId=video_id)
        lyrics_browse_id = watch_playlist.get("lyrics")
        if not lyrics_browse_id:
            Logger.info(f"MusicLAW: No lyrics browse id for videoId={video_id}")
            return None

        Logger.info(
            f"MusicLAW: Fetching lyrics via videoId={video_id}, lyricsBrowseId={lyrics_browse_id}"
        )
        return self.ytmusic.get_lyrics(lyrics_browse_id, timestamps=True)

    # Method to fetch the lyrics based on the song details sent by Chromium extension
    def get_lyrics(self, song_details) -> None:
        required_fields = ["songName", "songArtistsAndAlbum", "currentDuration"]
        if any(song_details.get(field) is None for field in required_fields):
            return

        self.current_duration = song_details["currentDuration"]
        incoming_video_id = song_details.get("videoId")

        song_name = song_details["songName"].lower()
        song_artists_and_album = song_details["songArtistsAndAlbum"].lower()

        song = f"{song_name} - {song_artists_and_album} - {incoming_video_id or ''}"
        if (
            song != self.current_song
        ):  # don't fetch lyrics again until the track is changed
            self.current_song = song
            self.current_video_id = incoming_video_id
            self.last_displayed_lyric = None

            self.lyrics.clear()
            self.lyrics_not_found = False

            clean_song_name, clean_song_artist = self.get_search_query(
                song_name, song_artists_and_album
            )
            if not clean_song_name:
                return

            query = clean_song_name
            if clean_song_artist:
                query = f"{clean_song_name} {clean_song_artist}"

            try:
                video_id = incoming_video_id
                if not video_id:
                    results = self.ytmusic.search(query=query, filter="songs", limit=5)
                    best_result = self.choose_song_result(
                        results, clean_song_name, clean_song_artist
                    )
                    if not best_result:
                        self.lyrics_not_found = True
                        return

                    video_id = best_result.get("videoId")
                if not video_id:
                    self.lyrics_not_found = True
                    return

                lyrics_data = self.get_lyrics_by_video_id(video_id)
                if not lyrics_data and incoming_video_id:
                    # Fallback to search result if direct videoId lookup has no lyrics.
                    results = self.ytmusic.search(query=query, filter="songs", limit=5)
                    best_result = self.choose_song_result(
                        results, clean_song_name, clean_song_artist
                    )
                    fallback_video_id = (
                        best_result.get("videoId") if best_result else None
                    )
                    if fallback_video_id and fallback_video_id != incoming_video_id:
                        lyrics_data = self.get_lyrics_by_video_id(fallback_video_id)

                if not lyrics_data:
                    self.lyrics_not_found = True
                    return

                self.create_lyrics_mappings(lyrics_data)
            except Exception as error:
                Logger.exception(f"MusicLAW: Failed to fetch lyrics: {error}")
                self.lyrics_unavailable()

    def set_lyrics(self) -> None:
        if self.lyrics_not_found:
            self.overlay_screen.lyric.text = "Lyrics not found"
        elif len(self.lyrics) == 0:
            self.overlay_screen.lyric.text = "Music LAW"
        else:
            try:
                lyric = self.lyrics[int(self.current_duration)]
                lyric = self.sanitize_lyric_text(lyric)
                self.overlay_screen.lyric.text = lyric
                if lyric and lyric != self.last_displayed_lyric:
                    self.last_displayed_lyric = lyric
                    Logger.info(
                        f"MusicLAW: Current lyric t={self.current_duration}s text={lyric}"
                    )
            except (KeyError, ValueError, TypeError):
                pass

        self.overlay_screen.lyric.texture_update()

    @staticmethod
    def hide_taskbar_icon(*args):  # NOQA
        hwnd = Window.get_window_info().window

        # Hide the taskbar icon by removing the WS_EX_APPWINDOW style
        # and adding the WS_EX_TOOLWINDOW style
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE = -20
        style = (
            style & ~0x00040000 | 0x00000080
        )  # WS_EX_APPWINDOW = 0x00040000, WS_EX_TOOLWINDOW = 0x00000080
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)

        # Update the window to apply the new style
        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020
        )

    def on_start(self):
        self.overlay_screen = self.screen_manager.get_screen("Lyrics Overlay")
        self.hide_taskbar_icon()

    # def on_stop(self):
    #     self.websocket_server_task.cancel()  # NOQA

    def build(self):
        self.icon = "icon.png"
        self.title = "Music LAW - Lyrics AnyWhere"

        self.screen_manager.add_widget(LyricsOverlayScreen())
        return self.screen_manager


async def websocket_handler(websocket, app):
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
        server = await websockets.serve(
            lambda ws: websocket_handler(ws, app), "127.0.0.1", 8765
        )
        await server.wait_closed()
    except OSError:
        app.stop()
    except asyncio.CancelledError:
        pass


async def start_kivy_app(app, websocket_server_task):
    await app.async_run()
    websocket_server_task.cancel()


def main():
    app = MusicLawApp()
    websocket_server_task = asyncio.ensure_future(start_websocket_server(app))
    return asyncio.gather(
        start_kivy_app(app, websocket_server_task), websocket_server_task
    )


if __name__ == "__main__":
    if hasattr(sys, "_MEIPASS"):
        resource_add_path(join(sys._MEIPASS))  # NOQA

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
