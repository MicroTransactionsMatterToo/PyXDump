import curses
import curses.panel
import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import functools
import sys
from typing import Tuple, Any, List
from types import FunctionType
from time import sleep
from typing import Dict, Union, Tuple, Optional
from uuid import uuid4 as uuid
import re
import atexit
import curses
import logging
import traceback


class WindowError(BaseException):
    pass


class ShortcutExistsError(BaseException):
    pass


class ShortcutDeletionError(BaseException):
    pass


class NoWindowsError(BaseException):
    pass


def decode_retrieved_str(data: int) -> Tuple[str, int]:
    """
    Decodes fetched characters from Curses

    Args:
        data (int): The fetched character data

    Returns:
        Tuple[str, int]: A tuple containing the fetched character and attribute code
    """
    character = chr(data & 0xFF)
    attribute = (data >> 8) << 8
    return character, attribute


class ShortcutManager:
    def __init__(self, app: 'App'):
        self.parent = app
        self.shortcuts = {}

    def add_shortcut(self, key: int, handler: functools.partial, close: functools.partial, force: bool = False):
        # Check for existing handler
        if self.shortcuts.get(key) is not None and force:
            raise ShortcutExistsError("Shortcut already assigned. Set force to override existing shortcut")
        else:
            self.shortcuts[key] = handler, close

    def remove_shortcut(self, key: int):
        try:
            del self.shortcuts[key]
        except KeyError:
            pass
        try:
            temp = self.shortcuts[key]
        except KeyError:
            return
        except Exception as e:
            raise ShortcutDeletionError(
                "When checking to see if shortcut was removed, an exception other than KeyError occured") from e
        else:
            raise ShortcutDeletionError("Shortcut could not be deleted")

    def check_shortcuts(self):
        key = self.parent.getch(False)
        if key == -1:
            return
        handler = self.shortcuts.get(key)
        # Close all other shortcut handlers
        for shortcut in self.shortcuts.values():
            if shortcut[1] is not None:
                shortcut[1]()
        if handler is not None:
            handler[0]()
        else:
            curses.ungetch(key)


class App:
    def __init__(self, menubar: bool = False, footerbar: bool = False):
        self.windows = {}  # type: Dict[str, Window]
        self.screen = Screen()
        self.menubar = MenuBar(self) if menubar else None
        self.footerbar = FooterBar(self) if footerbar else None
        self.shortcut_manager = ShortcutManager(self)
        self.keys = {}

    @staticmethod
    @atexit.register
    def _cleanup():
        # Reverse Curses stuff
        curses.cbreak()
        curses.echo()
        curses.endwin()

    def add_new_window(self, name: str, cols: int, lines: int, beg_y: int, beg_x: int, win_id: str = None) -> 'Window':
        line_change = 0
        col_change = 0
        if self.menubar is not None:
            line_change += 1
        if self.footerbar is not None:
            line_change += 1
        nwin = Window(lines - line_change, cols, beg_y + line_change, beg_x, name=name)
        if win_id is not None:
            nwin._uuid = win_id
        self.windows[name] = nwin
        return nwin

    def get_key(self):
        if len(self.windows) != 0:
            return list(self.windows.values())[0].window.getkey()
        if self.footerbar is not None:
            return self.footerbar.window.getkey()
        if self.menubar is not None:
            return self.menubar.window.getkey()
        raise NoWindowsError("No windows were found to fetch key value from")

    def getch(self, blocking=True):
        if len(self.windows) == 0:
            raise NoWindowsError("No windows were found to fetch key value from")
        for window in self.windows.values():
            curses.cbreak(True)
            if blocking:
                window.window.nodelay(False)
                rval = window.window.getch()
            else:
                window.window.nodelay(True)
                curses.cbreak(True)
                try:
                    sleep(0.2)
                    rval = window.window.getch()
                    window.window.nodelay(False)
                    curses.flushinp()
                except curses.error:
                    window.window.nodelay(False)
                    curses.flushinp()
                    return -1
            return rval

    def refresh(self):
        for window in self.windows.values():
            window.refresh()
        if self.menubar is not None:
            self.menubar.refresh()
        if self.footerbar is not None:
            self.footerbar.refresh()
        curses.doupdate()

    def run(self):
        """Core loop that runs everything"""
        while True:
            for window in self.windows.values():
                try:
                    window.draw()
                except NotImplementedError:
                    pass
            self.shortcut_manager.check_shortcuts()
            self.refresh()

    def add_keyboard_shortcut(self, key: int, action: FunctionType):
        pass


class Screen:
    DEFAULT_COLOUR_PAIRS = {
        254: (curses.COLOR_BLACK, curses.COLOR_WHITE),
        255: (curses.COLOR_WHITE, curses.COLOR_BLACK)
    }

    def __init__(self, color_pairs: Dict[int, Tuple[int, int]] = None):
        self._screen = curses.initscr()
        # Setup Curses
        curses.noecho()
        curses.start_color()

        # Setup colour pairs
        if color_pairs is not None:
            for key, value in color_pairs.items():
                curses.init_pair(key, value[0], value[1])
        else:
            for key, value in self.DEFAULT_COLOUR_PAIRS.items():
                curses.init_pair(key, value[0], value[1])
        self._screen.keypad(True)


class Window:
    @classmethod
    def from_derived_window(cls, window, name=None) -> 'Window':
        nwin = cls.__new__(cls)
        nwin.window = window
        nwin._uuid = str(uuid())
        nwin.name = name if name is not None else nwin._uuid
        # Flags and Configuration
        nwin.is_boxed = False
        nwin.sub_windows = {}  # type: Dict[str, Window]
        return nwin

    def __init__(self, lines: int, columns: int, begin_y: int = 0, begin_x: int = 0, name: str = None):
        self.window = curses.newwin(lines, columns, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.window)
        self.window.keypad(True)
        self.window.nodelay(False)
        self._uuid = str(uuid())
        self.name = name if name is not None else self._uuid
        # Flags and Configuration
        self.is_boxed = False
        self.sub_windows = {}  # type: Dict[str, Window]
        self.parent = None

    def __repr__(self) -> str:
        rval = "<Window at {location} with name of {name} and ID of {id}, ({yx})>"
        addr = re.search(r"0x[a-fA-F0-9]+", object.__repr__(self))
        return rval.format(location=addr, name=self.name, id=self._uuid, yx=self.window.getbegyx())

    def refresh(self) -> None:
        """
        Refreshes the underlying data of the Window. To show results on screen, call :code:`curses.doupdate`
        """
        self.window.noutrefresh()
        for window in self.sub_windows.values():
            window.window.noutrefresh()

    def box(self):
        """
        Boxes the window and sets :code:`is_boxed` to :code:`True`
        """
        self.window.box()
        self.is_boxed = True

    def unbox(self):
        """
        Sets the border to space characters and sets :code:`is_boxed` to :code:`False`
        """
        self.window.border(" ", " ", " ", " ", " ", " ", " ")
        self.is_boxed = False

    @property
    def y(self) -> int:
        return self.window.getbegyx()[0]

    @y.setter
    def y(self, value: int):
        self.window.move(value, self.window.getbegyx()[1])

    @property
    def x(self) -> int:
        return self.window.getbegyx()[1]

    @x.setter
    def x(self, value):
        self.window.move(self.window.getbegyx()[0], value)

    @property
    def yx(self) -> Tuple[int, int]:
        return self.window.getbegyx()

    @yx.setter
    def yx(self, value: Tuple[int, int]):
        self.window.move(value[0], value[1])

    def add_str(self, text: str, y: int = None, x: int = None, attr: int = curses.A_NORMAL):
        if y is not None or x is not None:
            if self.is_boxed:
                y += 1
                x += 1
            self.window.addstr(y, x, text, attr)
        else:
            self.window.addstr(text)

    def add_subwindow(self, name: str, cols: int, lines: int, beg_y: int, beg_x: int, win_id: str = None) -> 'Window':
        """
        Adds a subwindow to the current window. :param:`beg_y` and :param:`beg_x` are relative to the parent window
        """
        nwin = self.window.derwin(lines, cols, beg_y, beg_x)
        nwin = Window.from_derived_window(nwin, name)
        nwin.parent = self
        self.sub_windows[name] = nwin
        return nwin

    def remove_subwindow(self, name: str):
        del self.sub_windows[name]

    def erase(self):
        self.window.erase()

    def clear(self):
        self.window.clear()

    def set_background_colour(self, colour_pair_id: int):
        self.window.bkgd(" ", curses.color_pair(colour_pair_id))

    def draw(self):
        raise NotImplementedError("Implement the draw function for your window to implement custom behaviour")


class MenuBar(Window):
    def __init__(self, parent: App, items: List['MenuItem'] = None):
        super(MenuBar, self).__init__(1, curses.COLS, 0, 0, name="menubar")
        self.set_background_colour(254)
        self.parent = parent
        self.items = items if items is not None else []

    def _get_next_x(self) -> int:
        return self.items[-1].end_x if len(self.items) > 0 else 0

    def refresh(self):
        self.draw()
        self.window.noutrefresh()

    def draw(self):
        for menuitem in self.items:
            menuitem.draw()

    def box(self):
        raise WindowError("MenuBars cannot be boxed")

    def unbox(self):
        raise WindowError("MenuBars cannot be boxed")

    def add_item(self, item_name: str, entries: Dict[str, Any], key: str = None):
        key = key if key is not None else item_name[0]
        temp = MenuItem(item_name, key, self._get_next_x(), self, entries)
        self.parent.shortcut_manager.add_shortcut(key, functools.partial(temp.open), functools.partial(temp.close))
        self.items.append(temp)


class FooterBar(Window):
    def __init__(self, parent: App, items: List[Tuple[str, int, FunctionType]] = None):
        super(FooterBar, self).__init__(1, curses.COLS, curses.LINES - 1, 0, name="footerbar")
        self.set_background_colour(254)
        self.items = items if items is not None else []
        self.parent = parent

    def _get_next_x(self) -> int:
        return self.items[-1].end_x if len(self.items) > 0 else 0

    def refresh(self):
        self.draw()
        self.window.noutrefresh()

    def draw(self):
        for menuitem in self.items:
            menuitem.draw()

    def add_item(self, item_name: str, handler: FunctionType, key: int):
        key = key if key is not None else curses.KEY_F63
        temp = FooterItem(item_name, key, self._get_next_x(), self, handler)
        self.parent.shortcut_manager.add_shortcut(key, functools.partial(temp.function))
        self.items.append(temp)


class MenuItem:
    def __init__(self, text: str, key: str, beg_x: int, parent_win: MenuBar, entries: Dict[str, any] = None):
        self.entries = entries if entries is not None else {}
        self.text = text
        self.key = key
        self.beg_x = beg_x
        self.end_x = self.beg_x + len(text) + 4
        self.menu_height = len(entries) + 1
        self.menu_width = max(map(len, self.entries.keys())) + 2
        if self.menu_width < self.end_x - self.beg_x:
            self.menu_width = self.end_x - self.beg_x
        self.panel_win = curses.newwin(self.menu_height, self.menu_width, 1, self.beg_x)
        self.panel_win.bkgd(curses.color_pair(254))
        for y in range(0, self.menu_height - 1):
            self.panel_win.addstr(y, 0, "│")
            self.panel_win.addstr(y, self.menu_width - 1, "│")
        try:
            self.panel_win.addstr(self.menu_height - 1, 0, ("└" + ("─" * (self.menu_width - 2)) + "┘"))
        except curses.error:
            pass
        for line_no, text in zip(range(0, self.menu_height), self.entries.keys()):
            self.panel_win.addstr(line_no, 1, text)
        self.panel_win.noutrefresh()
        self.panel = curses.panel.new_panel(self.panel_win)
        self.panel.hide()
        self.active = False
        self.parent = parent_win
        curses.panel.update_panels()

    def draw(self):
        if self.active:
            self.parent.add_str("  " + self.text + "  ", 0, self.beg_x, attr=curses.color_pair(255))
        else:
            self.parent.add_str("  " + self.text + "  ", 0, self.beg_x, attr=curses.color_pair(254))


    def toggle(self):
        if self.active:
            self.close()
        elif self.active is False:
            self.open()

    def open(self):
        if self.active is True:
            self.close()
            return
        self.active = True
        self.panel.show()
        self.panel.top()
        curses.panel.update_panels()

    def close(self):
        if self.active is False:
            return
        self.panel.hide()
        self.active = False
        curses.panel.update_panels()


class FooterItem:
    def __init__(self, text: str, key: int, beg_x: int, parent_win: Window, function: FunctionType):
        self.text = text
        self.key = key
        self.beg_x = beg_x
        self.end_x = self.beg_x + len(text) + 4 + len(self.get_key_name())
        self.parent = parent_win
        self.function = function

    def draw(self):
        self.parent.add_str("  " + self.text + " ", 0, self.beg_x, attr=curses.color_pair(254))
        self.parent.window.addstr(self.get_key_name(), curses.A_BOLD)
        self.parent.window.addstr(" ", curses.A_NORMAL)

    def get_key_name(self):
        return curses.keyname(self.key).replace(b'KEY_', b'').decode('ascii')


def setup_curses():  # Tuple[curses._CursesWindow]
    app = App(True, True)
    app.add_new_window("root", curses.COLS, curses.LINES, 0, 0)
    root = app.windows['root']
    root.panel.bottom()
    hex_v = root.add_subwindow("hex", (curses.COLS // 3) * 2, curses.LINES - 2, 0, 0)
    text_v = root.add_subwindow("text", curses.COLS // 3, curses.LINES - 2, 0, (curses.COLS // 3) * 2)
    app.menubar.add_item("File", {
        "Open": None,
        "Save": None,
        "Save As": None,
        "Exit": None
    }, curses.KEY_F10)
    app.menubar.add_item("Test2", {"Test": None}, curses.KEY_F9)
    app.footerbar.set_background_colour(254)
    return app


if __name__ == "__main__":
    try:
        root = setup_curses()
        root.refresh()
        root.windows['root'].sub_windows['hex'].add_str("BOBBB")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(root.run())
    finally:
        curses.echo()
        curses.cbreak()
        curses.endwin()
