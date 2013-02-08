from ZomgBot.plugins import Plugin, Modifier
from datetime import datetime
import socket

@Plugin.register(depends=["tasks", "auth", "permission", "matches", "commands"])
class Minecraft(Plugin):

    @Modifier.repeat("minecraft", time=10.0, autostart=True)
    def minecraft_lookup(self):
        self.server_status = {}
        self.lastcheck = datetime.utcnow()
        servers = self.get_config()["servers"]

        for k, v in servers.iteritems():
            print k
            print v
            host = None
            if v.has_key('host'):
                host = v["host"]
            else:
                print "Host does not have proper host assigned {}".format(v)
                continue
            port = 25565
            if v.has_key('port'):
                port = int(v["port"])

            status = self.get_info(host, port)
            print status
            if not status:
                self.server_status["{}:{}".format(host,port)] = None
                #self.send_message('#llama5', '{}:{} appears to be down'.format(host, port))
            else:
                self.server_status["{}:{}".format(host,port)] = status
                #self.send_message('#llama5', '{}:{}: {} {}/{}'.format(host, port, status["motd"], status["players"], status["max_players"]))

    def get_info(self, host, port):
        try:
            #Set up our socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((host, port))

            #Send 0xFE: Server list ping
            s.send('\xfe')
            #Send a payload of 0x01 to trigger a new response if the server supports it
            s.send('\x01')

            #Read as much data as we can (max packet size: 241 bytes)
            d = s.recv(256)
            s.close()

            #Check we've got a 0xFF Disconnect
            assert d[0] == '\xff'

            #Remove the packet ident (0xFF) and the short containing the length of the string
            #Decode UCS-2 string
            d = d[3:].decode('utf-16be')

            #If the response string starts with simolean1, then we're dealing with the new response
            if (d.startswith(u'\xa7' + '1')):
                d = d.split(u'\x00')
                #Return a dict of values
                return {'protocol_version': int(d[1]),
                        'minecraft_version':    d[2],
                        'motd':                 d[3],
                        'players':          int(d[4]),
                        'max_players':      int(d[5])}
            else:
                d = d.split(u'\xa7')
                #Return a dict of values
                return {'motd':         d[0],
                        'players':   int(d[1]),
                        'max_players': int(d[2])}

        except Exception, e:
            print e
            return False

    def timesince(self, dt, default="just now"):
        """
        Returns string representing "time since" e.g.
        3 days ago, 5 hours ago etc.

        From: http://flask.pocoo.org/snippets/33/
        """

        now = datetime.utcnow()
        diff = now - dt
        
        periods = (
            (diff.days / 365, "year", "years"),
            (diff.days / 30, "month", "months"),
            (diff.days / 7, "week", "weeks"),
            (diff.days, "day", "days"),
            (diff.seconds / 3600, "hour", "hours"),
            (diff.seconds / 60, "minute", "minutes"),
            (diff.seconds, "second", "seconds"),
        )

        for period, singular, plural in periods:
            
            if period:
                return "%d %s ago" % (period, singular if period == 1 else plural)

        return default

    @Modifier.command("status")
    def status(self, context):
        items = []
        if not self.server_status:
            context.reply("Please wait")
        else:
            for k, v in self.server_status.iteritems():
                if v == None:
                    items.append("{} down".format(k))
                else:
                    items.append("{}: [{}/{}]".format(v["motd"], v["players"], v["max_players"]))
            items.append("Checked {}".format(self.timesince(self.lastcheck)))

            context.reply(' | '.join(items))

    @Modifier.match("^\$botnick\$: is (c|p|s) up")
    def check_server(self, m, context):
        s = m.groups()[0]
        print m.groups()
        server = None
        if s == 'c':
            server = 'c.nerd.nu:25565'
        elif s == 'p':
            server = 'p.nerd.nu:25565'
        else:
            server = 's.nerd.nu:25565'

        if self.server_status.has_key(server):
            stat = self.server_status[server]
            if stat == None:
                context.reply("{} down".format(server))
            else:
                context.reply("{}: [{}/{}]".format(stat["motd"], stat["players"], stat["max_players"]))
        else:
            context.reply("WAT?!")