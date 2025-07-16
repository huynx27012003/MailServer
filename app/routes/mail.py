import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime, formatdate
import subprocess
import base64
import io
import logging
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from fastapi.security import HTTPBearer
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText

from app.services import jwt_service
from app.services.session_store import get, set as store_password
from app.services.websocket_service import websocket_manager

IMAP_HOST = "172.20.210.50"
IMAP_PORT = 143

router = APIRouter(prefix="/mails")
security = HTTPBearer()

def login_imap(email_user: str, password: str) -> bool:
    try:
        print(f"[LOGIN_IMAP] Trying login with: {repr(email_user)} / {repr(password)}")
        username = email_user
        mail = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        mail.login(username, password)
        mail.logout()
        return True
    except Exception as e:
        print(f"❌ IMAP login error: {e}")
        return False
def fetch_mails(username: str, password: str) -> list:
    try:
        mail = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        mail.login(username, password)
        mail.select("INBOX", readonly=True)
        result, data = mail.search(None, "ALL")
        if result != "OK":
            raise Exception("❌ Failed to search inbox")
        uids = data[0].split()
        mails = []
        for uid in uids:
            res, msg_data = mail.fetch(uid, "(BODY[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if res != "OK":
                print(f"⚠️ Failed to fetch email UID {uid.decode()}")
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
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
                print(f"⚠️ Failed to decode subject for UID {uid.decode()}: {e}")
            from_ = msg.get("From", "")
            date = msg.get("Date", "")
            try:
                parsed_date = parsedate_to_datetime(date).isoformat()
            except:
                parsed_date = date
            mails.append({
                "uid": uid.decode(),
                "from": from_,
                "subject": subject,
                "date": parsed_date,
                "body": ""
            })
        mail.logout()
        return mails[::-1]
    except Exception as e:
        print(f"❌ Fetch mails error: {e}")
        raise

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
        mail = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
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


def get_user_password(username: str) -> str:
    password = get(username)
    if not password:
        default_passwords = ["Huyhuhong123@"]
        for default_pass in default_passwords:
            if login_imap(username, default_pass):
                password = default_pass
                store_password(username, password)
                print(f"✅ Using default password '{password}' for user {username}")
                break
        if not password:
            raise Exception("❌ No IMAP password stored and default passwords failed")
    return password

# ----- List all mails -----
@router.get("/")
def list_mails(token=Depends(security)):
    username = jwt_service.decode_token(token.credentials).strip()
    if '@' in username:
        username = username
    password = get_user_password(username)
    return fetch_mails(username, password)

# ----- Search mails by keyword in subject or body -----
@router.get("/search")
def search_mails(keyword: str, token=Depends(security)):
    username = jwt_service.decode_token(token.credentials).strip()
    if '@' in username:
        username = username
    password = get_user_password(username)
    try:
        print(f"🔍 [API] Searching mails for {username} with keyword: {keyword}")
        mails = fetch_mails(username, password)
        keyword = keyword.lower()
        filtered_mails = []
        for mail in mails:
            if keyword in mail["subject"].lower():
                mail_detail = fetch_mail_detail(username, password, mail["uid"])
                filtered_mails.append({
                    "uid": mail["uid"],
                    "from": mail["from"],
                    "subject": mail["subject"],
                    "date": mail["date"],
                    "body": mail_detail["body"]
                })
            else:
                mail_detail = fetch_mail_detail(username, password, mail["uid"])
                if keyword in mail_detail["body"].lower():
                    filtered_mails.append({
                        "uid": mail["uid"],
                        "from": mail["from"],
                        "subject": mail["subject"],
                        "date": mail["date"],
                        "body": mail_detail["body"]
                    })
        print(f"📬 [API] Found {len(filtered_mails)} mails matching keyword: {keyword}")
        return filtered_mails
    except Exception as e:
        print(f"❌ [API] Error searching mails: {e}")
        raise HTTPException(status_code=500, detail=f"Error searching mails: {str(e)}")

# ----- Get mail details -----
@router.get("/{uid}")
def get_mail_detail(uid: str, token=Depends(security)):
    username = jwt_service.decode_token(token.credentials).strip()
    if '@' in username:
        username = username
    password = get_user_password(username)
    try:
        print(f"📨 [API] Get mail detail for {username}, UID={uid}")
        result = fetch_mail_detail(username, password, uid)
        print(f"📬 [API] Mail detail result: {result}")
        return result
    except Exception as e:
        print(f"❌ [API] Error fetching mail details: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching mail details: {str(e)}")

# ----- Download attachment -----
@router.get("/{uid}/attachment/{filename}")
def download_attachment(uid: str, filename: str, token=Depends(security)):
    username = jwt_service.decode_token(token.credentials).strip()
    if '@' in username:
        username = username
    password = get_user_password(username)
    try:
        mail_detail = fetch_mail_detail(username, password, uid)
        attachment_data = None
        for attachment in mail_detail.get('attachments', []):
            if attachment['filename'] == filename:
                attachment_data = attachment['data']
                break
        if not attachment_data:
            raise Exception("❌ Attachment not found")
        file_data = base64.b64decode(attachment_data)
        return StreamingResponse(
            io.BytesIO(file_data),
            media_type='application/octet-stream',
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        print(f"❌ [API] Error downloading attachment: {e}")
        raise HTTPException(status_code=500, detail=f"Error downloading attachment: {str(e)}")

# ----- Send mail -----
class SendMailRequest(BaseModel):
    to: str
    subject: str
    body: str

@router.post("/send-mail")
async def send_mail(
    to: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    token=Depends(security)
):
    try:
        username = jwt_service.decode_token(token.credentials).strip()
        if '@' in username:
            username = username
        from_addr = f"{username}@localhost"
        to_clean = to.strip()
        if not to_clean or to_clean.lower() == "undefined":
            raise HTTPException(status_code=400, detail="Invalid recipient address")
        to_addr = to_clean if "@" in to_clean else f"{to_clean}@localhost"
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Date"] = formatdate(localtime=True)
        msg.attach(MIMEText(body, 'plain'))
        for file in files:
            if file.filename:
                file_content = await file.read()
                attachment = MIMEApplication(file_content)
                attachment.add_header('Content-Disposition', 'attachment', filename=file.filename)
                msg.attach(attachment)
                print(f"📎 Attached file: {file.filename}")
        server = smtplib.SMTP("172.20.210.50", 25)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
        password = get_user_password(username)
        save_to_sent_folder(username, password, msg)

        

        # Notify recipient about new email realtime
        recipient = to_clean.split("@")[0]
        await websocket_manager.notify_new_email(recipient)

        attachment_info = f" with {len(files)} attachments" if files else ""
        return {"message": f"✅ Email sent successfully{attachment_info}"}
    except Exception as e:
        logging.error("❌ Failed to send email", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
def save_to_sent_folder(username: str, password: str, msg):
    try:
        with imaplib.IMAP4(IMAP_HOST, IMAP_PORT) as imap:
            imap.login(username, password)
            imap.append("Sent", '', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            imap.logout()
            print("✅ Đã lưu email vào thư mục Sent")
    except Exception as e:
        print(f"❌ Không thể lưu vào Sent: {e}")

# ----- Send mail (simple, backward compatibility) -----
@router.post("/send-mail-simple")
async def send_mail_simple(data: SendMailRequest, token=Depends(security)):
    try:
        username = jwt_service.decode_token(token.credentials).strip()
        if '@' in username:
            username = username
        from_addr = f"{username}@localhost"
        to_clean = data.to.strip()
        if not to_clean or to_clean.lower() == "undefined":
            raise HTTPException(status_code=400, detail="Invalid recipient address")
        to_addr = to_clean if "@" in to_clean else f"{to_clean}@localhost"
        msg = MIMEText(data.body)
        msg["Subject"] = data.subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Date"] = formatdate(localtime=True)
        server = smtplib.SMTP("172.20.210.50", 25)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
        
        # After sending mail successfully:
        recipient = to_clean.split("@")[0]  # Fix here: use to_clean instead of to
        await websocket_manager.notify_new_email(recipient)
        
        return {"message": "✅ Email sent successfully"}
    except Exception as e:
        logging.error("❌ Failed to send email", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")