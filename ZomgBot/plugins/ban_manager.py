from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler
from ZomgBot.ircglob import glob, matches

from datetime import datetime
import re

from sqlalchemy import Column, DateTime, Integer, String, Text

from twisted.internet import reactor
from twisted.internet.defer import Deferred


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
            r = self.db.query(Ban).filter(Ban.banmask == mask).filter(Ban.channel == channel).delete()
            self.db.commit()
            return r > 0
        return self.execute(inner)


@Plugin.register(depends=["commands", "tasks"], uses_db=True)
class BanManager(Plugin):
    refresh_required = False

    def setup(self):
        self.helper = ThreadHelper(self)
        self.wait = []
        self.seen = set()
        self.channels = set(s.lower() for s in self.get_config().get("channels", []))
        self.mode_queue = {}
        self.line_queue = {}
        self.op = set()
        self.deop = {}

    ### general helper ###

    @staticmethod
    def glob_to_like_expr(pattern):
        return pattern.replace('*', '%').replace('?', '_')

    ### Op action managemnt ###

    def queue_line(self, channel, line):
        l = self.line_queue.setdefault(channel, [])
        l.append(line)
    
    def queue_kick(self, channel, user, reason):
        self.queue_line(channel, "KICK {} {} :{}".format(channel, user, reason))

    def queue_mode(self, channel, letter, set_, arg=None):
        l = self.mode_queue.setdefault(channel, [])
        l.append((letter, set_, arg))

    def _do_modes(self, channel):
        lines = []
        queue = sorted(self.mode_queue.get(channel, []), key=lambda t:not t[1])
        letters, args = "", []
        cur = None
        count = 0
        for letter, set_, arg in queue:
            if set_ != cur:
                cur = set_
                letters += "+" if set_ else "-"
            letters += letter
            if arg: args.append(arg)
            count += 1
            if count >= 4:
                lines.append("MODE {} {} {}".format(channel, letters, " ".join(args)))
                letters, args = "", []
                cur = None
                count = 0
        if count:
            lines.append("MODE {} {} {}".format(channel, letters, " ".join(args)))
        del self.mode_queue[channel]
        map(self.bot.irc.sendLine, lines)

    def _do_deop(self, channel):
        if channel in self.deop: del self.deop[channel]
        self.op.remove(channel)
        self.bot.irc.mode(str(channel), False, 'o', user=self.bot.irc.nickname)

    def _got_op(self, channel):
        if channel in self.mode_queue:
            self._do_modes(channel)
        if channel in self.line_queue:
            map(self.bot.irc.sendLine, self.line_queue[channel])
            del self.line_queue[channel]
        if channel in self.deop:
            self.deop[channel].reset(30)
        else:
            self.deop[channel] = reactor.callLater(30, self._do_deop, channel)

    def op_me(self, channel):
        if channel.name in self.op:
            return self._got_op(channel.name)
        if channel.name not in self.mode_queue and channel.name not in self.line_queue: return
        command = self.get_config().get("op_command", "PRIVMSG ChanServ :OP {channel} {nick}")
        self.bot.irc.sendLine(command.format(channel=channel.name, nick=self.bot.irc.nickname))

    ### database ban tracking ###

    def _kick_banned(self, channel, mask, banner, reason=None):
        for name, user in channel.users.items():
            if matches(mask, user.hostmask):
                self.queue_kick(str(channel), user.name, 'Banned by {}'.format(banner) + (': {}'.format(reason) if reason else ''))
        self.op_me(channel)
        self.wait.remove(mask)

    def find_ban(self, channel, hostmask):
        return self.helper.find_ban(channel, hostmask)

    def _really_track_ban(self, count, channel, user, mask):
        if count >= 1: return

        ban = Ban(time    = datetime.now(),
                  channel = str(channel),
                  banmask = mask,
                  ban_exp = self.glob_to_like_expr(mask),
                  banner  = user,
                  reason  = '')
        self.helper.add_ban(ban)

        self.wait.append(mask)

        reactor.callLater(5, self._kick_banned, channel, mask, banner=user)

    def track_ban(self, channel, user, mask):
        d = self.helper.count_bans(channel.name, mask)
        d.addCallback(self._really_track_ban, channel, user, mask)

    def update_ban(self, mask, reason=None, banner=None):
        def inner():
            ban = self.db.query(Ban).filter(Ban.banmask == mask).first()
            if ban:
                if reason: ban.reason = reason
                if banner: ban.banner = banner
                self.db.commit()
        self.helper.execute(inner)

    def remove_ban(self, mask, channel):
        return self.helper.remove_ban(channel, mask)

    ### commands ###

    @Modifier.command("unban", permission="bans.unban", chanop=True)
    def cmd_unban(self, context):
        if not context.channel:
            return "Can't unban from a query."
        mask = context.args[0]
        complain = True
        if mask in set(b[0] for b in context.channel.bans):
            self.queue_mode(context.channel.name, 'b', False, str(mask))
            self.op_me(context.channel)
            complain = False
        def inner(removed):
            if removed:
                return "Forgot ban for {}.".format(context.args[0])
            elif complain:
                return "Mask is not in ban database."
        d = self.remove_ban(context.args[0], context.channel.name)
        d.addCallback(inner)
        return d

    @Modifier.command("showban", permission="bans.showban", chanop=True)
    def cmd_showban(self, context):
        if not context.channel:
            return "Can't show bans from a query."
        mask = context.args[0]
        ban = self.find_ban(context.channel.name, mask)
        def inner(ban):
            if not ban:
                return "No bans match {}".format(mask)
            return "Ban for {} by {}".format(ban.banmask, ban.banner) + (": {}".format(ban.reason) if ban.reason else "")
        ban.addCallback(inner)
        return ban

    ### event handlers ###

    @EventHandler("ModeSet")
    def on_ModeSet(self, event):
        if event.channel.name not in self.channels: return
        if event.letter == 'o' and event.param == self.bot.irc.nickname:
            self.op.add(event.channel.name)
            self._got_op(event.channel.name)
            return
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

            limit = (self.bot.irc.supported.getFeature("MAXLIST", [(None, 50)])[0][1] / 2)
            bans = list(sorted(event.channel.bans, key=lambda t: -t[2]))
            if len(bans) >= limit:
                mask, setter, time = bans[0]
                self.track_ban(event.channel, setter, mask)
                self.queue_mode(event.channel.name, 'b', False, str(mask))

            self.queue_mode(event.channel.name, 'b', True, str(b.banmask))
            self.queue_kick(event.channel.name, event.user.name, 'Banned by {}'.format(b.banner) + (': {}'.format(b.reason) if b.reason else ''))
            self.op_me(event.channel)

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
                            self.queue_kick(channel.name, user.name, 'Banned by {}'.format(str(b.banner)))
                        else:
                            self.queue_kick(channel.name, user.name, 'Banned by {}'.format(setter))
                        self.op_me(channel)
                    b = self.find_ban(channel.name, user.hostmask)
                    b.addCallback(inner)
                    return

            b = self.find_ban(channel.name, user.hostmask)

            def inner(b):
                if not b: return

                limit = (self.bot.irc.supported.getFeature("MAXLIST", [(None, 50)])[0][1] / 2)
                bans = list(sorted(channel.bans, key=lambda t: -t[2]))
                if len(bans) >= limit:
                    mask, setter, time = bans[0]
                    self.track_ban(channel, setter, mask)
                    self.queue_mode(channel.name, 'b', False, str(mask))

                self.queue_mode(channel.name, 'b', True, str(b.banmask))
                self.queue_kick(channel.name, user.name, 'Banned by {}'.format(str(b.banner)))
                self.op_me(channel)

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
        bans = bans[limit:]
        for mask, setter, time in bans:
            self.track_ban(event.channel, setter, mask)
            self.queue_mode(event.channel.name, 'b', False, str(mask))
        if bans: self.op_me(event.channel)

    ### tasks ###

    @Modifier.repeat("clean_bans", time=15.0, autostart=True)
    def task_clean_bans(self):
        self.refresh_required = True
        for channel in self.bot.irc.channels:
            if channel not in self.channels: continue
            self.bot.irc.sendLine("MODE {} +b".format(channel))
