from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from fastapi.responses import StreamingResponse
from email.header import decode_header
from email.utils import parsedate_to_datetime
import imaplib
import email
import base64
import io

from app.services import jwt_service
from app.services.session_store import get

IMAP_HOST = "172.20.210.50"
IMAP_PORT = 993

router = APIRouter(prefix="/sent")
security = HTTPBearer()


def get_user_password(username: str) -> str:
    password = get(username)
    if not password:
        raise HTTPException(status_code=401, detail="Missing password for user")
    return password


def decode_mime_header(value: str) -> str:
    if not value:
        return "(Không rõ)"
    try:
        parts = decode_header(value)
        decoded = ''
        for part, encoding in parts:
            if isinstance(part, bytes):
                decoded += part.decode(encoding or 'utf-8', errors='replace')
            else:
                decoded += part
        return decoded
    except Exception:
        return value


def find_sent_folder(mail) -> str:
    result, folders = mail.list()
    print("📂 Available folders:")
    for f in folders:
        print(f.decode())
        if b"Sent" in f or b"sent" in f:
            # lấy ra tên folder: phần cuối sau dấu '"/"'
            folder_name = f.decode().split(' "/" ')[-1].strip('"')
            print(f"✅ Found Sent folder: {folder_name}")
            return folder_name
    return "Sent"  # fallback


# ----- List sent mails -----
@router.get("/")
def list_sent_mails(token=Depends(security)):
    username = jwt_service.decode_token(token.credentials).strip().split("@")[0]
    password = get_user_password(username)

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(username, password)

        sent_folder = find_sent_folder(mail)
        result, _ = mail.select(sent_folder, readonly=True)
        if result != "OK":
            raise Exception(f"❌ Failed to select Sent folder: {sent_folder}")

        result, data = mail.search(None, "ALL")
        if result != "OK":
            raise Exception("❌ Failed to search Sent folder")

        uids = data[0].split()
        mails = []
        for uid in uids:
            res, msg_data = mail.fetch(uid, "(BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
            if res != "OK":
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = decode_mime_header(msg.get("Subject", "(Không rõ tiêu đề)"))
            from_ = msg.get("From", "")
            to = msg.get("To", "")
            date = msg.get("Date", "")
            try:
                parsed_date = parsedate_to_datetime(date).isoformat()
            except:
                parsed_date = date

            mails.append({
                "uid": uid.decode(),
                "from": from_,
                "to": to,
                "subject": subject,
                "date": parsed_date
            })
        mail.logout()
        return mails[::-1]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list sent mails: {e}")


# ----- Get sent mail details -----
@router.get("/{uid}")
def get_sent_mail_detail(uid: str, token=Depends(security)):
    username = jwt_service.decode_token(token.credentials).strip().split("@")[0]
    password = get_user_password(username)

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(username, password)

        sent_folder = find_sent_folder(mail)
        result, _ = mail.select(sent_folder, readonly=True)
        if result != "OK":
            raise Exception(f"❌ Failed to select Sent folder: {sent_folder}")

        res, msg_data = mail.fetch(uid.encode(), "(RFC822)")
        if res != "OK":
            raise Exception("❌ Failed to fetch mail")

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        subject = decode_mime_header(msg.get("Subject", "(Không rõ tiêu đề)"))
        from_ = msg.get("From", "")
        to = msg.get("To", "")
        date = msg.get("Date", "")
        try:
            parsed_date = parsedate_to_datetime(date).isoformat()
        except:
            parsed_date = date

        body = ""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = part.get("Content-Disposition", "")
                content_type = part.get_content_type()

                if part.get_content_maintype() == 'text' and 'attachment' not in content_disposition:
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        body = part.get_payload(decode=True).decode(charset, errors="replace")
                    except:
                        body = part.get_payload(decode=True).decode("utf-8", errors="replace")

                if "attachment" in content_disposition or part.get_filename():
                    filename = decode_mime_header(part.get_filename() or "unknown")
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments.append({
                            "filename": filename,
                            "data": base64.b64encode(payload).decode("utf-8")
                        })
        else:
            payload = msg.get_payload(decode=True)
            try:
                body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            except:
                body = payload.decode("utf-8", errors="replace")

        mail.logout()
        return {
            "uid": uid,
            "from": from_,
            "to": to,
            "subject": subject,
            "date": parsed_date,
            "body": body,
            "attachments": attachments
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get mail detail: {e}")


# ----- Download attachment from sent mail -----
@router.get("/{uid}/attachment/{filename}")
def download_sent_attachment(uid: str, filename: str, token=Depends(security)):
    mail_detail = get_sent_mail_detail(uid, token)
    for attachment in mail_detail["attachments"]:
        if attachment["filename"] == filename:
            data = base64.b64decode(attachment["data"])
            return StreamingResponse(
                io.BytesIO(data),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    raise HTTPException(status_code=404, detail="Attachment not found")
