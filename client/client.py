#! /usr/bin/env python3

import socket
import json
import math
import os
import datetime
import sys
import signal
import asyncio
import time
import matplotlib.pyplot as plt

HOST = '192.168.2.15'    # The remote host
PORT = 51234             # The same port as used by the server

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

class algError(Exception):
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
                self.latency = 0
                self.stat = []
                self.speed = 1
                self.thp = 0
                self.fsb = 0
                self.initialspd = None
                self.bufferingTime = 0
                self.lastPausedTime = None
                self.firstPlayTimeStamp = None

        def getVidTimeStamp(self):
                return self.vidPlayCount

        def setInitialSpeed(self, spd):
                self.initialspd = spd
                self.speed = self.initialspd

        def setInitialBuffer(self, fsb):
                self.fsb = fsb

        def getFirstPlayTimeStamp(self):
                return self.firstPlayTimeStamp

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
                self.lastPausedTime = int(round(time.time()*1000))

        def vidContinue(self):
                self.vidPlay = True
                self.firstTime = False
                if self.lastPausedTime:
                        self.bufferingTime += int(round(time.time()*1000)) - self.lastPausedTime
                        self.lastPausedTime = None

        def __updateBufferSize(self):
                totalSize = 0
                for buffer in self.bufferList:
                        totalSize = totalSize + buffer['time']
                self.bufferUsage = totalSize

        def getBufferUsage(self):
                return self.bufferUsage

        def getLatency(self):
                return self.latency

        def setLatency(self, lat):
                ltc = self.latency
                try:
                        self.latency = int(lat.decode(encoding = 'utf-8'))
                except ValueError:
                        print("ignored latency")
                        self.latency = ltc
                        pass

        def addThroughput(self, thp):
                self.thp += thp

        def getSpeed(self):
                if self.initialspd and self.firstSecond:
                        return self.initialspd
                return self.speed

        def __calVidStatus(self):
                if self.vidPlay == True:
                        if len(self.bufferList) == 0:
                                print('Status : Video play buffering')
                                self.vidPause()
                        elif self.firstTime:
                                self.vidPause()
                else:
                        if len(self.bufferList) > 0 and not self.firstTime:
                                print('Status : Video play resumed')
                                self.vidContinue()
                        elif self.firstTime and self.getBufferUsage() >= self.fsb:
                                print('Status : Video play started')
                                self.firstPlayTimeStamp = int(round(time.time()*1000))
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
                self.firstSecond = False
                self.speed = self.thp
                self.thp = 0
                if self.speed == 0:
                        self.speed = 1
                self.__calVidStatus()
                if self.vidPlay:        # Current player count
                        asyncio.run(self.bufferReduce(1))

        def start(self):
                if self.vidPlay:
                        return
                signal.signal(signal.SIGALRM, self.__handler)
                signal.alarm(self.durination)
                self.firstTime = True
                self.firstSecond = True

        def stop(self):
                if not self.vidPlay:
                        return
                signal.signal(signal.SIGALRM, signal.SIG_DFL)
                signal.alarm(0)
                self.vidPlay = False
                self.size = 0

        def convertBitrateToStr(self, value):
                if self.initialspd and self.firstTime:
                        retbtr = "240p"
                        for string, bitrate in bitrate_table.items():
                                if self.initialspd*8 > int(bitrate):
                                        retbtr_2nd = retbtr
                                        retbtr = string
                        return str(retbtr)
                for string, bitrate in bitrate_table.items():
                        if value == bitrate:
                                return string
                return None

        async def VidBufferAdd(self, time, bitrate, idx):
                async with self.bufferLock:
                        self.bufferList.append({'time' : time, 'bitrate' : bitrate, 'index' : idx})
                        self.__updateBufferSize()

        def getCurrBufferIdx(self):
                if len(self.bufferList) == 0:
                        return 0
                else:
                        self.bufferList[-1]['index'] + 1

        def getStatistics(self):
                print("Buffering time", str(self.bufferingTime) + "ms")

class bufferAlg(alg):
        #       Buffer-based Alg (referred https://arxiv.org/pdf/1601.06748.pdf and http://yuba.stanford.edu/~nickm/papers/sigcomm2014-video.pdf)
        def __init__(self, measure, bitrateTable, initialBitrate = 0, buffersize = 25, reservoir = 10, upperReservoir = 5, initialBuffer = 5):
                self.buffersize = buffersize
                self.measure = measure
                self.reservoir = reservoir
                self.upperReservoir = upperReservoir
                self.bitrateTable = list(bitrateTable.values())
                self.initialBuffer = initialBuffer
                self.measure.setInitialBuffer(self.initialBuffer)

        def getIfBufferFull(self):
                if self.buffersize < self.measure.getBufferUsage():
                        return True
                else:
                        return False

        def setInitialSpeed(self, spd):
                pass

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

        def printConfiguration(self):
                print("Using Algorithm: BBA")
                print("buffersize = %d"%self.buffersize)
                print("reservoir = %d"%self.reservoir)
                print("upperReservoir = %d"%self.upperReservoir)


# BOLA is copied and modified from sabre project
class Bola:
        def __init__(self, measure, bitrateTable, buffersize = 25, segment_time = 3, gp = 5, initialBuffer = 5, initialBitrate = 0, reservoir = 5, upperReservoir = 5):
                self.measure = measure
                self.bitrateTable = [bitrate_table[x] for x in bitrate_table]
                self.segment_time = segment_time
                self.gp = gp

                utility_offset = -math.log(self.bitrateTable[0]) # so utilities[0] = 0
                self.utilities = [math.log(b) + utility_offset for b in self.bitrateTable]

                self.buffer_size = buffersize
                self.Vp = (self.buffer_size - self.segment_time) / (self.utilities[-1] + self.gp)

                self.last_seek_index = 0 # TODO
                self.last_quality = 0
                self.initialBuffer = initialBuffer
                self.measure.setInitialBuffer(self.initialBuffer)
                self.upperReservoir = upperReservoir
                self.spd = 1

        def setInitialSpeed(self, spd):
                quality = 0
                for q in range(len(self.bitrateTable)):
                        if spd*8 > self.bitrateTable[q]:
                                quality = q
                self.last_quality = quality
                self.measure.setInitialBuffer(self.buffer_size/2)

        def getIfBufferFull(self):
                if self.buffer_size + self.upperReservoir < self.measure.getBufferUsage():
                        return True
                else:
                        return False

        def quality_from_buffer(self):
                level = self.measure.getBufferUsage()
                quality = 0
                score = None
                for q in range(len(self.bitrateTable)):
                        s = ((self.Vp * (self.utilities[q] + self.gp) - level) / self.bitrateTable[q])
                        if score == None or s > score:
                                quality = q
                                score = s
                return quality

        def quality_from_throughput(self, tput):
                tput = 8*tput
                p = self.segment_time

                quality = 0
                while (quality + 1 < len(self.bitrateTable) and
                                self.measure.getLatency()/1000 + p * self.bitrateTable[quality + 1] / tput <= p):
                        quality += 1
                return quality

        def get_quality_delay(self, segment_index):
                quality = self.quality_from_buffer()
                delay = 0

                if quality > self.last_quality:
                        self.spdBackUp = self.spd
                        self.spd = self.measure.getSpeed()
                        if self.buffer_size <= self.measure.getBufferUsage():
                                self.spd = self.spdBackUp*1.1
                        quality_t = self.quality_from_throughput(self.spd)
                        if quality <= quality_t:
                                delay = 0
                        elif self.last_quality > quality_t:
                                quality = self.last_quality
                                delay = 0
                        else:
                                quality = quality_t + 1
                                delay = 0
                        print(quality, quality_t)

                self.last_quality = quality
                return (quality, delay)

        def getDesiredBitrate(self):
                print('buffer:'+str(self.measure.getBufferUsage()))
                q, _ = self.get_quality_delay(self.measure.getCurrBufferIdx())
                btr = self.bitrateTable[q]
                return btr

        def report_seek(self, where):
                # TODO: seek properly
                pass

        def printConfiguration(self):
                print("Using Algorithm: Bola-Basic")
                print("buffersize = %d"%self.buffer_size)
                print("gp = %d"%self.gp)
                print("upperReservoir = %d"%self.upperReservoir)

        def check_abandon(self, progress, buffer_level):
                if True:
                        return None

                remain = progress.size - progress.downloaded
                if progress.downloaded <= 0 or remain <= 0:
                        return None

                abandon_to = None
                score = (self.Vp * (self.gp + self.utilities[progress.quality]) - buffer_level) / remain
                if score < 0:
                        return # TODO: check

                for q in range(progress.quality):
                        other_size = progress.size * self.bitrateTable[q] / self.bitrateTable[progress.quality]
                        other_score = (self.Vp * (self.gp + self.utilities[q]) - buffer_level) / other_size
                        if other_size < remain and other_score > score:
                                # check size: see comment in BolaEnh.check_abandon()
                                score = other_score
                                abandon_to = q

                if abandon_to != None:
                        self.last_quality = abandon_to

                return abandon_to

class BolaWithFastSwitching(Bola):
        def getDesiredBitrate(self):
                print('buffer:'+str(self.measure.getBufferUsage()))
                q, _ = self.get_quality_delay(self.measure.getCurrBufferIdx())
                btr = self.bitrateTable[q]
                return btr



class player:
        def __init__(self, socket, measure, path, alg, preEvaluateSpeed = False, fastSwitching = False):
                self.socket = socket
                self.measure = measure(1)
                self.path = path + '/vid_'
                self.alg = alg(self.measure, bitrate_table, initialBitrate = 0, buffersize = 30, reservoir = 5, upperReservoir = 5)
                self.InitialSpeed = 1
                self.recClipBitrate = []
                self.preEvaluateSpeed = preEvaluateSpeed # Pre-Evaluate the network status, True to enable
                self.fastSwitching = fastSwitching

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

        def preSpeedTest(self):
                self.socket.send(b'speedteststart')
                thp = 0
                t0 = int(round(time.time() * 1000))
                while True:
                        testd = self.socket.recv(4096)
                        if testd == None:
                                continue
                        else:
                                thp += len(testd)
                                if b'end' in testd:
                                        break
                t1 = int(round(time.time() * 1000))
                dt = t1 - t0
                spd = thp / (dt/1000)
                self.InitialSpeed = spd
                idx = 0
                for _, bitrate in bitrate_table.items():
                        if spd > int(bitrate):
                                idx += 1
                self.alg.last_quality = idx

        def recordSelection(self, idx, bitrateS):
                if len(self.recClipBitrate) >= idx:
                        self.recClipBitrate[idx-1] = [bitrate_table[bitrateS], self.recClipBitrate[idx-1][1]]
                else:
                        self.recClipBitrate.append([bitrate_table[bitrateS], int(round(time.time()*1000))])

        def start(self):
                #self.config = '3Glogs/report.2010-09-28_1003CEST.json'
                self.config = '4Glogs/report_train_0001.json'
                self.socket.send(b'limitstart,' + self.config.encode(encoding='utf-8'))
                self.tStart = int(round(time.time()*1000))

                if self.preEvaluateSpeed:
                        self.preSpeedTest()
                        print("tested speed is %d"%(self.InitialSpeed//1024) + "KBps")

                self.measure.start()

                if self.preEvaluateSpeed:
                        self.alg.setInitialSpeed(self.InitialSpeed)
                        self.measure.setInitialSpeed(self.InitialSpeed)

                self.missionList = []
                for idx in range(1, self.count+1):
                        self.missionList.append(idx)
                
                while(len(self.missionList) != 0):
                        if self.fastSwitching:
                                q = self.alg.quality_from_throughput(self.measure.getSpeed())
                                btr = self.alg.bitrateTable[q]
                                if self.measure.getBufferUsage() > self.clip * 1.5 :
                                        if len(self.measure.bufferList) >= 3:
                                                if btr > self.measure.bufferList[2]['bitrate']:
                                                        missionIdx = int(self.measure.bufferList[2]['index'])
                                                        if missionIdx in self.missionList:
                                                                pass
                                                        else:
                                                                self.missionList = [missionIdx] + self.missionList
                                                else:
                                                        pass
                                        else:
                                                pass
                                else:
                                        pass


                        while(self.alg.getIfBufferFull() == True):
                                pass
                        bitrate = self.determineBitrate()
                        bitrateS = self.measure.convertBitrateToStr(bitrate)

                        idx = self.missionList[0]
                        self.recordSelection(idx, bitrateS)
                        self.socket.send(bitrateS.encode(encoding="utf-8") + b',' + str(idx).encode(encoding="utf-8"))
                        print('bitrate setting for clip ' + str(idx) + ' is ' + bitrateS)
                        filedata = b''
                        while True:
                                d = self.socket.recv(4096)
                                self.measure.addThroughput(len(d))
                                if d == None:
                                        continue
                                else:
                                        if b'f_end' in d:
                                                d = d[:-5]
                                                filedata = filedata + d
                                                # ignore disk write as it won't affect performance evaluation
                                                #f = open(self.path+str(idx), 'wb')
                                                #f.write(filedata)
                                                #f.close()
                                                asyncio.run(self.measure.VidBufferAdd(self.clip, bitrate, idx))
                                                self.missionList.remove(idx)
                                                break
                                        elif d.strip(b'\x7c'):
                                                self.measure.setLatency(d.strip(b'\x7c'))
                                        filedata = filedata + d

                self.socket.send(b'limitstop')
                self.measure.stop()
                self.socket.send(b'end')

        def drawGraphs(self):
                # Print statistics
                print("Test Report:")
                print("First Buffing Time: "+str(self.measure.getFirstPlayTimeStamp()-self.tStart)+"ms")
                self.measure.getStatistics()
                self.alg.printConfiguration()
                # Read net config
                self.filedir = '../sabre/example/tomm19/' + self.config
                f = open(self.filedir)
                self.records = json.load(f)
                f.close()
                if self.fastSwitching:
                        # when fast switching enabled, the time line becomes no longer meaningful, as same clip would load multiple times
                        dataWithoutFs = [[400000, 1589890237540], [400000, 1589890237923], [400000, 1589890238149], [400000, 1589890238358], [400000, 1589890238489], [1150000, 1589890238620], [2560000, 1589890238993], [5120000, 1589890239752], [10240000, 1589890241442], [10240000, 1589890243618], [20480000, 1589890245698], [20480000, 1589890248439], [20480000, 1589890252339], [10240000, 1589890256063], [20480000, 1589890257331], [20480000, 1589890259789], [40960000, 1589890261771], [960000, 1589890275891], [2560000, 1589890276313], [5120000, 1589890277348]]
                        x1 = []
                        x2 = []
                        for i in range(1, len(dataWithoutFs)+1):
                                x1.append(i)
                                x2.append(i)
                        y1 = [self.recClipBitrate[idx][0]/1000 for idx in range(len(self.recClipBitrate))]
                        y2 = [dataWithoutFs[idx][0]/1000 for idx in range(len(dataWithoutFs))]
                        plt.plot(x1, y1, label='with fast switching')
                        plt.plot(x2, y2, label='without fast switching')
                        plt.legend(loc=2)
                        plt.xlabel('clip index')
                        plt.ylabel('kbps')
                        plt.show()
                else:
                        x2 = [self.recClipBitrate[idx][1]-self.tStart for idx in range(len(self.recClipBitrate))]
                        y2 = [self.recClipBitrate[idx][0]/1000 for idx in range(len(self.recClipBitrate))]
                        x1 = []
                        y1 = []
                        for idx in range(len(self.records)):
                                if idx == 0:
                                        x1.append(self.records[idx]['duration_ms']/2)
                                        y1.append(self.records[idx]['bandwidth_kbps'])
                                else:
                                        if (self.records[idx-1]['duration_ms'] + self.records[idx]['duration_ms'])/2 + x1[-1] > x2[-1]:
                                                break
                                        x1.append((self.records[idx-1]['duration_ms'] + self.records[idx]['duration_ms'])/2 + x1[-1])
                                        y1.append(self.records[idx]['bandwidth_kbps'])

                        plt.plot(x1, y1, label='network bandwidth')
                        plt.plot(x2, y2, label='bitrate selection')
                        plt.legend(loc=2)
                        plt.xlabel('ms')
                        plt.ylabel('kbps')
                        plt.show()


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

        p = player(conn, speedMeasurement, path, Bola, preEvaluateSpeed = False, fastSwitching = False)
        p.preprocess()
        p.start()
        p.drawGraphs()

