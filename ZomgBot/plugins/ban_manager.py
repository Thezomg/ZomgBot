from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

@Plugin.register(depends=["commands"])
class BanManager(Plugin):
    @Modifier.command("ban", permission="channel.admin")
    def ban(self, context, target):
        print "Ban {}".format(target)

    @EventHandler("IJoinChannel")
    def test(self, event):
        print "I am joining channel {}".format(event)
