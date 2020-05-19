#! /usr/bin/python3

import argparse
import sys
import os
import json
import math

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

if __name__ == '__main__':
        parser = argparse.ArgumentParser(description='Split video to files')
        parser.add_argument('clip_size', nargs = 1, type = int,
                        help = 'the length of clip')
        parser.add_argument('total_size', nargs = 1, type = int,
                        help = 'the length of clip')
        args = parser.parse_args()

        clip = args.clip_size[0]
        total = args.total_size[0]
        vid_table = {}

        for key in bitrate_table:
                vid_table[key] = bitrate_table[key] * clip

        path = './video'
        os.mkdir(path)
        count = math.ceil(total / clip)
        prefix = 'vid_'
        data = {}
        data['clip_length'] = clip
        data['total_length'] = total
        for key in vid_table:
                data[key] = {}
                data[key]['0'] = count
                for idx in range(1, count+1):
                        data[key][str(idx)] = prefix + key + '_' + str(idx)
                        
        conf = open(path + '/vid_conf.json', 'w')
        json.dump(data, conf)
        
        path = path + '/' + prefix
        for key in vid_table:
                for idx in range(1, count+1):
                        fp = open(path+key+'_'+str(idx), 'wb')
                        fp.write(b'\x7c'*(vid_table[key]//8))
                        fp.close()
                        print('Created file ' + str(idx) + ' of ' + key)

        
        