import os
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from subprocess import Popen


class RestartOnChangeHandler(FileSystemEventHandler):
    def __init__(self, script_path):
        self.script_path = script_path
        self.process = None
        self.restart_bot()

    def restart_bot(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
        self.process = Popen([sys.executable, self.script_path])

    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            print(f'Изменения в {event.src_path}, перезапуск...')
            self.restart_bot()

    def on_created(self, event):
        if event.src_path.endswith('.py'):
            print(f'Добавлен {event.src_path}, перезапуск...')
            self.restart_bot()

if __name__ == "__main__":
    script_path = 'app/bot.py'  # Укажите путь до файла с вашим ботом
    event_handler = RestartOnChangeHandler(script_path)
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=True)

    observer.start()
    print(f'Наблюдение за изменениями в {os.getcwd()}...')
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()
