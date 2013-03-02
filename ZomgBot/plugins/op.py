from ZomgBot.plugins import Plugin
from ZomgBot.events import EventHandler
from ZomgBot.bot import IRCChannel

from string import Template

from twisted.internet import reactor

# op management plugin
#  api:
#   plugin.line(channel, line)               # queue an arbitrary line to a channel
#   plugin.kick(channel, user, message)      # queue a kick on channel for user `user` with reason `message`
#   plugin.notice(channel, user, message):   # queue a notice `message` to user `user`
#   plugin.mode(channel, letter, set_, arg): # queue a mode change on `channel`
#   plugin.run_queue(channel)                # run the queue for channel
#  `channel` parameters always accept either a str, or a ZomgBot.bot.IRCChannel

@Plugin.register(depends=["permission"])
class Op(Plugin):
    def setup(self):
        self.line_queue = {}
        self.mode_queue = {}
        self.op = set()
        self.deop = {}

    def _send_line(self, line):
        self.bot.irc.sendLine(line)

    def _channel_or_str(self, channel):
        if isinstance(channel, IRCChannel):
            return str(channel.name)
        return channel

    def _get_deop_time(self, channel):
        channel = self._channel_or_str(channel)
        time = self.get_config().get("deop", {}).get(channel, 0)
        if isinstance(time, basestring) and time.lower() == "never":
            return -1
        else:
            return time

    def line(self, channel, line):
        l = self.line_queue.setdefault(channel, [])
        l.append(line)
    
    def kick(self, channel, user, reason):
        channel = self._channel_or_str(channel)
        self.line(channel, "KICK {} {} :{}".format(channel, user, reason))

    def notice(self, channel, user, message):
        channel = self._channel_or_str(channel)
        self.line(channel, "NOTICE {} :{}".format(user, message)) 

    def mode(self, channel, letter, set_, arg=None):
        channel = self._channel_or_str(channel)
        l = self.mode_queue.setdefault(channel, [])
        l.append((letter, set_, arg))

    def _mode_order(self, t):
        letter, set_, arg = t
        if t == ("o", False, self.bot.irc.nickname):
            return 10
        elif set_ == True:
            return 5
        else:
            return 0

    def _do_modes(self, channel):
        lines = []
        queue = sorted(self.mode_queue.get(channel, []), key=self._mode_order)
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
        map(self._send_line, lines)

    def _do_deop(self, channel):
        if channel in self.deop: del self.deop[channel]
        if channel in self.op: self.op.remove(channel)
        self.bot.irc.mode(str(channel), False, 'o', user=self.bot.irc.nickname)

    def _got_op(self, channel):
        deop_instantly = self._get_deop_time(channel) == 0
        if channel in self.mode_queue:
            if deop_instantly and channel not in self.line_queue:
                if channel in self.deop: del self.deop[channel]
                self.op.remove(channel)
                self.mode(channel, 'o', False, self.bot.irc.nickname)
            self._do_modes(channel)
        if channel in self.line_queue:
            map(self._send_line, self.line_queue[channel])
            del self.line_queue[channel]
            if deop_instantly:
                self._do_deop(channel)
        if not deop_instantly:
            if channel in self.deop:
                delay = self._get_deop_time(channel)
                if delay >= 0:
                    self.deop[channel].reset(delay)
            else:
                delay = self._get_deop_time(channel)
                if delay >= 0:
                    self.deop[channel] = reactor.callLater(delay, self._do_deop, channel)

    def run_queue(self, channel):
        channel = self._channel_or_str(channel)
        if channel in self.op:
            return self._got_op(channel)
        if channel not in self.mode_queue and channel not in self.line_queue: return
        command = Template(self.get_config().get("op_command", "PRIVMSG ChanServ :OP $channel $nick")).\
                               safe_substitute(channel=channel, nick=self.bot.irc.nickname)
        self._send_line(command)

    @EventHandler("ModeSet")
    def on_ModeSet(self, event):
        if event.letter == 'o' and event.param == self.bot.irc.nickname:
            self.op.add(event.channel.name)
            self._got_op(event.channel.name)

    @EventHandler("ModeCleared")
    def on_ModeCleared(self, event):
        if event.letter == 'o' and event.param == self.bot.irc.nickname:
            if event.channel.name in self.op: self.op.remove(event.channel.name)
