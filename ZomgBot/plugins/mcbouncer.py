from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

@Plugin.register(depends=None)
class MCBouncer(Plugin):

    def ban(self, user, issuer, reason):
        print "MCBouncer Ban: {} banning {} for {}".format(issuer, user, reason)

