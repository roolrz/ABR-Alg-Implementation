#! /usr/bin/env python3

import socket
import json
import math
import os
import datetime
import sys
import signal
import asyncio

HOST = '192.168.2.15'    # The remote host
PORT = 51234             # The same port as used by the server

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

class alg:
        def __init__(self):
                pass

        def getDesiredBitrate(self):
                pass

class connection:
        def __init__(self, host, port):
                self.host = host
                self.port = port
                try:
                        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                except (socket.error, socket.herror, socket.gaierror):
                        raise socketError

        def connect(self):
                try:
                        self.socket.connect((self.host, self.port))
                except (socket.error, socket.herror, socket.gaierror):
                        raise socketError
                return self.socket

class speedMeasurement:
        def __init__(self, durination):
                self.size = 0
                self.durination = durination
                self.bufferList = []
                self.bufferUsage = 0
                self.bufferLock = asyncio.Lock()
                self.vidPlay = False
                self.vidPlayCount = 0

        def getVidTimeStamp(self):
                return self.vidPlayCount

        def getVidStatus(self):
                return self.vidPlay

        def vidStart(self):
                self.vidPlay = True
                self.vidPlayCount = 0

        def vidStop(self):
                self.vidPlay = False
                self.vidPlayCount = 0

        def vidPause(self):
                self.vidPlay = False

        def vidContinue(self):
                self.vidPlay = True

        def __updateBufferSize(self):
                totalSize = 0
                for buffer in self.bufferList:
                        totalSize = totalSize + buffer['time']
                self.bufferUsage = totalSize

        def getBufferUsage(self):
                return self.bufferUsage

        def __calVidStatus(self):
                if self.vidPlay == True:
                        if len(self.bufferList) == 0:
                                print('Status : Video play buffering')
                                self.vidPause()
                else:
                        if len(self.bufferList) > 0:
                                print('Status : Video play resumed')
                                self.vidContinue()
        
        async def bufferReduce(self, time):
                async with self.bufferLock:
                        self.bufferList[0]['time'] = self.bufferList[0]['time'] - time
                        if self.bufferList[0]['time'] <= 0:
                                        self.bufferList.pop(0)
                        self.vidPlayCount = self.vidPlayCount + 1
                        self.__updateBufferSize()

        def __handler(self, signum, frame):
                signal.alarm(self.durination)
                self.__calVidStatus()
                if self.vidPlay:        # Current player count
                        asyncio.run(self.bufferReduce(1))

        def start(self):
                signal.signal(signal.SIGALRM, self.__handler)
                signal.alarm(self.durination)

        def stop(self):
                signal.signal(signal.SIGALRM, signal.SIG_DFL)
                signal.alarm(0)
                self.size = 0

        def convertBitrateToStr(self, value):
                for string, bitrate in bitrate_table.items():
                        if value == bitrate:
                                return string
                return None

        async def VidBufferAdd(self, time, bitrate):
                async with self.bufferLock:
                        self.bufferList.append({'time' : time, 'bitrate' : bitrate})
                        self.__updateBufferSize()

        def getStatistics(self):
                return self.stat

class bufferAlg(alg):
        #       Buffer-based Alg (referred https://arxiv.org/pdf/1601.06748.pdf and http://yuba.stanford.edu/~nickm/papers/sigcomm2014-video.pdf)
        def __init__(self, measure, bitrateTable, initialBitrate = 0, buffersize = 25, reservoir = 10, upperReservoir = 5):
                self.buffersize = buffersize
                self.measure = measure
                self.reservoir = reservoir
                self.bitrate = initialBitrate
                self.upperReservoir = upperReservoir
                self.bitrateTable = list(bitrateTable)

        def getIfBufferFull(self):
                if self.buffersize < self.measure.getBufferUsage():
                        return True
                else:
                        return False

        def getDesiredBitrate(self):
                bufferUsage = self.measure.getBufferUsage()
                print('buffer:'+str(bufferUsage))
                if bufferUsage < self.reservoir:
                        return self.bitrateTable[0] # Should choose the lowest bitrate

                if bufferUsage > self.buffersize-self.upperReservoir:
                        return self.bitrateTable[-1] # Should choose the highest bitrate

                xlen = self.buffersize - self.reservoir - self.upperReservoir
                ylen = self.bitrateTable[-1] - self.bitrateTable[0]
                ratio = ylen/xlen
                bitrate = (bufferUsage - self.reservoir)*ratio + self.bitrateTable[0]
                realbit = self.bitrateTable[0]
                for bitset in self.bitrateTable:
                        if bitset < bitrate:
                                realbit = bitset
                return realbit
        

class player:
        def __init__(self, socket, measure, path, alg):
                self.socket = socket
                self.measure = measure(1)
                self.path = path + '/vid_'
                self.alg = alg(self.measure, bitrate_table.values(), initialBitrate = 0, buffersize = 25, reservoir = 5, upperReservoir = 5)

        def preprocess(self):
                self.socket.send(b'head')
                data = self.socket.recv(4096)
                data = data.decode(encoding="utf-8")
                self.head = json.loads(data)
                self.total = self.head['total']
                self.clip = self.head['clip']
                self.count = math.ceil(self.total/self.clip)

        def determineBitrate(self):
                # Check Buffering
                return self.alg.getDesiredBitrate()

        def start(self):
                self.measure.start()

                for idx in range(1, self.count+1):
                        while(self.alg.getIfBufferFull() == True):
                                pass
                        bitrate = self.determineBitrate()
                        bitrateS = self.measure.convertBitrateToStr(bitrate)
                        self.socket.send(bitrateS.encode(encoding="utf-8") + b',' + str(idx).encode(encoding="utf-8"))
                        print('bitrate setting for clip ' + str(idx) + ' is ' + bitrateS)
                        filedata = b''
                        while True:
                                d = self.socket.recv(4096)
                                if d == None:
                                        continue
                                else:
                                        if b'f_end' in d:
                                                d = d[:-5]
                                                filedata = filedata + d
                                                f = open(self.path+str(idx), 'wb')
                                                f.write(filedata)
                                                f.close()
                                                asyncio.run(self.measure.VidBufferAdd(self.clip, bitrate))
                                                break
                                        filedata = filedata + d

                self.measure.stop()

        def drawGraphs(self):
                pass

if __name__ == '__main__':
        try:
                conn = connection(HOST, PORT).connect()
        except socketError:
                print('connection failed')
                exit()
        
        path = './video'

        try:
                os.mkdir(path)
        except FileExistsError:
                pass

        p = player(conn, speedMeasurement, path, bufferAlg)
        p.preprocess()
        p.start()
        p.drawGraphs()
                        
