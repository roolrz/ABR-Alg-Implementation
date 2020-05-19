## ABR Alg Implementation and Evaluation

Final Project for CSE570@Stony Brook U

## Usage
1. Put the whole project into 2 different devices. Linux environment is required in serverside as it have use signal.setitimer() function and tc command, which seems to be unsupported on other platform. Client side can use both macOS or Linux, but not Windows (signal.SIGALRM used).
2. Modify the client/client.py file HOST constant in line 14, replace with the actual server IP address.
3. Start server by run "./start_server.sh" in the first time. After the video generated, you can only run "python3 server.py" to start it.
4. After server started, run "./client.py" to start evaluation.

# some configurations in client.py
1. In line 587,
'preEvaluateSpeed' refers to the "Test the network first" approach in the report. Should be set to True when using it.
2. In line 587,
'fastSwitching' refers to the "Fast switching" approach in the report. Should be set to True when using it.
3. In line 587,
'Bola' refers to the currently using algorithm, replace it with 'bufferAlg' when using BBA.
4. In line 402,
You can change some basic settings for current algorithm.