from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler
from ZomgBot.ircglob import glob, matches

from datetime import datetime
import re

from sqlalchemy import Column, DateTime, Integer, String, Text

from twisted.internet import reactor

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

@Plugin.register(depends=["commands", "tasks"], uses_db=True)
class BanManager(Plugin):
    refresh_required = False

    def setup(self):
        self.wait = []

    @staticmethod
    def glob_to_like_expr(pattern):
        return pattern.replace('*', '%').replace('?', '_')

    def kick_banned(self, channel, mask, banner, reason=None):
        for name, user in channel.users.items():
            print mask, user, user.hostmask, user.username, user.hostname
            if matches(mask, user.hostmask):
                self.bot.irc.kick(str(channel), user.name, 'Banned by {}'.format(banner) + (': {}'.format(reason) if reason else ''))
        self.wait.remove(mask)

    def find_ban(self, channel, hostmask):
        return self.db.query(Ban).\
            filter(Ban.channel == channel).\
            filter(":mask LIKE ban_exp").params(mask=hostmask).\
            first()

    def track_ban(self, channel, user, mask):
        count = self.db.query(Ban).filter(Ban.banmask == mask).count()
        if count >= 1:
            return

        ban = Ban(time    = datetime.now(),
                  channel = str(channel),
                  banmask = mask,
                  ban_exp = self.glob_to_like_expr(mask),
                  banner  = user,
                  reason  = '')
        self.db.add(ban)
        self.db.commit()

        self.wait.append(mask)

        reactor.callLater(5, self.kick_banned, channel, mask, banner=user)

    def update_ban(self, mask, reason=None, banner=None):
        ban = self.db.query(Ban).filter(Ban.banmask == mask).first()
        if ban:
            if reason: ban.reason = reason
            if banner: ban.banner = banner

        self.db.commit()

    @Modifier.command("untrack")
    def cmd_unban(self, context):
        self.remove_ban(context.args[0])

    def remove_ban(self, mask):
        r = self.db.query(Ban).filter(Ban.banmask == mask).delete()
        self.db.commit()
        return r > 0

    @EventHandler("ModeSet")
    def on_ModeSet(self, event):
        if event.letter != 'b': return
        self.track_ban(event.channel, event.user.name, event.param)

    @EventHandler("ModeCleared")
    def on_ModeCleared(self, event):
        if event.letter != 'b' or event.user.name == self.bot.irc.nickname: return
        self.remove_ban(event.param)

    @EventHandler("UserJoinedChannel")
    def on_UserJoinedChannel(self, event):
        b = self.find_ban(event.channel.name, event.user.hostmask)
        if not b: return

        self.bot.irc.mode(event.channel.name, True, 'b', mask=str(b.banmask))
        self.bot.irc.kick(event.channel.name, event.user.name, str('Banned by {}'.format(b.banner) + (': {}'.format(b.reason) if b.reason else '')))

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

    @Modifier.repeat("clean_bans", time=15.0, autostart=True)
    def task_clean_bans(self):
        self.refresh_required = True
        for channel in self.bot.irc.channels:
            self.bot.irc.sendLine("MODE {} +b".format(channel))
    
    @EventHandler("BanlistUpdated")
    def on_BanlistUpdated(self, event):
        limit = int(self.bot.irc.supported.getFeature("MAXBANS", 50) * 2.0/3.0)
        bans = event.channel.bans[limit:]
        for mask, setter, time in sorted(bans, key=lambda t: t[1]):
            self.track_ban(event.channel, setter, mask)
            self.bot.irc.mode(event.channel.name, False, 'b', mask=str(mask))
