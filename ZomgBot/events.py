class EventDispatcher(object):
    handlers = {}

    def __init__(self, name=None):
        self.name = name

    def dispatchEvent(self, event, name=None):
        name = name or event.name
        print "{} dispatching {}".format(self.name, name)
        for plugin, method in self.handlers.get(name, set()):
            method(event)
    
    def addEventHandler(self, plugin, event, method):
        print "{} adding handler for {}: {}".format(self.name, event, method)
        self.handlers.setdefault(event, set())
        self.handlers[event].add((plugin, method))

    def unregisterAll(self):
        handlers = {}

    def unregisterHandlers(self, plugin):
        handlers = [(k, set(h for h in handlerSet if h[0] != plugin)) for k, handlerSet in self.handlers.items()]

class Event(dict):
    def __getattr__(self, k):
        return self[k]

def EventHandler(event=None, priority=2):
    def inner(fn):
        fn.plugin = None
        fn.event = getattr(fn, "event", [])
        fn.event.append((event, priority))
        return fn
    return inner
