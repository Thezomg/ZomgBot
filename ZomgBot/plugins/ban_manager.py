from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler
from ZomgBot.ircglob import glob, matches

from datetime import datetime
import re

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql.expression import func

from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue


Base = Plugin.declarative_base("ban_manager")

class Ban(Base):
    id = Column(Integer, primary_key=True)
    time = Column(DateTime)
    channel = Column(String(64))
    banmask = Column(String(256))
    ban_exp = Column(String(256))
    banner = Column(String(64))
    reason = Column(Text)

    def __repr__(self):
        return "<Ban(channel={self.channel}, banmask={self.ban_exp}, banner={self.banner})>".format(self=self)


class ThreadHelper(object):
    def __init__(self, plugin):
        self.plugin = plugin

    @property
    def db(self):
        return self.plugin.db

    @staticmethod
    def worker(defer, func, a, kw):
        try:
            res = func(*a, **kw)
            reactor.callFromThread(defer.callback, res)
        except Exception as e:
            reactor.callFromThread(defer.errback, e)
    
    @classmethod
    def execute(cls, func, *a, **kw):
        d = Deferred()
        reactor.callInThread(cls.worker, d, func, a, kw)
        return d

    def add_ban(self, ban):
        def inner():
            self.db.add(ban)
            self.db.commit()
        return self.execute(inner)
    
    def find_ban(self, channel, mask):
        def inner():
            return self.db.query(Ban).\
                filter(Ban.channel == channel).\
                filter(":mask LIKE ban_exp").params(mask=mask).\
                first()
        return self.execute(inner)

    def count_bans(self, channel, mask):
        def inner():
            return self.db.query(Ban).\
                filter(Ban.channel == channel).\
                filter(Ban.banmask == mask).\
                count()
        return self.execute(inner)

    def remove_ban(self, channel, mask):
        def inner():
            r = self.db.query(Ban).\
                filter(func.lower(Ban.banmask) == mask.lower()).\
                filter(Ban.channel == channel).\
                delete(synchronize_session='fetch')
            self.db.commit()
            return r > 0
        return self.execute(inner)


@Plugin.register(depends=["commands", "op", "tasks"], uses_db=True)
class BanManager(Plugin):
    refresh_required = False

    def setup(self):
        self.helper = ThreadHelper(self)
        self.wait = []
        self.seen = set()
        self.channels = set(s.lower() for s in self.get_config().get("channels", []))
        self.op = self.parent.get_plugin("op")

    ### general helper ###

    @staticmethod
    def glob_to_like_expr(pattern):
        return pattern.replace('*', '%').replace('?', '_')

    def trim_bans(self, channel, headroom=0):
        limit = self.bot.irc.supported.getFeature("MAXLIST", [(None, 50)])[0][1] / 2
        bans = list(sorted(channel.bans, key=lambda t: -t[2]))[limit - headroom:]
        for mask, setter, time in bans:
            self.track_ban(channel, setter, mask)
            self.op.mode(channel.name, 'b', False, str(mask))
        return len(bans)

    ### database ban tracking ###

    def _kick_banned(self, channel, mask, banner, reason=None):
        for name, user in channel.users.items():
            if matches(mask, user.hostmask):
                self.op.kick(str(channel), user.name, 'Banned by {}'.format(banner) + (': {}'.format(reason) if reason else ''))
        self.op.run_queue(channel)
        self.wait.remove(mask)

    def find_ban(self, channel, hostmask):
        return self.helper.find_ban(channel, hostmask)

    def _really_track_ban(self, count, channel, user, mask, reason):
        if count >= 1: return False

        ban = Ban(time    = datetime.now(),
                  channel = str(channel),
                  banmask = mask,
                  ban_exp = self.glob_to_like_expr(mask),
                  banner  = user,
                  reason  = reason)
        self.helper.add_ban(ban)

        self.wait.append(mask)

        if self.get_config().get("no_kick_on_banned", False):
            reactor.callLater(5, self._kick_banned, channel, mask, banner=user)

        return True

    def track_ban(self, channel, user, mask, reason=''):
        d = self.helper.count_bans(channel.name, mask)
        d.addCallback(self._really_track_ban, channel, user, mask, reason)
        return d

    def update_ban(self, mask, reason=None, banner=None):
        def inner():
            ban = self.db.query(Ban).filter(Ban.banmask == mask).first()
            if ban:
                if reason: ban.reason = reason
                if banner: ban.banner = banner
                self.db.commit()
                return True
            return False
        return self.helper.execute(inner)

    def remove_ban(self, mask, channel):
        return self.helper.remove_ban(channel, mask)

    ### commands ###

    @Modifier.command("ban", permission="bans.ban", chanop=True)
    @inlineCallbacks
    def cmd_ban(self, context):
        if not context.channel:
            returnValue("Run this command in a channel (or specify a channel name after the command).")
        if len(context.args) < 1:
            returnValue("You must specify a mask to ban.")
        mask = context.args[0]
        reason = ' '.join(context.args[1:])

        if '!' not in mask:
            for u in context.channel.users.values():
                if mask.lower() == u.name.lower():
                    mask = "*!*@{}".format(u.hostname)
        if '!' not in mask:
            returnValue("{} is neither a nick!user@host mask nor the name of a user on the channel.".format(mask))

        banned = yield self.track_ban(context.channel, context.user.name, mask, reason)
        kb = False
        for u in context.channel.users.values():
            if matches(mask, u.hostmask):
                kb = True
                self.op.kick(context.channel.name, u.name, 'Banned by {}'.format(context.user.name) + (': {}'.format(reason) if reason else ''))

        if kb:
            self.trim_bans(context.channel, 1)
            self.op.mode(context.channel.name, 'b', True, mask)
            self.op.run_queue(context.channel)
        else:
            if banned:
                returnValue("{} banned successfully.".format(mask))
            else:
                returnValue("{} was already banned.".format(mask))

    @Modifier.command("unban", permission="bans.unban", chanop=True)
    @inlineCallbacks
    def cmd_unban(self, context):
        if not context.channel:
            returnValue("Run this command in a channel (or specify a channel name after the command).")
        if len(context.args) < 1:
            returnValue("You must specify a mask to unban.")

        mask = context.args[0]
        if '!' in mask:
            complain = True
            if mask.lower() in set(b[0].lower() for b in context.channel.bans):
                self.op.mode(context.channel.name, 'b', False, str(mask))
                self.op.run_queue(context.channel)
                complain = False
            removed = yield self.remove_ban(context.args[0], context.channel.name)
            if complain:
                if removed:
                    returnValue("Forgot ban for {}.".format(context.args[0]))
                else:
                    returnValue("Mask is not in ban database.")
        else:
            nick = mask
            complain = True

            data = yield self.bot.irc.whois(mask)
            if not data:
                returnValue("No suck nickname: {}".format(nick))
            mask = "{0}!{user}@{host}".format(nick, **data)
            bans = [mask_ for mask_, setter, time in context.channel.bans if matches(mask_, mask)]
            for b in bans:
                complain = False
                self.op.mode(context.channel.name, 'b', False, str(b))
            if bans: self.op.run_queue(context.channel)

            ban = yield self.find_ban(context.channel.name, mask)
            if ban:
                self.remove_ban(ban.banmask, context.channel.name)
                if complain:returnValue("Forgot ban for {}.".format(ban.banmask))
            elif complain:
                returnValue("User not banned.")


    @Modifier.command("showban", permission="bans.showban", chanop=True)
    def cmd_showban(self, context):
        if not context.channel:
            return "Run this command in a channel (or specify a channel name after the command)."
        if len(context.args) < 1:
            return "You must specify a mask to check."
        mask = context.args[0]
        ban = self.find_ban(context.channel.name, mask)
        def inner(ban):
            if not ban:
                return "No bans match {}".format(mask)
            return "Ban for {} by {}".format(ban.banmask, ban.banner) + (": {}".format(ban.reason) if ban.reason else "")
        ban.addCallback(inner)
        return ban

    @Modifier.command("updateban", permission="bans.updateban", chanop=True)
    def cmd_updateban(self, context):
        if not context.channel:
            return "Run this command in a channel (or specify a channel name after the command)."
        if len(context.args) < 1:
            return "You must specify a mask to update."
        mask = context.args[0]
        reason = ' '.join(context.args[1:])
        d = self.update_ban(mask, reason, context.user.name)
        def inner(d):
            if d:
                return "Updated ban for {}.".format(mask)
            else:
                return "Mask is not in ban database."
        d.addCallback(inner)
        return d

    ### event handlers ###

    @EventHandler("ModeSet")
    def on_ModeSet(self, event):
        if event.channel.name not in self.channels: return
        if event.letter != 'b': return
        self.track_ban(event.channel, event.user.name, event.param)

    @EventHandler("ModeCleared")
    def on_ModeCleared(self, event):
        if event.channel.name not in self.channels: return
        if event.letter != 'b' or event.user.name == self.bot.irc.nickname: return
        self.remove_ban(event.param, event.channel.name)

    @EventHandler("UserJoinedChannel")
    def on_UserJoinedChannel(self, event):
        if event.channel.name not in self.channels: return
        b = self.find_ban(event.channel.name, event.user.hostmask)

        def inner(b):
            if not b: return

            self.trim_bans(event.channel, 1)
            self.op.mode(event.channel.name, 'b', True, str(b.banmask))
            self.op.kick(event.channel.name, event.user.name, 'Banned by {}'.format(b.banner) + (': {}'.format(b.reason) if b.reason else ''))
            self.op.run_queue(event.channel)

        b.addCallback(inner)

    @EventHandler("UserChangedNick")
    def on_UserChangingNick(self, event):
        for channel in event.user.channels:
            if channel.name not in self.channels: continue

            user = channel.getOrCreateUser(event.user.name)
        
            for mask, setter, time in channel.bans:
                if matches(mask, event.user.hostmask):
                    def inner(b):
                        if b:
                            self.op.kick(channel.name, user.name, 'Banned by {}'.format(str(b.banner) + (': {}'.format(b.reason) if b.reason else '')))
                        else:
                            self.op.kick(channel.name, user.name, 'Banned by {}'.format(setter))
                        self.op.run_queue(channel)
                    b = self.find_ban(channel.name, user.hostmask)
                    b.addCallback(inner)
                    return

            b = self.find_ban(channel.name, user.hostmask)

            def inner(b):
                if not b: return

                self.trim_bans(channel, 1)
                self.op.mode(channel.name, 'b', True, str(b.banmask))
                self.op.kick(channel.name, user.name, 'Banned by {}'.format(str(b.banner)))
                self.op.run_queue(channel)

            b.addCallback(inner)

    @EventHandler("UserKicked")
    def on_UserKicked(self, event):
        banner = None
        message = event.message
        if event.kicker.name == "ChanServ":
            m = re.match(r"\((.*?)\) (.*)", message)
            if m: banner, message = m.groups()
        for mask in self.wait:
            if event.kickee.hostmask and matches(mask, event.kickee.hostmask):
                self.update_ban(mask, message, banner)
    
    @EventHandler("BanlistUpdated")
    def on_BanlistUpdated(self, event):
        limit = self.bot.irc.supported.getFeature("MAXLIST", [(None, 50)])[0][1] / 2
        bans = list(sorted(event.channel.bans, key=lambda t: -t[2]))
        if event.channel.name not in self.seen:
            for mask, setter, time in bans:
                self.track_ban(event.channel, setter, mask)
            self.seen.add(event.channel.name)
        
        if self.trim_bans(event.channel): self.op.run_queue(event.channel)

    ### tasks ###

    @Modifier.repeat("clean_bans", time=15.0, autostart=True)
    def task_clean_bans(self):
        self.refresh_required = True
        for channel in self.bot.irc.channels:
            if channel not in self.channels: continue
            self.bot.irc.sendLine("MODE {} +b".format(channel))
