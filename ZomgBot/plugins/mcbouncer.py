from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

@Plugin.register(depends=["commands", "auth", "permission"])
class MCBouncer(Plugin):

    @Modifier.command("ban", permission="mcb.addban")
    def addban(self, context):
        print "adding ban {}".format(' '.join(context.args))

    @Modifier.command("addnote", permission="mcb.addnote")
    def addnote(self, context):
    	print "adding note {}".format(' '.join(context.args))

    @Modifier.command("unban", permission="mcb.unban")
    def unban(self, context):
    	print "unbanning {}".format(' '.join(context.args))

    @Modifier.command("delnote", permission="mcb.delnote")
    def delnote(self, context):
    	print "deleting note {}".format(' '.join(context.args))

    @Modifier.command("lookup")
    def lookup(self, context):
    	print "looking up {}".format(' '.join(context.args))

    @Modifier.command("notes")
    def notes(self, context):
    	print "getting notes {}".format(' '.join(context.args))

    @Modifier.command("bans")
    def bans(self, context):
    	print "getting bans {}".format(' '.join(context.args))

    def allowed(self, context):
    	c = context.channel.name
    	return c in self.get_config().get("channels", [])

    @Modifier.command("mcballowchan", permission="mcb.manageallowed")
    def addallowed(self, context):
        print "adding allowed {}".format(' '.join(context.args))

    @Modifier.command("mcbunallowchan", permission="mcb.manageallowed")
    def defallowed(self, context):
        print "deleting allowed {}".format(' '.join(context.args))