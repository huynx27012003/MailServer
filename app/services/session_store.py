# app/services/session_store.py
session_passwords = {}  # Dictionary để lưu mật khẩu tạm thời

# Simple in-memory store for IMAP passwords
_store = {}

def set(username: str, password: str):
    _store[username] = password

def get(username: str) -> str | None:
    return _store.get(username)

def delete(username: str):
    _store.pop(username, None)
