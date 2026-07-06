# app/services/email_scrapers/email_scraper.py
import imaplib
import email
import logging
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime
from typing import List

from app.core.config import settings
from app.schemas.email_schema import ScrapedEmail

# Configure logger
logger = logging.getLogger(__name__)

class GmailScraper:
    def __init__(self):
        self.username = settings.GMAIL_USERNAME
        self.app_password = settings.GMAIL_APP_PASSWORD
        self.imap_server = settings.IMAP_SERVER
        
        # Target folders (Quotes handle spaces in folder names)
        self.rejected_folder_name = '"Rejected Jobs"' 
        self.applied_folder_name = '"Applied Jobs"'
        
        # Folders to explicitly skip during fetching
        self.excluded_folders = [
            "[Gmail]/Trash", 
            "[Gmail]/Bin", 
            "[Gmail]/Spam", 
            "[Gmail]/Drafts", # Added to exclusions
        ]

    def _connect(self) -> imaplib.IMAP4_SSL:
        """Establishes and returns an IMAP connection."""
        mail = imaplib.IMAP4_SSL(self.imap_server)
        mail.login(self.username, self.app_password)
        return mail

    def fetch_emails_since(self, last_scrape_time: datetime) -> List[ScrapedEmail]:
        """
        Fetches all emails from all valid folders since the given datetime.
        Returns a list of validated ScrapedEmail Pydantic models.
        """
        scraped_emails = []
        mail = None

        try:
            mail = self._connect()
            
            status, folder_list_bytes = mail.list()
            if status != "OK":
                logger.error("Failed to retrieve folder list from Gmail.")
                return scraped_emails

            imap_date_str = last_scrape_time.strftime("%d-%b-%Y")
            search_criteria = f'(SINCE "{imap_date_str}")'

            for folder_data in folder_list_bytes:
                folder_string = folder_data.decode('utf-8')
                parts = folder_string.split(' "/" ')
                
                if len(parts) < 2:
                    continue
                    
                folder_name = parts[-1].strip('"')

                if folder_name in self.excluded_folders:
                    continue

                try:
                    mail.select(f'"{folder_name}"', readonly=True)
                except imaplib.IMAP4.error as e:
                    logger.warning(f"Skipping folder '{folder_name}' (Cannot select): {e}")
                    continue

                status, messages = mail.uid('SEARCH', None, search_criteria)
                
                if status != "OK" or not messages[0]:
                    continue

                uids = messages[0].split()
                logger.info(f"Found {len(uids)} potential emails in '{folder_name}'.")

                for uid in uids:
                    status, msg_data = mail.uid('FETCH', uid, "(RFC822)")
                    
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            email_date_str = msg.get("Date")
                            if not email_date_str:
                                continue
                                
                            email_datetime = parsedate_to_datetime(email_date_str)
                            
                            if last_scrape_time.tzinfo is None and email_datetime.tzinfo is not None:
                                email_datetime = email_datetime.replace(tzinfo=None)
                            
                            if email_datetime <= last_scrape_time:
                                continue

                            sender_email = parseaddr(msg.get("From", ""))[1]
                            subject = self._decode_header_string(msg.get("Subject", "No Subject"))
                            body = self._get_text_body(msg)

                            email_model = ScrapedEmail(
                                email_id=uid.decode('utf-8'),
                                folder=folder_name,
                                sender_email=sender_email,
                                subject=subject,
                                time=email_datetime,
                                body=body
                            )
                            scraped_emails.append(email_model)

            logger.info(f"Successfully fetched a total of {len(scraped_emails)} new emails across all folders.")
            return scraped_emails

        except Exception as e:
            logger.error(f"Failed to fetch emails: {e}", exc_info=True)
            return []
            
        finally:
            if mail:
                try:
                    mail.close()
                    mail.logout()
                except Exception:
                    pass

    def move_emails_to_folder(self, emails_to_move: List[ScrapedEmail], target_folder: str):
        """
        Takes a list of ScrapedEmail objects and moves them to the specified target folder.
        It groups them by source folder to minimize IMAP select calls.
        """
        if not emails_to_move:
            logger.info(f"No emails provided to move to {target_folder}.")
            return

        folder_groups = {}
        for em in emails_to_move:
            if em.folder not in folder_groups:
                folder_groups[em.folder] = []
            folder_groups[em.folder].append(em.email_id)

        mail = None
        try:
            mail = self._connect()
            total_moved = 0

            for source_folder, uids in folder_groups.items():
                try:
                    mail.select(f'"{source_folder}"')
                    folder_moved_count = 0
                    
                    for uid_str in uids:
                        uid_bytes = uid_str.encode('utf-8')
                        
                        copy_status, _ = mail.uid('COPY', uid_bytes, target_folder)
                        
                        if copy_status == 'OK':
                            mail.uid('STORE', uid_bytes, '+FLAGS', '\\Deleted')
                            folder_moved_count += 1
                        else:
                            logger.warning(f"Failed to copy email UID {uid_str} from {source_folder} to {target_folder}.")

                    if folder_moved_count > 0:
                        mail.expunge()
                        total_moved += folder_moved_count
                        
                except imaplib.IMAP4.error as e:
                    logger.error(f"Failed processing folder '{source_folder}' during move: {e}")
                    continue

            logger.info(f"Successfully moved {total_moved}/{len(emails_to_move)} emails to {target_folder}.")

        except Exception as e:
            logger.error(f"Failed to move emails: {e}", exc_info=True)
            
        finally:
            if mail:
                try:
                    mail.close()
                    mail.logout()
                except Exception:
                    pass

    # --- Private Helper Methods ---

    def _decode_header_string(self, header_value: str) -> str:
        if not header_value:
            return ""
            
        decoded_string = ""
        decoded_parts = decode_header(header_value)
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                decoded_string += part.decode(encoding or "utf-8", errors="ignore")
            else:
                decoded_string += part
                
        return decoded_string.strip()

    def _get_text_body(self, msg) -> str:
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode(charset, errors='ignore')
        else:
            content_type = msg.get_content_type()
            if content_type == "text/plain" or content_type == "text/html":
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(charset, errors='ignore')
                    
        return body.strip()