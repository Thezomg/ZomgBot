from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import Event, EventHandler

class CommandContext(object):
    def __init__(self, user, channel):
        self.user = user
        self.channel = channel

    def reply(self, msg, public=True):
        if self.channel and public:
            self.channel.say(msg)
        else:
            self.user.say(msg)
    
    def parse_args(self, msg):
        self.args = msg[1:].split(' ')
        return self.args.pop(0)

@Plugin.register(depends=["auth"])
class Commands(Plugin):
    @EventHandler("PluginsLoaded")
    def handle_reload(self, event):
        cmds = Modifier.get("command")
        self.commands = {}
        for cmd in cmds:
            [self.commands.update({n: cmd}) for n in cmd.annotation["command"].get("aliases", []) + [cmd.annotation["command"]["args"][0]]]
        print self.commands

    def _really_do_command(self, auth_result, name, context):
        if name in self.commands:
            self.commands[name].call_with_self(context)
        else:
            context.reply("No such command, try another one you retard.")

    def do_command(self, name, context):
        print "Trying to execute {}".format(name)
        r = self.events.dispatchEvent(name="AuthenticateUser", event=Event(user=context.user.user, irc=context.user.irc))
        r.addCallback(self._really_do_command, name, context)

    @EventHandler("ChannelMsg")
    def handle_commands(self, event):
        print event
        if not event.message.startswith('/'): return
        context = CommandContext(event.user, event.channel)
        command = context.parse_args(event.message)
        self.do_command(command, context)

    @EventHandler("PrivateMsg")
    def handle_private(self, event):
        if not event.message.startswith('/'): return
        context = CommandContext(event.user, None)
        command = context.parse_args(event.message)
        self.do_command(command, context)

    @Modifier.command("mystatus")
    def cmd_mystatus(self, context):
        context.reply("You are {}, ".format(context.user) + ("logged in as {}".format(context.user.account) if context.user.account else "not logged in"))
