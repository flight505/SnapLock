# SnapLock commands registry.
# Each command in this list must expose start() and stop() functions.
from .snaplock_create import entry as snaplock_create

commands = [
    snaplock_create,
]


def start():
    for command in commands:
        command.start()


def stop():
    for command in commands:
        command.stop()
