import time
import jsocket
import socket
import logging

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

class JSockPlugin():
    server = None
    bot = None

    def __init__(self, bot, port=5489, timeout=2.0):
        self.bot = bot
        self.server = ServerFactoryWithCallback(JSockFactoryThread, callback=self.function_received, port=port)
        self.server.timeout = timeout

    def function_received(self, function, args):
        print "Got function %s" % (function)
        if function == "say":
            print "sending message"
            self.bot.send_message('#llama', 'function called, %s(%s)' % (function, ', '.join(args)))

    def start(self):
        self.server.start()

    def stop(self):
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
