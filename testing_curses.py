import asyncio
from time import sleep
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

flag = 0

async def derp():
    if flag == 1:
        print("DER")
    else:
        return ""

loop = asyncio.get_event_loop()
file_name = 'FILE_NAME'

executor = ThreadPoolExecutor(
    max_workers=3
)

# load the file without blocking


while True:
    sleep(0.5)
    loop.run_until_complete(derp())
    print("DF")
    flag ^= 1