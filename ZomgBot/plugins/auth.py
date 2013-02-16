from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

from twisted.internet.defer import Deferred

@Plugin.register(depends=[])
class Auth(Plugin):
    def whois_done(self, result, event):
        event.user.account = result.get("account", None)
        print "{} is now authed as {}".format(event.user, result.get("account", None))

    @EventHandler("AuthenticateUser", priority=-10)
    def auth_event(self, event):
        if event.user.account: return True
        d = event.irc.whois(event.user.name)
        d.addCallback(self.whois_done, event)
        return d
