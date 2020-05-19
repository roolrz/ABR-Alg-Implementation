#! /usr/bin/env python3

import os
import sys
import socket
import json
import signal

bitrate_table = {
        '240p' : 400000,
        '360p' : 960000,
        '432p' : 1150000,
        '480p' : 2560000,
        '576p' : 1920000,
        '720p' : 2560000,
        '900p' : 5120000,
        '1080p': 10240000,
        '1440p': 20480000,
        '2160p': 40960000,
}

class socketError(Exception):
        pass

class fileError(Exception):
        pass

class configError(Exception):
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

                
class speedLimiter:
        def __init__(self, config):
                self.filedir = '../sabre/example/tomm19/' + config
                f = open(self.filedir)
                self.records = json.load(f)
                f.close()
                self.recordMax = len(self.records)
                self.recordIdx = 0
                self.startFlag = False
                self.currentLatency = 0
                print('Using "'+self.filedir+'"')
        
        def printRecords(self):
                print(self.records)

        def getCurrentLatency(self):
                return self.currentLatency

        def __timerhandler(self, signum, frame):
                if self.startFlag == False:
                        return
                self.recordIdx = self.recordIdx + 1
                if self.recordIdx == self.recordMax:
                        self.recordIdx = 0
                signal.setitimer(signal.ITIMER_REAL, self.records[self.recordIdx]['duration_ms']/1000)
                if self.records[self.recordIdx]['bandwidth_kbps'] == 0:
                        self.records[self.recordIdx]['bandwidth_kbps'] = 1
                os.system("sudo tc qdisc change dev eth0 root tbf rate " + str(self.records[self.recordIdx]['bandwidth_kbps']) + "kbit burst 4kb latency " + str(self.records[self.recordIdx]['latency_ms']) +"ms")
                print('Limited network at %d kbps and %d ms latency for %d ms'%(self.records[self.recordIdx]['bandwidth_kbps'], self.records[self.recordIdx]['latency_ms'], self.records[self.recordIdx]['duration_ms']))

        def start(self):
                if self.startFlag:
                        return
                signal.signal(signal.SIGALRM, self.__timerhandler)
                signal.setitimer(signal.ITIMER_REAL, self.records[self.recordIdx]['duration_ms']/1000)
                os.system("sudo tc qdisc del dev eth0 root")
                if self.records[self.recordIdx]['bandwidth_kbps'] == 0:
                        self.records[self.recordIdx]['bandwidth_kbps'] = 1
                os.system("sudo tc qdisc add dev eth0 root tbf rate " + str(self.records[self.recordIdx]['bandwidth_kbps']) + "kbit burst 4kb latency " + str(self.records[self.recordIdx]['latency_ms']) +"ms")
                self.startFlag = True
                self.currentLatency = self.records[self.recordIdx]['latency_ms']
                print('Limited network at %d kbps and %d ms latency for %d ms'%(self.records[self.recordIdx]['bandwidth_kbps'], self.records[self.recordIdx]['latency_ms'], self.records[self.recordIdx]['duration_ms']))

        def stop(self):
                if not self.startFlag:
                        return
                os.system("sudo tc qdisc del dev eth0 root")
                self.startFlag = False

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

        def connect(self):
                return self.socket.connect()


class client:
        def __init__(self, clientaddr, clientsocket, pkgResolver, spdLimiter):
                self.csocket = clientsocket
                self.caddr = clientaddr
                self.pkgResolver = pkgResolver
                self.spdLimiterClass = spdLimiter
                self.speedtested = False
                self.speedLimit = False
        
        def run(self):
                while True:
                        conf = self.csocket.recv(4096)
                        if not conf: 
                                continue
                        if b'speedteststart' == conf and not self.speedtested:
                                self.speedtested = True
                                teststr = b'\x7c'*4096
                                print('Testlen %d'%(len(teststr)*256/1024) + 'KB')
                                for idx in range(256):
                                        _ = idx # ignore compiler warnings
                                        self.csocket.send(teststr)
                                self.csocket.send(b'end')
                        elif b'limitstart' in conf:
                                self.spdLimiter = self.spdLimiterClass(conf.decode(encoding='utf-8').split(',')[1])
                                self.speedLimit = True
                                self.spdLimiter.start()
                        elif conf == b'limitstop':
                                self.spdLimiter.stop()
                        elif conf == b'head':
                                stat = self.pkgResolver.getStat()
                                self.csocket.send(bytes(json.dumps(stat), 'utf-8'))
                        elif conf == b'end':
                                self.spdLimiter.stop()
                                self.csocket.close()
                                print('connection from %s:%s closed'%(self.caddr[0], self.caddr[1]))
                                break
                        else:
                                conf = conf.decode(encoding="utf-8").split(',')
                                if conf[0] not in bitrate_table:
                                        print('%s bitrate setting err'%conf[0])
                                        continue
                                fp = self.pkgResolver.getFp(conf[0], int(conf[1]))
                                if fp == None:
                                        print('file %d err'%int(conf[1]))
                                        continue
                                print('starting transfer file ' + str(conf[1]))
                                if self.speedLimit:
                                        l = str(self.spdLimiter.getCurrentLatency()).encode(encoding="utf-8") + fp.read(4090)
                                else:
                                        l = fp.read(4096)
                                while (l):
                                        self.csocket.send(l)
                                        l = fp.read(4096)
                                fp.close()
                                self.csocket.send(b'f_end')
                                print('file transfer complete')

if __name__ == '__main__':
        try:
                conn = connection('0.0.0.0', 51234)
        except socketError:
                print('Unable to open socket')
                exit()
        
        print('Server online')
        while True:
                c, addr = conn.accept()
                print('Connected to :', addr[0], ':', addr[1]) 
                client(addr, c, packageResolver('./video'), speedLimiter).run()

                

