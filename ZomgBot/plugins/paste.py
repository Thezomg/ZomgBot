from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

import urllib
import urllib2
import json

from datetime import datetime

@Plugin.register(depends=["commands"])
class Paste(Plugin):

    def paste(self, data, title=None, expire=None, private=True, language="text", password=None, user="ZomgBot"):
        paste_url = self.get_config().get("paste_url", "http://paste.thezomg.com/")
        data_key = self.get_config().get("data_key", "paste_data")
        expire_key = self.get_config().get("expire_key", "paste_expire")
        private_key = self.get_config().get("private_key", "paste_private")
        private_type = self.get_config().get("private_type", "bool")
        password_key = self.get_config().get("password_key", "paste_password")
        user_key = self.get_config().get("user_key", "paste_user")
        title_key = self.get_config().get("title_key", "paste_title")
        lang_key = self.get_config().get("lang_key", "paste_lang")
        extra_post = self.get_config().get("extra", "api_submit=true&mode=json")
        private_url = self.get_config().get("private_url", "http://paste.thezomg.com/{id}/{hash}")
        public_url = self.get_config().get("public_url", "http://paste.thezomg.com/{id}")

        paste_data = dict()

        if data_key and data:
            paste_data[data_key] = data

        if expire_key and expire:
            paste_data[expire_key] = expire

        if private_key:
            if private_type == "bool":
                paste_data[private_key] = private
            else:
                paste_data[private_key] = "1" if private else "0"

        if password_key and password:
            paste_data[password_key] = password

        if user_key and user:
            paste_data[user_key] = user

        if title_key and title:
            paste_data[title_key] = title

        if lang_key and language:
            paste_data[lang_key] = language

        encoded_post = urllib.urlencode(paste_data)

        if extra_post:
            encoded_post = "{}&{}".format(encoded_post, extra_post)

        req = urllib2.urlopen(paste_url, encoded_post)
        data = req.read()

        if data:
            data = json.loads(data)

            if private:
                return private_url.format(**data['result'])
            else:
                return public_url.format(**data['result'])
        else:
            return "Error pasting"
