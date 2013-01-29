import time
import jsocket
import socket
import logging

from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import Event, EventHandler

logger = logging.getLogger("jsocket")
logger.setLevel(logging.ERROR)

class JSockFactoryThread(jsocket.ServerFactoryThread):
    callback = None

    def __init__(self, callback):
        super(JSockFactoryThread, self).__init__()
        self.callback = callback
        self.timeout = 2.0

    def _process_message(self, obj):
        if obj != "":
            if obj['function'] != "":
                args = obj['args']
                if obj['args'] == "":
                    args = []
                self.callback(obj['function'], args)

class ServerFactoryWithCallback(jsocket.ServerFactory):
    callback = None

    def __init__(self, server_thread, callback, **kwargs):
        super(ServerFactoryWithCallback, self).__init__(server_thread, **kwargs)
        self.callback = callback

    def run(self):
        while self._isAlive:
            tmp = self._thread_type(self.callback)
            self._purge_threads()
            while not self.connected and self._isAlive:
                try:
                    self.accept_connection()
                except socket.timeout as e:
                    logger.debug("socket.timeout: %s" % e)
                except Exception as e:
                    logger.exception(e)
                else:
                    tmp.swap_socket(self.conn)
                    tmp.start()
                    self._threads.append(tmp)
                    break
        self._wait_to_exit()
        self.close()

@Plugin.register(depends=["commands"])
class JSockPlugin(Plugin):
    server = None
    bot = None

    @EventHandler("PluginsLoaded")
    def handle_reload(self, event):
        self.auto_load = self.get_config().get("auto_load", False)
        self.port = self.get_config().get('port', 5489)
        self.timeout = self.get_config().get('timeout', 2.0)
        self.get_config()['port'] = self.port
        self.get_config()['timeout'] = self.timeout
        self.get_config()['auto_load'] = self.auto_load
        self.save_config()
        if self.auto_load:
            self._start_server()

    def _start_server(self):
        self.server = ServerFactoryWithCallback(JSockFactoryThread, callback=self.function_received, port=self.port)
        self.server.timeout = self.timeout
        self.server.start()

    def function_received(self, function, args):
        print "Got function %s" % (function)
        if function == "say":
            print "sending message"
            self.send_message('#llama5', '%s' % (', '.join(args)))

    @Modifier.command("jsock")
    def jsock_command(self, context):
        self._start_server()
        context.reply("Started jsock")

    def teardown(self):
        self._stop()

    def _stop(self):
        self.server.stop()
        self.server.join()


if __name__ == '__main__':

    def test(function, args):
        print "Got function %s" % (function)
    server = ServerFactoryWithCallback(JSockFactoryThread, test)
    server.timeout = 2.0
    server.start()

    time.sleep(1)
    cPids = []
    for i in range(10):
        client = jsocket.JsonClient()
        cPids.append(client)
        client.connect()
        client.send_obj({"function": "test", "args": ["llama", "arg2", "arg3"]})

    #time.sleep(2)
    for c in cPids:
        c.close()
    server.stop()
    server.join()
