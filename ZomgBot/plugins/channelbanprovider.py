from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

@Plugin.register(depends=None, provides=None)
class ChannelBanProvider(Plugin):

    def ban(self, user, issuer, reason):
        print "Channel ban: {} banning {} for {}".format(issuer, user, reason)

