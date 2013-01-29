from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

from twisted.internet.defer import Deferred

@Plugin.register(depends=[])
class Auth(Plugin):
    def setup(self):
        self.needuser = {}

    @EventHandler("WhoisAccount")
    def whois_event(self, event):
        event.user.account = event.account
        print "{} is now authed as {}".format(event.user, event.account)
        if event.user in self.needuser:
            print "calling back"
            self.needuser.pop(event.user).callback(True)
        else:
            print "not calling back because {} is not in {}".format(event.user, self.needuser)
    
    @EventHandler("WhoisEnd")
    def whois_end(self, event):
        if event.user in self.needuser:
            self.needuser.pop(event.user).callback(False)

    @EventHandler("AuthenticateUser", priority=-1)
    def auth_event(self, event):
        if event.user.account: return True
        d = Deferred()
        event.irc.whois(event.user.name)
        self.needuser[event.user] = d
        return d
