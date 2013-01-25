from ZomgBot import bot

from time import sleep
import signal
import sys

def signal_handler(signal, frame):
    if bot and bot.irc:
        bot.stop()
    else:
        sys.exit(0)
#    sleep(2)
#    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    bot.init('irc.gamesurge.net', 6667, '#llama', 'ZomgBot')
    bot.run()
