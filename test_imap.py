import mysql.connector
import subprocess
import os
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_mail_user(email, hashed_password, domain="gmail.com"):
    """
    Create a mail user by adding to virtual_users, virtual_mailboxes, and creating mailbox directory.
    
    Args:
        email (str): Email address (e.g., 'nxh27012003@gmail.com')
        hashed_password (str): Bcrypt hashed password
        domain (str): Domain name (default: 'gmail.com')
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

    # Step 5: Create mailbox directory
    mailbox_dir = f"/var/mail/vhosts/{domain}/{username}/Maildir"
    try:
        # Create Maildir structure
        subprocess.run(["sudo", "mkdir", "-p", f"{mailbox_dir}/{{cur,new,tmp}}"], check=True)
        # Set ownership to vmail:vmail (UID/GID 5000)
        subprocess.run(["sudo", "chown", "-R", "vmail:vmail", mailbox_dir], check=True)
        # Set permissions to 700
        subprocess.run(["sudo", "chmod", "-R", "700", mailbox_dir], check=True)
        logger.info(f"Created mailbox directory {mailbox_dir} with correct permissions")

        # Verify directory
        result = subprocess.run(["ls", "-ld", f"{mailbox_dir}/cur", f"{mailbox_dir}/new", f"{mailbox_dir}/tmp"], 
                               capture_output=True, text=True)
        logger.info(f"Directory check: {result.stdout}")

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create mailbox directory: {e}")
        return

    logger.info(f"✅ User {email} added successfully.")

if __name__ == "__main__":
    # Example usage
    email = "nxh27012004@gmail.com"
    hashed_pw = "$2b$12$fYqD9naIj/jOTAPyIjFrR.K78p5TTRWccx4MZFRM.gqZTe7/iGA.."
    create_mail_user(email, hashed_pw)