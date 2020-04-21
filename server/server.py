#! /usr/bin/env python3

import os
import sys
import socket
import threading
import json

bitrate_table = {
        '240p' : 640000,
        '360p' : 960000,
        '432p' : 1150000,
        '480p' : 1280000,
        '576p' : 1920000,
        '720p' : 2560000,
        '1080p': 5120000,
}

class socketError(Exception):
        pass

class fileError(Exception):
        pass

class packageResolver:
        def __init__(self, path):
                self.path = path
                try:
                        self.files = os.listdir(self.path)
                        jsonFile = open(self.path + '/vid_conf.json', 'r')
                        self.jsonData = json.load(jsonFile)
                        jsonFile.close()
                except os.error:
                        print('file open failed')
                        raise fileError
                self.clip_length = self.jsonData['clip_length']
                self.total_length = self.jsonData['total_length']
                self.cnt240p = self.jsonData['240p']['0']
                self.cnt360p = self.jsonData['360p']['0']
                self.cnt432p = self.jsonData['432p']['0']
                self.cnt480p = self.jsonData['480p']['0']
                self.cnt576p = self.jsonData['576p']['0']
                self.cnt720p = self.jsonData['720p']['0']
                self.cnt1080p = self.jsonData['1080p']['0']
                        
        def getStat(self):
                stat = bitrate_table.copy()
                stat['clip'] = self.clip_length
                stat['total'] = self.total_length
                return stat

        def getFp(self, conf, idx):
                if conf not in bitrate_table:
                        return None
                count = self.jsonData[conf]['0']
                if (idx > count) or (idx < 1) or (not isinstance(idx, int)):
                        return None
                path= self.path + '/vid_' + conf + '_' + str(idx)
                try:
                        fp = open(path, 'rb')
                except:
                        print('open file "' + path + '" failed')
                        raise fileError
                return fp

                

class connection:
        def __init__(self, host, port):
                self.host = host
                self.port = port
                try:
                        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        self.socket.bind((self.host, self.port))
                        self.socket.listen(5)
                except (socket.error, socket.herror, socket.gaierror):
                        raise socketError

        def accept(self):
                return self.socket.accept()


class clientThread(threading.Thread):
        def __init__(self, clientaddr, clientsocket, pkgResolver):
                threading.Thread.__init__(self)
                self.csocket = clientsocket
                self.caddr = clientaddr
                self.pkgResolver = pkgResolver
        
        def run(self):
                while True:
                        conf = self.csocket.recv(1024)
                        if not conf: 
                                continue
                        if conf == b'head':
                                stat = self.pkgResolver.getStat()
                                self.csocket.send(bytes(json.dumps(stat), 'utf-8'))
                        elif conf == b'end':
                                print('connection closed')
                                self.csocket.close()
                                exit()
                        else:
                                conf = conf.decode(encoding="utf-8").split(',')
                                if conf[0] not in bitrate_table:
                                        print('bitrate setting err')
                                        continue
                                fp = self.pkgResolver.getFp(conf[0], int(conf[1]))
                                if fp == None:
                                        print('file err')
                                        continue
                                print('starting transfer file ' + str(conf[1]))
                                l = fp.read(1024)
                                while (l):
                                        self.csocket.send(l)
                                        l = fp.read(1024)
                                fp.close()
                                self.csocket.send(b'f_end')
                                print('file transfer complete')


if __name__ == '__main__':
        pkgResolver = packageResolver('./video')
        try:
                conn = connection('127.0.0.1', 51234)
        except socketError:
                print('Unable to open socket')
        
        print('Server online')

        while True:
                c, addr = conn.accept()
                print('Connected to :', addr[0], ':', addr[1]) 
                newThread = clientThread(addr, c, packageResolver('./video'))
                newThread.start()

                

