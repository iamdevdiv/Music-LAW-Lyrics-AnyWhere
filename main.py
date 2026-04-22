from kivy.config import Config

Config.set("input", "mouse", "mouse,multitouch_on_demand")  # disable multitouch
Config.set("graphics", "borderless", "1")  # remove title bar
Config.set("graphics", "resizable", "0")
Config.set("graphics", "width", "142")
Config.set("graphics", "height", "30")
Config.set("graphics", "always_on_top", "1")
Config.set("graphics", "show_taskbar_icon", "0")

import sys
from os.path import join
from kivy.resources import resource_add_path

if hasattr(sys, '_MEIPASS'):
    resource_add_path(join(sys._MEIPASS))  # NOQA

from kivy.core.text import LabelBase
LabelBase.register(name="NotoLatin", fn_regular="fonts/NotoSans-Regular.ttf")
LabelBase.register(name="NotoJP", fn_regular="fonts/NotoSansJP-Regular.ttf")
LabelBase.register(name="NotoKR", fn_regular="fonts/NotoSansKR-Regular.ttf")
LabelBase.register(name="NotoDEV", fn_regular="fonts/NotoSansDevanagari-Regular.ttf")
LabelBase.register(name="NotoAR", fn_regular="fonts/NotoSansArabic-Regular.ttf")
LabelBase.register(name="NotoGUR", fn_regular="fonts/NotoSansGurmukhi-Regular.ttf")
LabelBase.register(name="NotoGUJ", fn_regular="fonts/NotoSansGujarati-Regular.ttf")
LabelBase.register(name="NotoTAM", fn_regular="fonts/NotoSansTamil-Regular.ttf")
LabelBase.register(name="NotoTEL", fn_regular="fonts/NotoSansTelugu-Regular.ttf")
LabelBase.register(name="NotoKAN", fn_regular="fonts/NotoSansKannada-Regular.ttf")
LabelBase.register(name="NotoMAL", fn_regular="fonts/NotoSansMalayalam-Regular.ttf")
LabelBase.register(name="NotoORI", fn_regular="fonts/NotoSansOriya-Regular.ttf")
LabelBase.register(name="NotoBEN", fn_regular="fonts/NotoSansBengali-Regular.ttf")

import regex
import ctypes
import asyncio
import websockets

from json import loads
from pyautogui import position
from urllib.parse import quote

# Miscellaneous Kivy imports
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.network.urlrequest import UrlRequest
from kivy.metrics import dp
from kivy.core.text import Label as CoreLabel

# Kivy's properties imports
from kivy.properties import ObjectProperty, BooleanProperty, StringProperty, NumericProperty

# Kivy's UI imports
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition

# Change Kivy window background color and opacity
Window.clearcolor = (16 / 255, 23 / 255, 32 / 255, 1)
Window.opacity = 0.9


class TooltipBehavior:
    tooltip_text = StringProperty("")
    tooltip_delay = NumericProperty(1.5)
    # "auto" chooses based on widget position, otherwise "left"/"right".
    tooltip_side = StringProperty("auto")
    # Safety cap: maximum tooltip height as a fraction of Window.height.
    # Set to 0 to disable clamping.
    tooltip_max_height_ratio = NumericProperty(0.7)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tooltip_hovered = False
        self._tooltip_visible = False
        self._tooltip_ev = None
        self._tooltip_bound = False
        self._tooltip_poll_ev = None
        self._tooltip_pressed = False

    def on_parent(self, instance, parent):
        # Bind/unbind mouse tracking based on whether the widget is in the tree.
        if parent is None:
            if self._tooltip_bound:
                Window.unbind(mouse_pos=self._on_tooltip_mouse_pos)
                Window.unbind(on_focus=self._on_tooltip_window_focus)
                # Not all Window providers implement this event; safe to unbind.
                Window.unbind(on_cursor_leave=self._on_tooltip_cursor_leave)
                self._tooltip_bound = False
            self._tooltip_cancel()
            self._tooltip_hide()
        else:
            if not self._tooltip_bound:
                Window.bind(mouse_pos=self._on_tooltip_mouse_pos)
                Window.bind(on_focus=self._on_tooltip_window_focus)
                try:
                    Window.bind(on_cursor_leave=self._on_tooltip_cursor_leave)
                except Exception:
                    # If the provider doesn't support cursor leave events, we still
                    # handle most cases via mouse_pos hover tracking.
                    pass
                self._tooltip_bound = True

    def _on_tooltip_window_focus(self, window, focused: bool):
        if not focused:
            self._tooltip_hovered = False
            self._tooltip_pressed = False
            self._tooltip_cancel()
            self._tooltip_hide()

    def _on_tooltip_cursor_leave(self, *args):  # NOQA
        self._tooltip_hovered = False
        self._tooltip_pressed = False
        self._tooltip_cancel()
        self._tooltip_hide()

    def on_touch_down(self, touch):
        if getattr(touch, "button", "left") == "left" and self.collide_point(*touch.pos):
            # If user clicks (e.g. to drag), do not allow delayed tooltip to appear.
            self._tooltip_pressed = True
            self._tooltip_hovered = False
            self._tooltip_cancel()
            self._tooltip_hide()
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if getattr(touch, "button", "left") == "left":
            self._tooltip_pressed = False
        return super().on_touch_up(touch)

    def _tooltip_cancel(self) -> None:
        if self._tooltip_ev is not None:
            self._tooltip_ev.cancel()
            self._tooltip_ev = None

        if self._tooltip_poll_ev is not None:
            self._tooltip_poll_ev.cancel()
            self._tooltip_poll_ev = None

    def _find_tooltip_widget(self):
        node = self
        while node is not None:
            ids = getattr(node, "ids", None)
            if ids and "tooltip" in ids:
                return ids["tooltip"]
            node = node.parent
        return None

    def _on_tooltip_mouse_pos(self, window, pos):
        if not self.get_root_window():
            return

        if self._tooltip_pressed:
            return

        # Avoid tooltips for hidden/disabled buttons.
        if self.opacity <= 0 or self.width <= 1 or self.height <= 1:
            if self._tooltip_hovered or self._tooltip_visible:
                self._tooltip_hovered = False
                self._tooltip_cancel()
                self._tooltip_hide()
            return

        inside = self.collide_point(*self.to_widget(*pos))
        if inside:
            if not self._tooltip_hovered:
                self._tooltip_hovered = True
                self._tooltip_cancel()
                if self.tooltip_text:
                    if self.tooltip_delay <= 0:
                        self._tooltip_show(0)
                    else:
                        self._tooltip_ev = Clock.schedule_once(self._tooltip_show, self.tooltip_delay)
        else:
            if self._tooltip_hovered or self._tooltip_visible:
                self._tooltip_hovered = False
                self._tooltip_cancel()
                self._tooltip_hide()

    def _tooltip_show(self, dt):
        if self._tooltip_pressed or (not self._tooltip_hovered) or (not self.tooltip_text):
            return

        tooltip = self._find_tooltip_widget()
        if tooltip is None or tooltip.parent is None:
            return

        tooltip.text = self.tooltip_text
        tooltip.opacity = 1

        # Measure inner label texture (TooltipBubble is a container).
        inner = None
        ids = getattr(tooltip, "ids", None)
        if ids:
            inner = ids.get("t")
        if inner is None:
            return

        inner.texture_update()

        pad_x = tooltip.padding_x
        pad_y = tooltip.padding_y

        buffer_y = dp(2)
        tooltip.size = inner.texture_size[0] + (pad_x * 2), inner.texture_size[1] + (pad_y * 2) + buffer_y

        # Clamp height (safety net) so it never grows to full window height.
        ratio = float(getattr(self, "tooltip_max_height_ratio", 0.0) or 0.0)
        if ratio > 0:
            max_h = max(0.0, Window.height * ratio)
            if tooltip.height > max_h:
                tooltip.height = max_h

        # Start polling so we reliably hide when the mouse leaves the window.
        self._tooltip_poll_ev = Clock.schedule_interval(self._tooltip_poll, 0.1)

        parent = tooltip.parent
        gap = dp(6)

        # Convert the hovered widget bounds into tooltip-parent coordinates.
        wx0, wy0 = self.to_window(self.x, self.y)
        wx1, wy1 = self.to_window(self.right, self.top)
        px0, py0 = parent.to_widget(wx0, wy0)
        px1, py1 = parent.to_widget(wx1, wy1)

        side = self.tooltip_side
        if side == "auto":
            side = "right" if (self.center_x < Window.width * 0.5) else "left"

        if side == "right":
            x = px1 + gap
        else:
            x = px0 - tooltip.width - gap
        y = ((py0 + py1) * 0.5) - (tooltip.height * 0.5)

        # Clamp to stay on-screen.
        x = max(0, min(x, parent.width - tooltip.width))
        y = max(0, min(y, parent.height - tooltip.height))
        tooltip.pos = x, y
        self._tooltip_visible = True

    def _tooltip_hide(self) -> None:
        tooltip = self._find_tooltip_widget()
        if tooltip is not None:
            tooltip.opacity = 0
            tooltip.text = ""
        self._tooltip_visible = False

    def _tooltip_poll(self, dt):
        # Hide tooltips when window loses focus or when cursor is outside the window.
        if not Window.focus:
            self._tooltip_hovered = False
            self._tooltip_cancel()
            self._tooltip_hide()
            return False

        x, y = Window.mouse_pos
        if x < 0 or y < 0 or x > Window.width or y > Window.height:
            self._tooltip_hovered = False
            self._tooltip_cancel()
            self._tooltip_hide()
            return False

        # Continue polling only while visible/hovered.
        return self._tooltip_visible or self._tooltip_hovered


def detect_script(text: str) -> str:
    if regex.search(r'\p{Hiragana}|\p{Katakana}|\p{Han}', text):
        return "JP"
    if regex.search(r'\p{Hangul}', text):
        return "KR"
    if regex.search(r'\p{Devanagari}', text):
        return "DEV"
    if regex.search(r'\p{Gurmukhi}', text):
        return "GUR"
    if regex.search(r'\p{Gujarati}', text):
        return "GUJ"
    if regex.search(r'\p{Tamil}', text):
        return "TAM"
    if regex.search(r'\p{Telugu}', text):
        return "TEL"
    if regex.search(r'\p{Kannada}', text):
        return "KAN"
    if regex.search(r'\p{Malayalam}', text):
        return "MAL"
    if regex.search(r'\p{Oriya}', text):
        return "ORI"
    if regex.search(r'\p{Bengali}', text):
        return "BEN"
    if regex.search(r'\p{Arabic}', text):
        return "AR"
    return "LATIN"


class IconButton(TooltipBehavior, ButtonBehavior, Image):  # button with icon representation
    pass


class RotatingImage(Image):
    angle = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.start_rotation()

    def start_rotation(self) -> None:
        """Start endless rotation.

        Note: Kivy's canvas Rotate uses positive angles as counter-clockwise.
        To rotate clockwise, we decrement the angle (negative speed).
        """
        duration = 0.9
        degrees_per_second = -abs(360.0 / duration)

        self._degrees_per_second = degrees_per_second
        Clock.schedule_interval(self._tick_rotation, 0)

    def _tick_rotation(self, dt: float) -> None:
        self.angle = (self.angle + (self._degrees_per_second * dt)) % 360.0


class AlignButton(IconButton):
    window_center_x = None
    window_right = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.alignment = "left"  # default alignment
        self.icons = {
            "left": "images/align-left.png",
            "center": "images/align-center.png",
            "right": "images/align-right.png"
        }
        self.center_trigger = None
        self.right_trigger = None

    def toggle_alignment(self):
        # Stop any active triggers
        self.stop_triggers()
        
        # Cycle through alignments: left -> center -> right -> left
        if self.alignment == "left":
            self.alignment = "center"
        elif self.alignment == "center":
            self.alignment = "right"
        else:
            self.alignment = "left"
        
        # Update the icon
        self.source = self.icons[self.alignment]
        
        # Update the app's current alignment
        App.get_running_app().current_alignment = self.alignment

    def stop_triggers(self):
        """Stop any active alignment triggers"""
        if self.center_trigger:
            self.center_trigger.cancel()
            self.center_trigger = None
        if self.right_trigger:
            self.right_trigger.cancel()
            self.right_trigger = None

    def create_center_trigger(self):
        """Create and start the center alignment trigger"""
        self.stop_triggers()  # Stop any existing triggers

        AlignButton.window_center_x = Window.left + (Window.width / 2)
        self.center_trigger = Clock.create_trigger(lambda dt: self.align_window_center(), 0, True)
        self.center_trigger()

    def create_right_trigger(self):
        """Create and start the right alignment trigger"""        
        self.stop_triggers()  # Stop any existing triggers

        AlignButton.window_right = Window.left + Window.width
        self.right_trigger = Clock.create_trigger(lambda dt: self.align_window_right(), 0, True)
        self.right_trigger()

    def align_window_center(self):
        """Set window position for center alignment"""
        drag_button_1 = App.get_running_app().overlay_screen.drag_button_1
        drag_button_2 = App.get_running_app().overlay_screen.drag_button_2
        if drag_button_1.drag_enabled or drag_button_2.drag_enabled:
            return
        
        Window.left = AlignButton.window_center_x - (Window.width / 2)

    def align_window_right(self):
        """Set window position for right alignment"""
        drag_button_1 = App.get_running_app().overlay_screen.drag_button_1
        drag_button_2 = App.get_running_app().overlay_screen.drag_button_2
        if drag_button_1.drag_enabled or drag_button_2.drag_enabled:
            return
        
        Window.left = AlignButton.window_right - Window.width

    def update_alignment_positions(self):
        """Update alignment positions after drag button is released"""
        if App.get_running_app().is_expanded:
            return
        
        AlignButton.window_center_x = Window.left + (Window.width / 2)
        AlignButton.window_right = Window.left + Window.width


# Button to mimic the title bar's drag behaviour for moving the Kivy window around
class DragButton(IconButton):
    def __init__(self, **kwargs):
        self.drag_enabled = False
        self.initial_x = 0  # to store the initial x position of mouse
        self.initial_y = 0  # to store the initial y position of mouse
        self.initial_left = 0  # to store the initial left position of Kivy window
        self.initial_right = 0  # to store the initial right position of Kivy window
        self.initial_top = 0  # to store the initial top position of Kivy window

        self.window_right = None
        self.retain_window_right_trigger = Clock.create_trigger(lambda dt: self.retain_window_right(), 0, True)

        super().__init__(**kwargs)

    def on_press(self):
        pos = position()
        self.initial_x = pos[0]
        self.initial_y = pos[1]
        self.initial_left = Window.left
        self.initial_right = Window.left + Window.width
        self.initial_top = Window.top

        if self == App.get_running_app().overlay_screen.drag_button_2:
            self.window_right = Window.left + Window.width
            self.retain_window_right_trigger()

        self.drag_enabled = True

    def on_touch_move(self, touch):
        if self.drag_enabled:
            pos = position()

            app = App.get_running_app()
            is_expanded = app.is_expanded

            if is_expanded:
                # Expanded: allow only vertical drag.
                Window.left = self.initial_left
            else:
                if self == App.get_running_app().overlay_screen.drag_button_1:
                    Window.left = (self.initial_left + pos[0] - self.initial_x)
                else:
                    Window.left = self.initial_right - Window.width + pos[0] - self.initial_x

            Window.top = (self.initial_top + pos[1] - self.initial_y)
            self.window_right = Window.left + Window.width

    def on_touch_up(self, touch):
        self.drag_enabled = False
        self.retain_window_right_trigger.cancel()

        # Update alignment positions after dragging
        align_button = App.get_running_app().overlay_screen.align_button
        align_button.update_alignment_positions()
    
    def retain_window_right(self):
        Window.left = self.window_right - Window.width


# The simple screen to show the synced lyrics and options to move or close the window
class LyricsOverlayScreen(Screen):
    lyric = ObjectProperty()
    align_button = ObjectProperty()
    drag_button_1 = ObjectProperty()
    drag_button_2 = ObjectProperty()
    settings_button = ObjectProperty()
    exit_button = ObjectProperty()

    window_focused = BooleanProperty(True)
    button_size = dp(Window.height * 0.8), dp(Window.height)

    def __init__(self):
        super().__init__(name="Lyrics Overlay")

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)

        # Makes the buttons visible when window is focused,
        # and turns invisible when window is not in focus.
        # Schedule after KV is applied so `ids` are populated.
        Clock.schedule_interval(self.set_window_focused, 0)

    def update_window_center_x(self):
        Window.left = AlignButton.window_center_x - (Window.width / 2)

    def update_window_right(self):
        Window.left = AlignButton.window_right - Window.width

    def set_window_focused(self, dt=None):
        if Window.focus:
            self.window_focused = True
        else:
            self.window_focused = False
        
        drag_button_1 = self.ids.get("drag_button_1")
        drag_button_2 = self.ids.get("drag_button_2")
        if not drag_button_1 or not drag_button_2:
            return

        if drag_button_1.drag_enabled or drag_button_2.drag_enabled:
            return
        
        # When expanded, do not auto-adjust horizontal alignment.
        app = App.get_running_app()
        if not app.is_expanded:
            if app.current_alignment == "center":
                self.update_window_center_x()
            elif app.current_alignment == "right":
                self.update_window_right()
        
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
    overlay_screen = None
    current_alignment = StringProperty("left")  # track current alignment state
    is_expanded = BooleanProperty(False)
    is_loading = BooleanProperty(False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Cache for text-width measurements used by the loader positioning.
        # Key: (text, font_name, font_size) -> width
        self._text_width_cache: dict[tuple[str, str, float], float] = {}

        # Flag to block lyrics interference if a YT Music tab is sending lyrics data and additional tabs are opened
        self.is_client_connected = False

        self.lyrics = {}  # to store lyrics fetched from the API
        self.lyrics_not_found = False  # flag to handle the case of lyrics not being available
        self.is_instrumental = False  # LRCLIB can mark tracks as instrumental
        self.previous_text = ""  # to keep record of previously shown lyrics text

        self.current_song = None  # to keep record of currently playing song and fetch lyrics only when changed
        self.total_duration = None
        self.current_duration = None

        self.old_window_width = Window.width
        self.old_window_left = Window.left
        self.old_window_size = Window.size

        self.screen_manager = CustomScreenManager(transition=NoTransition())
        
    def lyrics_unavailable(self, *args):  # NOQA
        self.is_loading = False
        self.lyrics_not_found = True
        self.is_instrumental = False

    @staticmethod
    def parse_synced_lyrics(lyrics_str: str) -> dict:
        """
        Parse [mm:ss.xx] lines and, for timestamps having multiple lines
        (original + romanization), pick the original line:
        - prefer any line containing non-Latin script characters
            (Han/Hiragana/Katakana/Devanagari/Gurmukhi/Arabic/Cyrillic/etc.)
        - if none, pick the first line
        - ignore empty lines and pure musical markers like '♪'
        Returns: dict(seconds -> chosen line)
        """
        # pattern to capture a timestamp and the following text
        # Accept [mm:ss], [mm:ss.xx], or [mm:ss.xxx]
        line_pattern = r'^\s*\[(\d{2}):(\d{2})(?:\.(\d{1,3}))?\](.*)$'
        # regex that matches many non-Latin scripts (so we consider that "original")
        non_latin_script_re = (r'\p{Han}|\p{Hiragana}|\p{Katakana}|'      # CJK / Japanese
                            r'\p{Hangul}|'                           # Korean
                            r'\p{Devanagari}|\p{Gurmukhi}|\p{Gujarati}|'  # Indic
                            r'\p{Tamil}|\p{Telugu}|\p{Kannada}|\p{Malayalam}|\p{Oriya}|\p{Bengali}|' 
                            r'\p{Arabic}|\p{Hebrew}|\p{Cyrillic}')

        groups = {}  # seconds_float -> list of candidate lines (preserve order)
        for raw_line in lyrics_str.splitlines():
            m = regex.match(line_pattern, raw_line)
            if not m:
                continue
            mm = int(m.group(1))
            ss = int(m.group(2))
            ms_raw = m.group(3)
            ms = int(ms_raw) if ms_raw else 0
            ms /= 10 ** len(ms_raw) if ms_raw else 1

            # Convert to integer seconds (nearest) so the rest of the app can index by `int(current_duration)`.
            total_seconds = int((mm * 60 + ss + ms) + 0.5)
            text = m.group(4).strip()

            # ignore empty text
            if not text:
                continue
            # ignore pure musical markers like single ♪ or sequences of ♪
            if text.strip() == "♪":
                continue

            groups.setdefault(total_seconds, []).append(text)

        chosen = {}
        for sec, candidates in groups.items():
            # If only one candidate, choose it
            if len(candidates) == 1:
                chosen[sec] = candidates[0]
                continue

            # Remove exact duplicate candidates (keep first occurrence)
            uniq = []
            seen = set()
            for c in candidates:
                if c not in seen:
                    uniq.append(c)
                    seen.add(c)
            candidates = uniq

            # Prefer the first candidate that contains non-latin script characters
            non_latin_candidates = [c for c in candidates if regex.search(non_latin_script_re, c)]
            if non_latin_candidates:
                # if more than one non-latin candidate, pick the longest (heuristic) or first
                chosen[sec] = max(non_latin_candidates, key=len)
                continue

            # If none contain non-latin scripts, try to detect romanization pattern:
            # romaji often is all-ASCII letters (a-z) and spaces, maybe punctuation.
            # But we assume in that case the first candidate is the original (English or Latin).
            chosen[sec] = candidates[0]

        return chosen

    def create_lyrics_mappings(self, req, res) -> None:  # NOQA
        self.is_loading = False
        # LRCLIB may return an "instrumental" flag.
        # If true, always show "Instrument" instead of lyrics.
        self.is_instrumental = bool(res.get("instrumental"))
        if self.is_instrumental:
            self.lyrics.clear()
            self.lyrics_not_found = False
            return

        if not res.get("syncedLyrics"):
            self.lyrics_not_found = True
            return
        
        self.lyrics = self.parse_synced_lyrics(res["syncedLyrics"])

        # Some tracks return syncedLyrics that we can't parse (timestamp format variants).
        # Treat as unavailable rather than crashing.
        if not self.lyrics:
            self.lyrics_not_found = True
            return

        current_line = "Music LAW"
        last_second = max(self.lyrics.keys())
        for second in range(last_second + 1):
            try:
                current_line = self.lyrics[second]
            except KeyError:
                self.lyrics[second] = current_line

    @staticmethod
    def get_lyrics_url(song_name: str, artists: list[str], total_duration: int) -> str:
        return (f"https://lrclib.net/api/get"
            f"?track_name={quote(song_name)}"
            f"&artist_name={quote(', '.join(artists))}"
            f"&duration={total_duration}")

    @staticmethod
    def normalize_artists(artist_string: str) -> list[str]:
        # Split by comma, ampersand, or ' and '
        parts = regex.split(r",|&| and ", artist_string, flags=regex.IGNORECASE)
        return [a.strip() for a in parts if a.strip()]

    @staticmethod
    def normalize_song_names(song_name: str) -> list[str]:
        """
        Generate fallback song-name variants for LRCLIB.
        Order matters: earlier = higher priority.
        """
        variants = []

        original = song_name.strip()
        variants.append(original)

        # Remove parentheses and brackets
        no_parens = regex.sub(r"\s*[\(\[].*?[\)\]]", "", original).strip()
        if no_parens and no_parens != original:
            variants.append(no_parens)

        # Remove feat / ft / featuring
        no_feat = regex.split(r"\s+(ft\.?|feat\.?|featuring)\s+", no_parens, flags=regex.IGNORECASE)[0].strip()
        if no_feat and no_feat != no_parens:
            variants.append(no_feat)

        # Remove dash / hyphen suffix
        no_dash = regex.split(r"\s*[-–—]\s*", no_feat)[0].strip()
        if no_dash and no_dash != no_feat:
            variants.append(no_dash)

        # First 3 words fallback
        words = no_dash.split()
        if len(words) > 3:
            variants.append(" ".join(words[:3]))

        # De-duplicate while preserving order
        seen = set()
        final = []
        for v in variants:
            if v.lower() not in seen:
                seen.add(v.lower())
                final.append(v)

        return final
    
    def try_lyrics_requests(self, song_name: str, artist_string: str, total_duration: int, callback, on_fail):
        """
        Try multiple (song_name x artist) combinations until LRCLIB returns lyrics.
        """

        # Show loader while we are making network requests.
        self.is_loading = True

        def _success(req, res):
            self.is_loading = False
            callback(req, res)

        def _fail(*args):
            self.is_loading = False
            on_fail(*args)

        song_attempts = self.normalize_song_names(song_name)
        artists = self.normalize_artists(artist_string)

        # Artist fallback combinations
        artist_attempts = []
        for i in range(len(artists)):
            artist_attempts.append(artists[:len(artists) - i])
        if artists:
            artist_attempts.append([artists[0]])

        # Cartesian product: song × artist
        attempts = []
        for s in song_attempts:
            for a in artist_attempts:
                attempts.append((s, a))

        def try_next(attempts_left):
            if not attempts_left:
                _fail()
                return

            song_try, artist_try = attempts_left.pop(0)
            url = self.get_lyrics_url(song_try, artist_try, total_duration)
            print(url)
            print(f"Trying → song='{song_try}' | artists='{', '.join(artist_try)}'")

            UrlRequest(
                url,
                on_success=_success,
                on_failure=lambda *a: try_next(attempts_left),
                on_error=lambda *a: try_next(attempts_left),
                on_cancel=lambda *a: try_next(attempts_left),
            )

        try_next(attempts)

    # Method to fetch the lyrics based on the song details sent by Chromium extension
    def get_lyrics(self, song_details) -> None:
        if None in song_details.values():
            return

        self.current_duration = song_details["currentDuration"]

        total_duration = song_details["totalDuration"]
        song_name = song_details["songName"].lower()
        song_artists = song_details["songArtists"].lower()

        song = f"{song_name} - {song_artists}"
        if song != self.current_song:  # don't fetch lyrics again until the track is changed
            self.current_song = song

            self.lyrics.clear()
            self.lyrics_not_found = False
            self.is_instrumental = False

            self.try_lyrics_requests(song_name, song_artists, total_duration,
                    self.create_lyrics_mappings,
                    self.lyrics_unavailable)

    def set_lyrics(self) -> None:
        self.start_align_triggers()

        if self.is_instrumental:
            text = "Instrumental"
        elif self.lyrics_not_found:
            text = "Lyrics not found"
        elif len(self.lyrics) == 0:
            text = "Music LAW"
        else:
            try:
                text = self.lyrics[int(self.current_duration)]
                if text == self.previous_text:
                    return
                self.previous_text = text
            except (KeyError, ValueError, TypeError):
                return

        # Detect script + choose font
        script = detect_script(text)
        font_map = {
            "LATIN": "NotoLatin",
            "JP": "NotoJP",
            "KR": "NotoKR",
            "DEV": "NotoDEV",
            "GUR": "NotoGUR",
            "GUJ": "NotoGUJ",
            "TAM": "NotoTAM",
            "TEL": "NotoTEL",
            "KAN": "NotoKAN",
            "MAL": "NotoMAL",
            "ORI": "NotoORI",
            "BEN": "NotoBEN",
            "AR": "NotoAR",
        }

        self.overlay_screen.lyric.text = text
        self.overlay_screen.lyric.font_name = font_map.get(script, "NotoLatin")
        self.overlay_screen.lyric.texture_update()
    
    def start_align_triggers(self) -> None:
        if self.is_expanded:
            return
        
        align_button = self.overlay_screen.ids.get('align_button')
        if self.current_alignment == "center" and not align_button.center_trigger:
            align_button.create_center_trigger()
        elif self.current_alignment == "right" and not align_button.right_trigger:
            align_button.create_right_trigger()

    def toggle_width(self):
        width_toggle_button = self.overlay_screen.ids.get("width_toggle_button")

        if not self.is_expanded:
            # Save current geometry so we can restore it.
            self.old_window_left = Window.left
            self.old_window_size = Window.size

            # Get primary screen width without relying on Kivy.
            screen_width = None
            try:
                import tkinter as tk

                root = tk.Tk()
                root.withdraw()
                screen_width = int(root.winfo_screenwidth())
                root.destroy()
            except Exception:
                screen_width = None

            if not screen_width:
                # Fallback (should rarely happen): keep current width.
                screen_width = int(Window.width)

            align_button = self.overlay_screen.ids.get("align_button")
            align_button.stop_triggers()

            Window.left = 0
            Window.size = (int(screen_width), int(Window.height))
            self.is_expanded = True

            width_toggle_button.source = "images/collapse.png"
        else:
            Window.size = self.old_window_size
            Window.left = self.old_window_left

            self.is_expanded = False

            width_toggle_button.source = "images/expand.png"

    def _measure_text_width(self, text: str, font_name: str, font_size: float) -> float:
        key = (text, font_name, font_size)
        cached = self._text_width_cache.get(key)
        if cached is not None:
            return cached

        lbl = CoreLabel(text=key[0], font_name=font_name, font_size=font_size)
        lbl.refresh()
        width = float(lbl.texture.size[0]) if lbl.texture else 0.0

        # Simple bounded cache to avoid unbounded growth.
        if len(self._text_width_cache) > 128:
            self._text_width_cache.clear()
        self._text_width_cache[key] = width

        return width

    def get_loader_rel_x(self, label, *_deps) -> float:
        """Return loader X relative to the given Label.

        Keeps the loader just to the right of the rendered text, so it stays
        near the text even when the label itself stretches (expanded mode).
        """

        padding_left = label.padding[0]
        padding_right = label.padding[2]
        content_width = label.width - padding_left - padding_right

        text = label.text
        font_name = getattr(label, "font_name", "NotoLatin")
        font_size = label.font_size
        measured_core = self._measure_text_width(text, font_name, font_size)

        halign = label.halign
        free_space = max(0.0, content_width - measured_core)
        if halign == "center":
            offset = free_space / 2.0
        elif halign == "right":
            offset = free_space
        else:
            offset = 0.0

        number_of_buttons = 3
        left_buttons_width = self.overlay_screen.button_size[0] * number_of_buttons
        gap = 4.0
        extra_left = left_buttons_width if Window.focus else 0.0
        x = extra_left + padding_left + offset + measured_core + gap

        # Snap to whole pixels to avoid tiny drift when alignment changes.
        return x

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

    # def on_stop(self):
    #     self.websocket_server_task.cancel()  # NOQA

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
    async def handler(ws):
        await websocket_handler(ws, None, app)
    
    try:
        server = await websockets.serve(handler, "127.0.0.1", 8765)
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
    return asyncio.gather(start_kivy_app(app, websocket_server_task), websocket_server_task)


if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
