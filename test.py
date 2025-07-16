import imaplib
import email
from email.header import decode_header

IMAP_HOST = "172.20.210.50"
IMAP_PORT = 143

username = "user2@example.com"
password = "Huyhuhong123@"


def clean_subject(subject):
    if subject is None:
        return ""
    decoded_parts = decode_header(subject)
    decoded_subject = ""
    for part, encoding in decoded_parts:
        try:
            if isinstance(part, bytes):
                # Nếu encoding lạ hoặc None, cố decode utf-8 với ignore errors
                decoded_subject += part.decode(encoding or "utf-8", errors="ignore")
            else:
                decoded_subject += part
        except Exception:
            # Nếu decode lỗi, chuyển bytes sang string latin1 (fallback) rồi chuyển sang utf-8
            if isinstance(part, bytes):
                decoded_subject += part.decode("latin1", errors="ignore")
            else:
                decoded_subject += str(part)
    return decoded_subject


def main():
    try:
        mail = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        mail.login(username, password)
        print("✅ Login OK")

        # In ra tất cả mailbox
        status, mailboxes = mail.list()
        if status == "OK":
            print("📂 Danh sách mailbox:")
            for mbox in mailboxes:
                print(mbox.decode())
        else:
            print("❌ Không lấy được danh sách mailbox")

        # Danh sách mailbox thư đã gửi phổ biến
        sent_boxes = ["Sent", "Sent Items", "[Gmail]/Sent Mail", "INBOX.Sent"]

        mailbox_selected = None
        for box in sent_boxes:
            status, _ = mail.select(box, readonly=True)
            if status == "OK":
                mailbox_selected = box
                break

        # Nếu không tìm thấy thư mục sent, thử lấy thư trong INBOX
        if mailbox_selected is None:
            print("❌ Không tìm thấy mailbox thư đã gửi, thử lấy trong INBOX")
            status, _ = mail.select("INBOX", readonly=True)
            if status == "OK":
                mailbox_selected = "INBOX"
            else:
                print("❌ Không thể chọn mailbox INBOX, dừng chương trình")
                mail.logout()
                return

        print(f"📂 Đã chọn mailbox: {mailbox_selected}")

        status, data = mail.search(None, "ALL")
        if status != "OK":
            print("❌ Lỗi khi tìm email")
        else:
            mail_ids = data[0].split()
            print(f"🔎 Tổng số email: {len(mail_ids)}")

            # Lấy 10 email mới nhất
            last_10 = mail_ids[-10:]

            for num in last_10:
                status, msg_data = mail.fetch(num, "(RFC822)")
                if status != "OK":
                    print(f"❌ Lỗi lấy email id {num.decode()}")
                    continue
                msg = email.message_from_bytes(msg_data[0][1])

                subject = clean_subject(msg.get("Subject"))
                from_ = msg.get("From")
                to_ = msg.get("To")
                date_ = msg.get("Date")

                print("=" * 50)
                print(f"Subject: {subject}")
                print(f"From: {from_}")
                print(f"To: {to_}")
                print(f"Date: {date_}")
                print("=" * 50)

        mail.logout()
    except Exception as e:
        print("❌ Lỗi:", e)


if __name__ == "__main__":
    main()
