from ZomgBot.plugins import Plugin
from ZomgBot.events import EventHandler

from twisted.internet.defer import Deferred

@Plugin.register(depends=[])
class NickServ(Plugin):
    delay_end = None

    def finish(self):
        if self.delay_end is None: return
        self.delay_end.callback(True)
        self.delay_end = None

    def get_auth_data(self):
        cfg = self.get_config()
        user = cfg.get("username", "ZomgBot")
        password = cfg.get("password", "hunter2")
        return "{0}\0{0}\0{1}".format(user, password).encode('base64').strip()
    
    @EventHandler("SignedOn")
    def on_SignedOn(self, event):
        if not self.bot.irc.supports_cap:
            print "BOO, the server doesn't FUCKING support the cap command."
            print "we should probably try PMing NickServ instead."

    @EventHandler("CapList")
    def on_CapList(self, event):
        if "sasl" in event.capabilities:
            self.bot.irc.request_cap("sasl")

    @EventHandler("CapEnding")
    def on_CapEnding(self, event):
        if "sasl" not in self.bot.irc.capabilities: return
        self.bot.irc.sendLine("AUTHENTICATE PLAIN")
        self.delay_end = Deferred()
        return self.delay_end

    @EventHandler("IRC.AUTHENTICATE")
    def on_AUTHENTICATE(self, event):
        if event.params[0] == "+":
            self.bot.irc.sendLine("AUTHENTICATE {}".format(self.get_auth_data()))
    
    @EventHandler("IRC.904")
    @EventHandler("IRC.905")
    def on_auth_failed(self, event):
        self.finish()

    @EventHandler("IRC.900")
    def on_authed(self, event):
        print "Logged on as {}".format(event.params[2])

    @EventHandler("IRC.903")
    def on_sasl_successful(self, event):
        self.finish()
