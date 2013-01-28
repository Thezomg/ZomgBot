from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

mc_ban_provider = "MCBouncer"
chan_ban_provider = "ChannelBanProvider"

@Plugin.register(depends=["commands"])
class BanManager(Plugin):
    @Modifier.command("ban", permission="mcb.addban")
    def ban(self, context):#, target):
        provider = self.parent.get_plugin(mc_ban_provider)
        provider.ban('user', 'issuer', 'reason')
        context.reply('Doing MCBouncer ban')

    @Modifier.command("cban", permission="channel.admin")
    def channel_ban(self, context):
        provider = self.parent.get_plugin(chan_ban_provider)
        provider.ban('user', 'issuer', 'reason')
        context.reply('Doing Channel Ban')

    @EventHandler("IJoinChannel")
    def test(self, event):
        print "I am joining channel {}".format(event)
