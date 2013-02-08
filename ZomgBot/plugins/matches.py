from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import Event, EventHandler
import logging
import re

class MatchContext(object):
    def __init__(self, user, channel):
        self.user = user
        self.channel = channel

    def reply(self, msg, public=True):
        if self.channel and public:
            self.channel.say(msg)
        else:
            self.user.say(msg)
    
    def parse_args(self, msg):
        self.msg = msg
        self.args = msg[1:].split(' ')
        return self.args.pop(0)

@Plugin.register(depends=["auth", "permission"])
class Matches(Plugin):
    @EventHandler("PluginsLoaded")
    def handle_reload(self, event):
        cmds = Modifier.get("match")
        self.matches = []
        for cmd in cmds:
            a = cmd.annotation["match"]
            [self.matches.append((cmd, a, self.setup_regex(n))) for n in a.get("aliases", []) + [a["args"][0]]]
        print self.matches

    def setup_regex(self, r):
        r = r.replace("\\$botnick\\$", self.parent.parent.config["irc"]["nick"])
        return re.compile(r)

    def _really_do_match(self, auth_result, context):
        for cmd, an, r in self.matches:
            perm = an.get("permission")
            if not perm or context.user.has_permission(perm):
                m = r.search(context.msg)
                if m != None:
                    try:
                        cmd.call_with_self(m, context)
                    except Exception as e:
                        logging.exception("Encountered a {} (\"{}\") executing /{}. Tell its retarded author to fix their shit.".format(e.__class__.__name__, str(e), a))
                        context.reply("Encountered a {} (\"{}\") executing /{}. Tell its retarded author to fix their shit.".format(e.__class__.__name__, str(e), a))
            else:
                context.reply("You need the permission {} and you don't have it, you fuckwad.".format(perm))

    def do_match(self, context):
        r = self.events.dispatchEvent(name="AuthenticateUser", event=Event(user=context.user.user, irc=context.user.irc))
        r.addCallback(self._really_do_match, context)

    @Modifier.match("^\$botnick\$: testing match$")
    def test_match(self, matches, context):
        context.reply("Hmmm... seems to have worked.")

    @EventHandler("ChannelMsg")
    def handle_matches(self, event):
        context = MatchContext(event.user, event.channel)
        context.parse_args(event.message)
        self.do_match(context)