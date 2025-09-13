import multiprocessing

import subprocess

# قائمة البوتات

bots = ["logger_v1.py"] 

# دالة لتشغيل بوت معين

def run_bot(bot_file):

    subprocess.run(["python", bot_file])

if __name__ == "__main__":

    processes = []

    

    for bot in bots:

        p = multiprocessing.Process(target=run_bot, args=(bot,))

        p.start()

        processes.append(p)

    

    # انتظار انتهاء العمليات (لمنع إغلاق البرنامج)

    for p in processes:

        p.join()

