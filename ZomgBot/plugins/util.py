from ZomgBot.plugins import Plugin, Modifier

@Plugin.register(depends=["commands"])
class Util(Plugin):
    @Modifier.command("raw", permission="util.raw")
    def cmd_raw(self, context):
        if not context.args:
            return "Need argument"
        self.bot.irc.sendLine(context.full)

    @Modifier.command("inject", permission="util.inject")
    def cmd_inject(self, context):
        if not context.args:
            return "Need argument"
        try:
            self.bot.irc.lineReceived(context.full)
        except:
            return "Line caused an error"

    @Modifier.command("exec", permission="util.exec")
    def cmd_exec(self, context):
        allow = self.get_config().get("enable_exec", False)
        if not allow:
            return "You must enable exec in config before using it in IRC"
        exec context.full

    @Modifier.command("reload", permission="util.reload")
    def cmd_reload(self, context):
        self.parent.parent.reload()
        return "Bot reloaded"

    @Modifier.command("rehash", permission="util.rehash")
    def cmd_rehash(self, context):
        self.parent.parent.config.loadOrCreate()
        return "Reloaded the configuration file"
