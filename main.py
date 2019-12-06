import asyncio
from functools import partial
from aioconsole import ainput, aprint
import threading
import sys
from server_functions import _server, _step, _packets, _update, _display, _disable, _crash

COMMANDS_DICT = {
    'server': _server,
    'step': _step,
    'update': _update,
    'packets': _packets,
    'display': _display,
    'disable': _disable,
    'crash': _crash
}

async def main():
    # event loop for reading input from the user
    while True:
        command_str = await ainput('')
        lower_command_str = command_str.lower()
        command_call, *command_args = lower_command_str.split(' ')
        if command_call in COMMANDS_DICT:
            try:
                func_to_call = COMMANDS_DICT[command_call]
                result = func_to_call(*command_args)
                if result:
                    await aprint(result)
            except FileNotFoundError as e:
                await aprint(f'ERROR {command_call} {e}')
            except TypeError as e:
                await aprint(f'ERROR {command_call} {e}')
            except:
                the_type, the_value, _ = sys.exc_info()
                await aprint(f'{command_call} {" ".join(*command_args)} {the_type}:{the_value}')
        else:
            await aprint(f'Command: {command_call} does not exist. Arguments provided: {" ".join([*command_args]) if len(command_args) > 0  else "None"}')

if __name__ == "__main__":
    asyncio.run(main())