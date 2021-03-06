from ZomgBot import bot
from ZomgBot.config import Config

from twisted.internet import reactor
from time import sleep
import signal
import sys

def signal_handler(signal, frame):
    if bot and bot.irc:
        bot.stop("CTRL-C from console")
    elif reactor.running:
        reactor.stop()
    else:
        sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    config = Config()
    config.loadOrCreate()

    bot.init(config)
    bot.run()
