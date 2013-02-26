from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler
from ZomgBot.ircglob import glob, matches

from datetime import datetime
import re

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql.expression import null

from twisted.internet import reactor

Base = Plugin.declarative_base("tell")

class Message(Base):
    id = Column(Integer, primary_key=True)
    sender = Column(String)
    to = Column(String)
    message = Column(String)
    channel = Column(String)
    date = Column(DateTime)

    def __init__(self, sender, to, channel, message, date):
        self.sender = sender
        self.to = to.lower()
        self.message = message
        self.date = date
        self.channel = channel.lower()

    def __repr__(self):
        return "<Message('{self.sender}', '{self.to}', '{self.channel}', '{self.message}', '{self.date}')>".format(self=self)

@Plugin.register(depends=["commands", "paste"], uses_db=True)
class Tell(Plugin):

    @Modifier.command("tell")
    def cmd_tell(self, context):
        if context.channel == None:
            src = "pm"
        else:
            src = context.channel.name

        msg = Message(context.user.name, context.args[0], src, ' '.join(context.args[1:]), datetime.now())   

        self.db.add(msg)
        self.db.commit()

        context.reply('{}, I will let {} know.'.format(context.user.name, context.args[0]))

    def get_message_query(self, user, zones):
        zones.append(null())
        zones.append('')
        return self.db.query(Message).filter((Message.to == user.name.lower()) & (Message.channel.in_(zones)))

    def handle_messages(self, event, zones):
        query = self.get_message_query(event.user, zones)
        msgs = query.all()
        query.delete(synchronize_session='fetch')
        self.db.commit()
        to_send = []
        to_send_priv = []
        for m in msgs:
            if m.channel == "pm":
                to_send_priv.append('{user}: [{date}] <{sender}> {message}'.format(user=event.user.name, date=m.date.strftime('%Y-%m-%d %H:%M:%S GMT'), sender=m.sender, message=m.message))
            else:
                to_send.append('{user}: [{date}] <{sender}> {message}'.format(user=event.user.name, date=m.date.strftime('%Y-%m-%d %H:%M:%S GMT'), sender=m.sender, message=m.message))


        paste = self.parent.get_plugin("paste")
        if len(to_send) > 0:
            if len(to_send) < 4:
                event.channel.say("\n".join(to_send))
            else:
                url = paste.paste("\n".join(to_send), expire=30*60, title='messages for {}'.format(event.user.name))
                event.channel.say('{}, your messages: {}'.format(event.user.name, url))

        if len(to_send_priv) > 0:
            if len(to_send_priv) < 4:
                event.user.say("\n".join(to_send_priv))
            else:
                url = paste.paste("\n".join(to_send_priv), expire=30*60, title='private messages for {}'.format(event.user.name))
                event.user.say('your messages: {}'.format(url))


    @EventHandler("ChannelMsg")
    def handle_chanmsg(self, event):
        self.handle_messages(event, zones=[event.channel.name, "pm"])


    @EventHandler("PrivateMsg")
    def handle_privmsg(self, event):
        self.handle_messages(event, zones=["pm"])