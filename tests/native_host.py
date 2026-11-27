"""Run the existing agent tests inside our DLL's actual embedded runtime.

Only the transport changes: JSON-lines to a native disposable process, with no
Frida service/injection. The JS fixtures and all assertions remain unchanged.
"""
import json
from pathlib import Path
import queue
import re
import subprocess
import threading
import frida

ROOT = Path(__file__).resolve().parents[1]


class NativeDevice:
    def __init__(self, executable=None):
        self.process = None
        self.next_id = 0
        self.executable = executable or ROOT / 'build/native/native-harness.exe'

    def spawn(self, _):
        self.process = subprocess.Popen([self.executable],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', bufsize=1)
        self.lines = queue.Queue()
        self.errors = []
        def read():
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put(None)
        def errors():
            for line in self.process.stderr:
                self.errors.append(line)
        threading.Thread(target=read, daemon=True).start()
        threading.Thread(target=errors, daemon=True).start()
        return self.process.pid

    def request(self, op, id, **args):
        self.process.stdin.write(json.dumps(dict(op=op, id=id, **args)) + '\n')
        self.process.stdin.flush()
        line = self.lines.get(timeout=15)
        if line is None:
            raise RuntimeError('Native host exited: ' + ''.join(self.errors))
        response = json.loads(line)
        if not response['ok']:
            raise frida.RPCException(str(response['result']))
        return response['result']

    def attach(self, pid):
        assert pid == self.process.pid
        return self

    def resume(self, pid):
        pass

    def create_script(self, source):
        id = self.next_id
        self.next_id += 1
        self.request('create', id, source=source)
        return NativeScript(self, id)

    def detach(self):
        pass

    def kill(self, pid):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
                raise AssertionError('Native host did not exit cleanly')
        assert self.process.returncode == 0, self.process.returncode
        assert not self.errors, self.errors
        self.process.stdout.close()
        self.process.stderr.close()


class NativeScript:
    def __init__(self, host, id):
        self.host, self.id = host, id
        self.exports_sync = self

    def load(self):
        self.host.request('load', self.id)

    def unload(self):
        self.host.request('unload', self.id)

    def on(self, event, callback):
        # Unexpected errors are collected by the host and checked on exit.
        assert event == 'message'

    def __getattr__(self, name):
        method = re.sub(r'_([a-z])', lambda m: m[1].upper(), name)
        return lambda *args: self.host.request('call', self.id, method=method, args=args)
