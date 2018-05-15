import curses
from time import sleep

stdscr = curses.initscr()
curses.cbreak()
curses.noecho()
stdscr.nodelay(1)

num_iters_nochar = 0
num_iters_char = 0

for i in range(10**2):
    sleep(0.1)
    if stdscr.getch() == -1:
        num_iters_nochar += 1
    else:
        num_iters_char += 1




curses.nocbreak()
curses.echo()
curses.endwin()
print( num_iters_nochar , 'iterations with no input')
print( num_iters_char , 'iterations with input')
