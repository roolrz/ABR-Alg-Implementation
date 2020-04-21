#! /usr/bin/env python3

import socket
import json
import math
import os

HOST = '127.0.0.1'    # The remote host
PORT = 51234              # The same port as used by the server
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    s.send(b'head')
    data = s.recv(1024)
    data = data.decode(encoding="utf-8")
    f_json = json.loads(data)
    total = f_json['total']
    clip = f_json['clip']
    count = math.ceil(total/clip)
    path = './video'
    try:
        os.mkdir(path)
    except FileExistsError:
        pass
    prefix = 'vid_'
    path = path + '/' + prefix
    for idx in range(1, count+1):
        f = open(path+str(idx), 'wb')
        s.send(b'1080p,' + str(idx).encode(encoding="utf-8"))
        while True:
            d = s.recv(1024)
            if d == None:
                continue
            else:
                if b'f_end' in d:
                    d = d[:-5]
                    if d != None:
                        f.write(d)
                    f.close()
                    print('received file ' + str(idx))
                    break
                f.write(d)
            