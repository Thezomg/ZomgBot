import jsocket
from time import sleep
import sys
client = jsocket.JsonClient(port=5489)
client.connect()
client.send_obj({"function": "say", "args": [sys.argv[1]]})
sleep(1)
client.close()
