from ZomgBot.plugins import Plugin
from ZomgBot.events import EventHandler

from string import Template

from twisted.internet.defer import Deferred


class SaslMechanism(object):
    username = ""
    password = ""
    def __init__(self, username, password):
        self.username = username
        self.password = password
    def respond(data):
        return None


class SaslPlain(SaslMechanism):
    id = "PLAIN"
    def get_auth_data(self):
        return "{0}\0{0}\0{1}".format(self.username, self.password)
    def respond(self, data):
        if data: return False
        return self.get_auth_data()


@Plugin.register(depends=[])
class NickServ(Plugin):
    delay_end = None
    delay_join = None

    nickserv_requested = False
    sasl_buffer = ""

    @EventHandler("Connected")
    def on_Connected(self, event):
        self.username = self.get_config().get("username", "ZomgBot")
        self.password = self.get_config().get("password", "hunter2")
        self.sasl_methods = [SaslPlain]

    @property
    def use_sasl(self):
        return self.get_config().get("sasl", True)

    def send_line(self, line):
        print "sasl: " + line
        self.bot.irc.sendLine(line)

    def sasl_send(self, data):
        while data and len(data) >= 400:
            en, data = data[:400].encode('base64').replace('\n',''), data[400:]
            self.send_line("AUTHENTICATE " + en)
        if data:
            self.send_line("AUTHENTICATE " + data.encode('base64').replace('\n', ''))
        else:
            self.send_line("AUTHENTICATE +")

    def sasl_start(self):
        if self.sasl_methods:
            self.sasl_method = self.sasl_methods.pop(0)(self.username, self.password)
            print "Trying SASL method: " + self.sasl_method.id
            self.bot.irc.sendLine("AUTHENTICATE " + self.sasl_method.id)
            return True
        else:
            return False

    def sasl_failed(self, already=False):
        if not already and self.sasl_start(): return # try next method
        self.finish()
        self.maybe_quit()
    
    def sasl_next(self, data):
        if data == '+':
            data = ''
        else:
            data = data.decode('base64')
        if len(data) == 400:
            self.sasl_buffer += data
        else:
            response = self.sasl_method.respond(self.sasl_buffer + data)
            if response == False: # abort
                self.bot.irc.sendLine("AUTHENTICATE *")
            else:
                self.sasl_send(response)
            self.sasl_buffer = ""

    def finish(self):
        if self.delay_end is None: return
        self.delay_end.callback(True)
        self.delay_end = None

    def get_nickserv_command(self):
        cfg = self.get_config()
        user = cfg.get("username", "ZomgBot")
        password = cfg.get("password", "hunter2")
        template = Template(cfg.get("command", "IDENTIFY $user $password"))
        return template.safe_substitute(user=user, password=password)
    
    def get_nickserv_user(self):
        return self.get_config().get("service", "NickServ")

    def check_notice(self, user, message):
        if user.name != self.get_nickserv_user(): return
        ignore_msg = self.get_config().get("ignore_msg", "/msg NickServ")
        if ignore_msg in message: return
        success_msg = self.get_config().get("success_msg", "You are now identified")
        if success_msg not in message:
            self.maybe_quit()
            return
        if self.delay_join is not None:
            self.delay_join.callback(True)
            self.delay_join = None

    def maybe_quit(self):
        cfg = self.get_config()
        if cfg.get("quit_on_error", False):
            self.bot.stop("Authentication failed.")
    
    @EventHandler("SignedOn")
    def on_SignedOn(self, event):
        if not (self.bot.irc.supports_cap and self.use_sasl):
            if self.use_sasl: print "BOO, the server doesn't FUCKING support IRCv3."
            self.nickserv_requested = True
            self.bot.irc.sendLine(self.get_nickserv_command())
            self.delay_join = Deferred()
            return self.delay_join

    @EventHandler("PrivateNotice")
    def on_PrivateNotice(self, event):
        if not self.nickserv_requested: return
        self.check_notice(event.user, event.message)

    @EventHandler("CapList")
    def on_CapList(self, event):
        if "sasl" in event.capabilities and self.use_sasl:
            self.bot.irc.request_cap("sasl")

    @EventHandler("CapEnding")
    def on_CapEnding(self, event):
        if "sasl" not in self.bot.irc.capabilities: return
        if self.sasl_start():
            self.delay_end = Deferred()
            return self.delay_end

    @EventHandler("IRC.AUTHENTICATE")
    def on_AUTHENTICATE(self, event):
        self.sasl_next(event.params[0])
    
    @EventHandler("IRC.904") # ERR_SASLFAIL
    @EventHandler("IRC.905") # ERR_SASLTOOLONG
    @EventHandler("IRC.906") # ERR_SASLABORTED
    def on_auth_failed(self, event):
        self.sasl_failed()

    @EventHandler("IRC.907") # ERR_SASLALREADY
    def on_auth_already(self, event):
        self.sasl_failed(True)

    @EventHandler("IRC.900")
    def on_authed(self, event):
        print "Logged on as {}".format(event.params[2])

    @EventHandler("IRC.903")
    def on_sasl_successful(self, event):
        self.finish()
