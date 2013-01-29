from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

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

@Plugin.register(depends=None)
class Commands(Plugin):
    @EventHandler("PluginsLoaded")
    def handle_reload(self, event):
        cmds = Modifier.get("command")
        self.commands = {}
        for cmd in cmds:
            [self.commands.update({n: cmd}) for n in cmd.annotation["command"].get("aliases", []) + [cmd.annotation["command"]["args"][0]]]
        print self.commands

    def do_command(self, name, context):
        print "Trying to execute {}".format(name)
        if name in self.commands:
            self.commands[name].call_with_self(context)
        else:
            context.reply("No such command, try another one you retard.")

    @EventHandler("ChannelMsg")
    def handle_commands(self, event):
        if not event.message.startswith('/'): return
        context = CommandContext(event.user, event.channel)
        command = context.parse_args(event.message)
        self.do_command(command, context)

    @Modifier.command("derp")
    def cmd_derp(self, context):
        context.reply("hello, {}!".format(context.user))

    @Modifier.command("test")
    def cmd_test(self, context):
        context.reply("after reload!")

    @Modifier.command("yaml")
    def cmd_yamltest(self, context):
        self.get_config()['storage'] = 'testing'
        self.save_config()
        context.reply("setting key specific to this plugin")
