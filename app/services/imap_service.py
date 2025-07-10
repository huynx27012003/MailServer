import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import base64

IMAP_HOST = "172.20.210.50"
IMAP_PORT = 993

def login_imap(username: str, password: str) -> bool:
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(username, password)
        mail.logout()
        print(f"[LOGIN_IMAP] Trying login with: '{username}' / '{password}'")
        return True
    except Exception as e:
        print(f"[LOGIN_IMAP] Login failed for {username}: {e}")
        return False

def fetch_mails(username: str, password: str) -> list:
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(username, password)
        mail.select("INBOX", readonly=True)
        _, msgnums = mail.search(None, "ALL")
        mails = []
        for num in msgnums[0].split():
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            subject = "(Không rõ tiêu đề)"
            try:
                decoded_subject = decode_header(msg["Subject"] or "")[0]
                subject_bytes, encoding = decoded_subject
                if isinstance(subject_bytes, bytes):
                    subject = subject_bytes.decode(encoding or "utf-8", errors="replace")
                else:
                    subject = subject_bytes or ""
            except Exception as e:
                print(f"⚠️ Failed to decode subject for UID {num.decode()}: {e}")
            mails.append({
                "uid": num.decode(),
                "from": msg.get("From", ""),
                "subject": subject,
                "date": msg.get("Date", "")
            })
        mail.logout()
        return mails
    except Exception as e:
        print(f"❌ Fetch mails error: {e}")
        return []

def fetch_mail_detail(username: str, password: str, uid: str) -> dict:
    """
    Fetch detailed email content by UID, handling decoding errors and attachments.
    
    Args:
        username (str): Email account username.
        password (str): Email account password.
        uid (str): Email UID.
    
    Returns:
        dict: Email details with UID, from, subject, date, body, and attachments.
    """
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(username, password)
        mail.select("INBOX", readonly=True)

        res, msg_data = mail.fetch(uid.encode(), "(RFC822)")
        if res != "OK":
            raise Exception(f"❌ Failed to fetch email UID {uid}")

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        print(f"📧 Processing email UID {uid}, Content-Type={msg.get_content_type()}")

        # Decode subject with fallback
        subject = "(Không rõ tiêu đề)"
        try:
            decoded_subject = decode_header(msg["Subject"] or "")[0]
            subject_bytes, encoding = decoded_subject
            if isinstance(subject_bytes, bytes):
                try:
                    subject = subject_bytes.decode(encoding or "utf-8", errors="replace")
                except (LookupError, UnicodeDecodeError):
                    subject = subject_bytes.decode("latin-1", errors="replace")
            else:
                subject = subject_bytes or ""
        except Exception as e:
            print(f"⚠️ Failed to decode subject for UID {uid}: {e}")

        from_ = msg.get("From", "")
        date = msg.get("Date", "")
        try:
            parsed_date = parsedate_to_datetime(date).isoformat()
        except:
            parsed_date = date

        body = ""
        attachments = []
        body_found = False

        if msg.is_multipart():
            print(f"📧 UID {uid} is multipart, walking through {len(list(msg.walk()))} parts")
            for part in msg.walk():
                content_disposition = part.get("Content-Disposition", "").lower()
                content_type = part.get_content_type()
                print(f"📄 Part: Content-Type={content_type}, Content-Disposition={content_disposition}, Filename={part.get_filename()}")

                # Body text
                if content_type in ["text/plain", "text/html"] and "attachment" not in content_disposition:
                    if not body_found or content_type == "text/plain":
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                charset = part.get_content_charset() or "utf-8"
                                try:
                                    body = payload.decode(charset, errors="replace")
                                except (LookupError, UnicodeDecodeError):
                                    body = payload.decode("latin-1", errors="replace")
                                print(f"📝 Found body ({content_type}) for UID {uid}: {body[:50]}...")
                                if content_type == "text/plain":
                                    body_found = True
                        except Exception as e:
                            print(f"⚠️ Failed to decode body part for UID {uid}: {e}")

                # Attachments
                if (
                    "attachment" in content_disposition
                    or part.get_filename()
                    or content_type.startswith(("application/", "image/"))
                ):
                    filename = part.get_filename()
                    if not filename:
                        if content_type.startswith("application/"):
                            filename = f"attachment_{len(attachments) + 1}.{content_type.split('/')[-1] or 'bin'}"
                        else:
                            continue
                    try:
                        decoded_filename, enc = decode_header(filename)[0]
                        if isinstance(decoded_filename, bytes):
                            filename = decoded_filename.decode(enc or "utf-8", errors="replace")
                    except Exception as e:
                        print(f"⚠️ Failed to decode filename for UID {uid}: {e}")
                        filename = f"attachment_{len(attachments) + 1}"

                    payload = part.get_payload(decode=True)
                    if payload:
                        try:
                            b64_data = base64.b64encode(payload).decode("utf-8")
                            attachments.append({
                                "filename": filename,
                                "data": b64_data
                            })
                            print(f"📎 Found attachment for UID {uid}: {filename}")
                        except Exception as e:
                            print(f"⚠️ Failed to encode attachment {filename} for UID {uid}: {e}")
                    else:
                        print(f"⚠️ No payload for attachment {filename} in UID {uid}")

        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    try:
                        body = payload.decode(charset, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        body = payload.decode("latin-1", errors="replace")
                print(f"📝 Found body (non-multipart) for UID {uid}: {body[:50]}...")
            except Exception as e:
                print(f"⚠️ Failed to decode body for UID {uid}: {e}")

        mail.logout()
        print(f"📬 Returning mail detail for UID {uid}: attachments={len(attachments)}")
        return {
            "uid": uid,
            "from": from_,
            "subject": subject,
            "date": parsed_date,
            "body": body,
            "attachments": attachments
        }

    except Exception as e:
        print(f"❌ Fetch mail detail error for UID {uid}: {e}")
        return {
            "uid": uid,
            "from": "",
            "subject": "(Không rõ tiêu đề)",
            "date": "",
            "body": "",
            "attachments": []
        }