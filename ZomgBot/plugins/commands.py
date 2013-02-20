from ZomgBot.bot import IRCUserInChannel
from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import Event, EventHandler

from collections import Sequence
import logging

from twisted.internet.defer import Deferred, maybeDeferred, inlineCallbacks, returnValue


class CommandContext(object):
    def __init__(self, user, channel):
        self.user = user
        self.channel = channel
        self._real_chan = channel

    def reply(self, msg, public=True):
        if '\n' in msg:
            [self.reply(m, public) for m in msg.split('\n')]
            return
        msg = msg.strip()
        if self._real_chan and public:
            self._real_chan.say(msg)
        else:
            self.user.say(msg)
    
    def parse_args(self, msg):
        self.args = msg.split(' ')
        self.command = self.args[0]
        self.full = msg.split(' ', 1)[-1] if len(self.args) > 1 else ''
        if len(self.args) >= 2 and self.args[1].startswith('#'):
            channel = self.user.irc.getChannel(self.args[1])
            if channel:
                self.channel = channel
                self.args.pop(1)
        return self.args.pop(0)


@Plugin.register(depends=["auth", "permission"])
class Commands(Plugin):
    prefix = ["/"]

    def setup(self):
        self.commands = {}
        if "prefix" in self.get_config():
            self.prefix = map(str.lower, self.get_config()["prefix"])

    @property
    def prefixes(self):
        if self.get_config().get("bot_nick_is_prefix", False):
            return self.prefix + [self.bot.irc.nickname.lower() + s for s in [", ", ": ", " "]]
        else:
            return self.prefix

    @EventHandler("PluginsLoaded")
    def on_PluginsLoaded(self, event):
        cmds = Modifier.get("command")
        self.commands = {}
        for cmd in cmds:
            a = cmd.annotation["command"]
            [self.commands.update({n.lower(): (cmd, a)}) for n in a.get("aliases", []) + [a["args"][0]]]

    def _really_do_command(self, auth_result, name, context):
        if name not in self.commands: return

        cmd, an = self.commands[name]

        if an.get("channel", False) and not context.channel:
            context.reply("Please run this command in a channel (or specify the channel name as the first argument).")
            return

        perm = an.get("permission", None)
        if not perm or context.user.has_permission(perm, context.channel) or (an.get("chanop", False) and isinstance(context.user, IRCUserInChannel) and context.user.op):
            context.permission = "global" if not perm or context.user.has_permission(perm) else "channel"
            try:
                result = maybeDeferred(self.commands[name][0].call_with_self, context)
                def inner(result):
                    if isinstance(result, basestring):
                        context.reply(result)
                    elif isinstance(result, Sequence):
                        map(context.reply, result)
                result.addCallback(inner)
            except Exception as e:
                logging.exception("Encountered a {} (\"{}\") executing /{}.".format(e.__class__.__name__, str(e), name))
                context.reply("Encountered a {} (\"{}\") executing /{}.".format(e.__class__.__name__, str(e), name))
        else:
            context.reply("You need the permission {}.".format(perm))

    def do_command(self, name, context):
        r = self.events.dispatchEvent(name="AuthenticateUser", event=Event(user=context.user.base, irc=context.user.irc))
        r.addCallback(self._really_do_command, name, context)

    @inlineCallbacks
    def _dispatch_command(self, user, command, channel=None):
        event = Event(user=user, channel=channel, command=command)
        cancel = not (yield self.events.dispatchEvent(name="CommandPreprocess", event=event))
        if cancel:
            return
        else:
            self.dispatch_command(user, event.command, channel)

    def dispatch_command(self, user, command, channel=None):
        context = CommandContext(user, channel)
        command = context.parse_args(command)
        self.do_command(command, context)

    @EventHandler("ChannelMsg")
    def handle_commands(self, event):
        for prefix in self.prefixes:
            if not event.message.lower().startswith(prefix): continue
            self._dispatch_command(event.user, event.message[len(prefix):], event.channel)
            return

    @EventHandler("PrivateMsg")
    def handle_private(self, event):
        for prefix in self.prefixes:
            if not event.message.lower().startswith(prefix): continue
            self._dispatch_command(event.user, event.message[len(prefix):], None)
            return

    @Modifier.command("mystatus")
    def cmd_mystatus(self, context):
        userhost = str(context.user)
        if context.user.hostname:
            userhost += "!{}@{}".format(context.user.username, context.user.hostname)
        context.reply("You are {}, ".format(userhost) + ("logged in as {}".format(context.user.account) if context.user.account else "not logged in"))
        # figure out human names for all their modes
        mnames = ', '.join(self.parent.parent.irc.statuses[s] for s in context.user.status)
        if mnames: context.reply("You are {} in {}".format(mnames, context.channel))
