import mysql.connector
import paramiko
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_mail_user(email, hashed_password, domain="gmail.com", ssh_host="172.20.210.50", ssh_user="huy", ssh_password=None, ssh_key_path=None, sudo_password=None):
    """
    Create a mail user by adding to virtual_users, virtual_mailboxes, and creating mailbox directory on remote server.
    
    Args:
        email (str): Email address (e.g., 'nxh27012004@gmail.com')
        hashed_password (str): Bcrypt hashed password
        domain (str): Domain name (default: 'gmail.com')
        ssh_host (str): Remote server IP (default: '172.20.210.50')
        ssh_user (str): SSH username
        ssh_password (str): SSH password (optional, use ssh_key_path instead if possible)
        ssh_key_path (str): Path to SSH private key (optional)
        sudo_password (str): Password for sudo commands (usually same as ssh_password)
    """
    try:
        # Step 1: Connect to MySQL
        conn = mysql.connector.connect(
            host="172.20.210.50",
            user="mailuser",
            password="Huyhuhong123@",
            database="mailserver"
        )
        cursor = conn.cursor()

        # Step 2: Get domain_id from virtual_domains
        cursor.execute("SELECT id FROM virtual_domains WHERE name=%s", (domain,))
        domain_result = cursor.fetchone()
        if not domain_result:
            logger.error(f"Domain '{domain}' not found in virtual_domains")
            return
        domain_id = domain_result[0]

        # Step 3: Insert into virtual_users
        cursor.execute(
            "INSERT INTO virtual_users (email, password) VALUES (%s, %s)",
            (email, hashed_password)
        )
        logger.info(f"Inserted {email} into virtual_users")

        # Step 4: Insert into virtual_mailboxes (domain-specific path)
        username = email.split('@')[0]
        mailbox_path = f"{domain}/{username}/"
        cursor.execute(
            "INSERT INTO virtual_mailboxes (domain_id, email, mailbox_path) VALUES (%s, %s, %s)",
            (domain_id, email, mailbox_path)
        )
        logger.info(f"Inserted {email} into virtual_mailboxes with path {mailbox_path}")

        # Commit database changes
        conn.commit()

    except mysql.connector.Error as e:
        logger.error(f"Database error: {e}")
        conn.rollback()
        return
    finally:
        cursor.close()
        conn.close()

    # Step 5: Create mailbox directory on remote server via SSH
    mailbox_dir = f"/var/mail/vhosts/{domain}/{username}/Maildir"
    try:
        # Initialize SSH client
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Connect using password or key
        if ssh_key_path:
            ssh.connect(ssh_host, username=ssh_user, key_filename=ssh_key_path)
        else:
            ssh.connect(ssh_host, username=ssh_user, password=ssh_password)

        # Use sudo password (default to ssh_password if not provided)
        if sudo_password is None:
            sudo_password = ssh_password

        # Execute commands with sudo -S (read password from stdin)
        commands = [
            f"mkdir -p {mailbox_dir}/{{cur,new,tmp}}",
            f"chown -R vmail:vmail {mailbox_dir}",
            f"chmod -R 700 {mailbox_dir}",
            f"ls -ld {mailbox_dir}/cur {mailbox_dir}/new {mailbox_dir}/tmp"
        ]

        for cmd in commands:
            # Use echo to pipe password to sudo -S
            full_cmd = f"echo '{sudo_password}' | sudo -S {cmd}"
            stdin, stdout, stderr = ssh.exec_command(full_cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            if exit_status != 0:
                logger.error(f"Command '{cmd}' failed: {error}")
                ssh.close()
                return
            logger.info(f"Command '{cmd}' output: {output}")

        ssh.close()
        logger.info(f"Created mailbox directory {mailbox_dir} with correct permissions")

    except paramiko.SSHException as e:
        logger.error(f"SSH error: {e}")
        return

    logger.info(f"✅ User {email} added successfully.")

if __name__ == "__main__":
    # Example usage
    email = "nxh27012005@gmail.com"
    hashed_pw = "$2b$12$fYqD9naIj/jOTAPyIjFrR.K78p5TTRWccx4MZFRM.gqZTe7/iGA.."
    create_mail_user(
        email=email,
        hashed_password=hashed_pw,
        ssh_user="huy",
        ssh_password="1",
        sudo_password="1"  # Usually same as ssh_password
    )
