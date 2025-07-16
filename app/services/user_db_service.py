import mysql.connector
import bcrypt
import paramiko
import logging

# --- Cấu hình cơ sở dữ liệu ---
DB_CONFIG = {
    'host': '172.20.210.50',
    'user': 'mailuser',
    'password': 'Huyhuhong123@',
    'database': 'mailserver'
}

# --- Cấu hình logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_user_password_hash(email: str) -> str | None:
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM virtual_users WHERE email = %s", (email,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        print(f"[DB] Fetched password hash for {email}: {'Found' if row else 'Not found'}")
        return row[0] if row else None
    except Exception as e:
        print(f"[DB] Error fetching password hash for {email}: {e}")
        return None


def verify_user_credentials(email: str, plain_password: str) -> bool:
    hash = get_user_password_hash(email)
    if not hash:
        print(f"[DB] No password hash found for {email}")
        return False
    try:
        result = bcrypt.checkpw(plain_password.encode(), hash.encode())
        print(f"[BCRYPT] Password verification for {email}: {'Success' if result else 'Failed'}")
        return result
    except Exception as e:
        print(f"[BCRYPT] Error verifying password for {email}: {e}")
        return False


def create_user_if_not_exists(
    email: str,
    plain_password: str,
    domain="gmail.com",
    ssh_host="172.20.210.50",
    ssh_user="huy",
    ssh_password=None,
    ssh_key_path=None,
    sudo_password=None
) -> bool:
    try:
        # Check if user already exists
        existing_hash = get_user_password_hash(email)
        if existing_hash:
            print(f"[DB] User {email} already exists")
            return False

        # Connect to DB
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get domain_id
        cursor.execute("SELECT id FROM virtual_domains WHERE name=%s", (domain,))
        domain_result = cursor.fetchone()
        if not domain_result:
            print(f"[DB] Domain '{domain}' not found in virtual_domains")
            return False
        domain_id = domain_result[0]

        # Hash password
        hashed_pw = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()

        # Insert into virtual_users
        cursor.execute("INSERT INTO virtual_users (email, password) VALUES (%s, %s)", (email, hashed_pw))
        print(f"[DB] Inserted {email} into virtual_users")

        # Insert into virtual_mailboxes
        username = email.split('@')[0]
        mailbox_path = f"{domain}/{username}/"
        cursor.execute(
            "INSERT INTO virtual_mailboxes (domain_id, email, mailbox_path) VALUES (%s, %s, %s)",
            (domain_id, email, mailbox_path)
        )
        print(f"[DB] Inserted {email} into virtual_mailboxes with path {mailbox_path}")

        # Commit changes
        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"[DB] Error creating user {email}: {e}")
        return False

    # Tạo thư mục mailbox qua SSH
    mailbox_dir = f"/var/mail/vhosts/{domain}/{username}/Maildir"
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if ssh_key_path:
            ssh.connect(ssh_host, username=ssh_user, key_filename=ssh_key_path)
        else:
            ssh.connect(ssh_host, username=ssh_user, password=ssh_password)

        if sudo_password is None:
            sudo_password = ssh_password

        commands = [
            f"mkdir -p {mailbox_dir}/{{cur,new,tmp}}",
            f"chown -R vmail:vmail {mailbox_dir}",
            f"chmod -R 700 {mailbox_dir}",
            f"ls -ld {mailbox_dir}/cur {mailbox_dir}/new {mailbox_dir}/tmp"
        ]

        for cmd in commands:
            full_cmd = f"echo '{sudo_password}' | sudo -S {cmd}"
            stdin, stdout, stderr = ssh.exec_command(full_cmd)
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                error = stderr.read().decode()
                print(f"[SSH] Command failed: {cmd} - {error}")
                ssh.close()
                return False

            output = stdout.read().decode()
            print(f"[SSH] {cmd} => {output.strip()}")

        ssh.close()
        print(f"[SSH] Mailbox directory created for {email}")
        return True

    except paramiko.SSHException as e:
        print(f"[SSH] SSH error: {e}")
        return False


def get_user_by_username(email: str) -> dict | None:
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT email, password FROM virtual_users WHERE email = %s", (email,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        result = {"email": row[0], "password": row[1]} if row else None
        print(f"[DB] Fetched user {email}: {'Found' if result else 'Not found'}")
        return result
    except Exception as e:
        print(f"[DB] Error fetching user {email}: {e}")
        return None
