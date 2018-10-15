import datetime
import json
import os
import random
import re
import shutil
import subprocess
import time

# pocketsphinx
import speech_recognition as sr

# network
import requests

# local modules
from util import *
import admin
import commands
import data
import parse
import puzzle

def xtoi(s):
    s = s[1:]
    for (x, i) in zip(data.xsIn, data.ipaOut): s = s.replace(x, i)
    return s

def ordinal(n):
    return '{}{}'.format(n,
            'th' if n//10 % 10 == 1 else
            'st' if n % 10 == 1 else
            'nd' if n % 10 == 2 else
            'rd' if n % 10 == 3 else
            'th')

class Bot:

    def __init__(self, client):
        self.client = client
        self.prefix = '!'
        self.extprefix = '!!'

        with connect() as conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS nameid (
                name        TEXT UNIQUE NOT NULL,
                userid      INTEGER UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS perm (
                rule        TEXT NOT NULL,
                cmd         TEXT NOT NULL,
                userid      INTEGER NOT NULL,
                duration    REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS puztime (
                userid      INTEGER UNIQUE NOT NULL,
                nextguess   REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS puzhist (
                level       INTEGER PRIMARY KEY,
                userid      INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shocks (
                name        TEXT UNIQUE NOT NULL,
                num         INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS alias (
                src         TEXT UNIQUE NOT NULL,
                dest        TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feeds (
                url         TEXT NOT NULL,
                chat        INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ttt (
                gameid      INTEGER PRIMARY KEY,
                p1          INTEGER NOT NULL,
                p2          INTEGER NOT NULL,
                turn        INTEGER NOT NULL,
                board       TEXT NOT NULL
            );
            ''')

        self.dailied = False
        self.frink = subprocess.Popen('java -cp tools/frink/frink.jar:tools/frink SFrink'.split(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.quota = '(unknown)'
        self.recog = sr.Recognizer()
        self.soguess = None
        self.starttime = time.time()
        self.tioerr = ''
        self.wpm = dict()
        self.wump = None

    def checkwebsites(self):
        if hasattr(self, 'feeds'):
            for feed in self.feeds:
                for msg in feed.go():
                    for room in feed.rooms: client.send_message(room, msg)
        else:
            client.send_message(Chats.testing, 'WARNING: feeds not initialized @'+admin.username)
            self.feeds = []

    def get_reply(self, msg):
        return msg.reply_to_message if hasattr(msg, 'reply_to_message') else None

    def reply(self, msg, txt):
        print(txt)
        txt = txt.strip()
        if not txt: txt = '[reply empty]'
        if len(txt) > 4096: txt = '[reply too long]'
        self.client.send_message(msg.chat.id, txt, reply_to_message_id=msg.message_id)

    def reply_photo(self, msg, path):
        print(path)
        self.client.send_photo(msg.chat.id, path, reply_to_message_id=msg.message_id)

    def process_message(self, msg):
        self.client.forward_messages(Chats.ppnt, msg.chat.id, [msg.message_id])
        if msg.edit_date: return

        sid = str(msg.message_id)
        if len(str(msg.message_id)) > 3 and ( \
                len(set(sid)) == 1 or \
                list(map(abs, set(map(lambda x: int(x[1])-int(x[0]), zip(sid,sid[1:]))))) == [1] or \
                msg.message_id % 10000 == 0):
            self.reply(msg, '{} message hype'.format(ordinal(msg.message_id)))

        txt = msg.text
        if not txt: return

        if msg.chat.id == Chats.frink:
            self.reply(msg, commands.frink(self, msg, txt, ''))
            return

        is_cmd = txt[:len(self.prefix)] == self.prefix
        is_ext = txt[:len(self.extprefix)] == self.extprefix
        if is_cmd or is_ext:
            rmsg = self.get_reply(msg)
            buf = rmsg.text if rmsg else ''
            idx = len(self.extprefix) if is_ext else len(self.prefix)
            self.reply(msg, parse.parse(self, txt[idx:], buf, msg, is_ext))

        elif msg.from_user.id in self.wpm:
            (start, end, n) = self.wpm[msg.from_user.id]
            n += len(msg.text) + 1
            self.wpm[msg.from_user.id] = (start, msg.date, n)

        if txt[:len(admin.prefix)] == admin.prefix and msg.from_user.id == admin.userid:
            cmd, *args = txt[len(admin.prefix):].split(' ', 1)
            cmd = 'cmd_' + cmd
            args = (args or [None])[0]
            if hasattr(admin, cmd): self.reply(msg, getattr(admin, cmd)(self, args) or 'done')
            else: self.reply(msg, 'Unknown admin command.')

        matches = re.findall(r'\bx/[^/]*/|\bx\[[^]]*\]', txt)
        if matches:
            self.reply(msg, '\n'.join(map(xtoi, matches)))

        if txt[0] == '$' and txt[-1] == '$' and len(txt) > 2:
            # TODO adding a timeout is probably a good idea
            r = requests.get('https://latex.codecogs.com/png.latex?'+txt[1:-1], stream=True)
            with open('tex.png', 'wb') as f: shutil.copyfileobj(r.raw, f)
            self.reply_photo(msg, 'tex.png')
            os.remove('tex.png')

        for (pat, prob, resp) in data.triggers:
            if re.search(pat, txt) and random.random() < prob:
                self.reply(msg, resp(txt))

    def callback(self, client, update):
        print(update)
        self.process_message(update)

    def daily(self):
        pass
        #text = open('messages.txt').readlines()[datetime.date.today().toordinal()-736764].strip()
        #self.client.send_message(Chats.schmett, text)
        #self.client.send_message(Chats.haxorz, text)
        #self.client.send_message(Chats.duolingo, text)