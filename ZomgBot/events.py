from twisted.internet.defer import maybeDeferred, succeed
from copy import copy

class StopPropagating(Exception):
    pass

class CancelEvent(StopPropagating):
    pass

class EventDispatcher(object):
    handlers = {}

    def __init__(self, name=None):
        self.name = name

    def eventErrback(self, err, event, plugin):
        if err.check(StopPropagating): return err
        print "ERROR PROCESSING EVENT {} (from {})".format(event, plugin)
        print err
        return True
    
    def eventPostErrback(self, err, event):
        r = err.check(StopPropagating)
        if r:
            return r != CancelEvent
        else:
            print "Unexpected error in execution chain for event {}."
            print err
            return True

    def eventCallback(self, result, event):
        print "{} processed successfully!".format(event)
        return result

    def dispatchEvent(self, event, name=None):
        name = name or event.name
        print "{} dispatching {}".format(self.name, name)
        rm = copy(self.handlers.get(name, []))
        rm.sort(key=lambda t: t[2])
        def nextHandler(_=None):
            if not rm: return succeed(True)
            plugin, method = rm.pop(0)[:2]
            r = maybeDeferred(method, event)
            r.addCallback(nextHandler)
            return r
        result = nextHandler()
        result.addCallbacks(self.eventCallback, self.eventPostErrback, callbackArgs=(name,), errbackArgs=(name,))
        return result
    
    def addEventHandler(self, plugin, event, method, priority=0):
        print "{} adding handler for {} (p={}): {}".format(self.name, event, priority, method)
        self.handlers.setdefault(event, [])
        self.handlers[event].append((plugin, method, priority))

    def unregisterAll(self):
        handlers = {}

    def unregisterHandlers(self, plugin):
        print "{} removing handlers for {}".format(self.name, plugin)
        self.handlers = dict((k, [h for h in handlerSet if h[0] != plugin]) for k, handlerSet in self.handlers.items())

class Event(dict):
    def __getattr__(self, k):
        return self[k]

def EventHandler(event=None, priority=0):
    def inner(fn):
        fn.plugin = None
        fn.event = getattr(fn, "event", [])
        fn.event.append((event, priority))
        return fn
    return inner
