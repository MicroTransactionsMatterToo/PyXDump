from typing import Dict, Union, Tuple, Optional
from uuid import uuid4 as uuid
import re
import atexit
import curses
import asyncio


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


class App:
    def __init__(self):
        self.windows = {}  # type: Dict[str, Window]
        self.screen = curses.initscr()
        # Register our cleanup to prevents Curses from fucking everything up
        atexit.register(self._cleanup)

    def _cleanup(self):
        # Reverse Curses stuff
        self.screen.keypad(False)
        curses.cbreak()
        curses.echo()
        curses.endwin()

    def add_new_window(self, name: str, cols: int, lines: int, beg_y: int, beg_x: int, win_id: str = None):
        nwin = Window(lines, cols, beg_y, beg_x, name)
        if win_id is not None:
            nwin._uuid = win_id
        self.windows[name] = nwin


class Screen:
    def __init__(self):
        self._screen = curses.initscr()
        # Setup Curses
        curses.noecho()
        curses.nocbreak()
        self._screen.keypad(True)


class Window:
    @classmethod
    def from_derived_window(cls, window, name=None):
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

    def add_subwindow(self, name: str, cols: int, lines: int, beg_y: int, beg_x: int, win_id: str = None):
        """
        Adds a subwindow to the current window. :param:`beg_y` and :param:`beg_x` are relative to the parent window
        """
        nwin = self.window.derwin(lines, cols, beg_y, beg_x)
        nwin = Window.from_derived_window(nwin, name)
        nwin.parent = self
        self.sub_windows[name] = nwin

    def remove_subwindow(self, name: str):
        del self.sub_windows[name]

    def erase(self):
        self.window.erase()

    def clear(self):
        self.window.clear()

    def inch(self, y: int, x: int) -> Tuple[str, int]:
        """
        Gets the character at :code:`y, x`.

        Args:
            y (int): y coord
            x (int): x coord

        Returns:
            Tuple[str, int]: A tuple containing the character and attribute code
        """
        data = self.window.inch(y, x)
        character = chr(data & 0xFF)
        attribute = (data >> 8) << 8
        return character, attribute

    def get_char(self, y: int, x: int) -> Tuple[str, int]:
        """
        Gets the character at :code:`y, x`.

        Args:
            y (int): y coord
            x (int): x coord

        Returns:
            Tuple[str, int]: A tuple containing the character and attribute code
        """
        return self.inch(y, x)

    def get_input(self, y: int = None, x: int = None):
        """
        Gets a single character from the user. If x or y is provided, the other coordinate
        must also be provided

        Args:
            y (Optional[int]): y coordinate
            x (Optional[int]): x coordinate

        Returns:
            Tuple[str, int]: A tuple containing the character and attribute code
        """
        if y and x:
            char = self.window.getch(y, x)
            char = decode_retrieved_str(char)
            return char
        elif x is None or y is None:
            raise ValueError("Both y and x must be provided")
        elif x is None and y is None:
            char = self.window.getch()
            char = decode_retrieved_str(char)
            return char
