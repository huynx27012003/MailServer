import imaplib
import threading
import time
import asyncio
from app.services.websocket_service import websocket_manager

IMAP_HOST = "172.20.210.50"
IMAP_PORT = 143

class ImapIdleListener(threading.Thread):
    def __init__(self, username: str, password: str):
        super().__init__(daemon=True)
        self.username = username
        self.password = password
        self.mail = None
        self.running = True

    def run(self):
        while self.running:
            try:
                self.mail = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
                self.mail.login(self.username, self.password)
                self.mail.select("INBOX", readonly=True)
                print(f"[IMAP IDLE] Started IDLE for {self.username}")

                while self.running:
                    tag = self.mail._new_tag()
                    self.mail.send(f"{tag} IDLE\r\n".encode())
                    resp = self.mail.readline()
                    if resp != b'+ idling\r\n':
                        print(f"[IMAP IDLE] Unexpected response: {resp}")
                        break

                    ready = self.mail.sock.recv(1024)
                    if b'EXISTS' in ready:
                        print(f"[IMAP IDLE] New mail detected for {self.username}")
                        # Notify websocket clients asynchronously
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(websocket_manager.notify_new_email(self.username))
                        loop.close()

                        self.mail.send(b'DONE\r\n')
                        self.mail.readline()
                    time.sleep(1)

                self.mail.logout()
            except Exception as e:
                print(f"[IMAP IDLE] Error for {self.username}: {e}")
                time.sleep(10)

    def stop(self):
        self.running = False
        if self.mail:
            try:
                self.mail.send(b'DONE\r\n')
                self.mail.logout()
            except:
                pass

imap_listeners = {}

def start_idle_for_user(username: str, password: str):
    if username in imap_listeners:
        return
    listener = ImapIdleListener(username, password)
    imap_listeners[username] = listener
    listener.start()

def stop_idle_for_user(username: str):
    listener = imap_listeners.get(username)
    if listener:
        listener.stop()
        del imap_listeners[username]