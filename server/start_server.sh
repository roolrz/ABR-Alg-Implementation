#! /bin/bash
rm -rf ./video
echo 'Generating files'
python3 vid_generater.py 3 60
echo 'Starting server'
python3 server.py
