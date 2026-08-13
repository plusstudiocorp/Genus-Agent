import base64
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# This tool is still a prototype
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

#==================
# User Functions
#==================

def get_service():
    """Authenticates the user and returns the Gmail API service object."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def list_recent_emails(service, max_results=10, query=""):
    """Lists recent emails matching an optional Gmail search query."""
    result = service.users().messages().list(userId="me", maxResults=max_results, q=query).execute()
    messages = result.get("messages", [])
    
    email_list = []
    for msg in messages:
        # Fetch high-level details for summary
        msg_data = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata", metadataHeaders=["Subject", "From", "Date"]
        ).execute()
        
        headers = msg_data.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
        date = next((h["value"] for h in headers if h["name"].lower() == "date"), "Unknown Date")
        
        email_list.append({
            "id": msg["id"],
            "threadId": msg["threadId"],
            "subject": subject,
            "from": sender,
            "date": date,
            "snippet": msg_data.get("snippet", "")
        })
    return email_list


def read_msg(service, msg_id):
    """Fetches full content and body of a specific email by ID."""
    data = service.users().messages().get(userId="me", id=msg_id).execute()
    
    headers = data.get("payload", {}).get("headers", [])
    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
    sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
    date = next((h["value"] for h in headers if h["name"].lower() == "date"), "Unknown Date")
    snippet = data.get("snippet", "")
    
    # Recursive parser to extract email body content
    def extract_body(payload):
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
        
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    return base64.urlsafe_b64decode(part["body"].get("data", "")).decode("utf-8", errors="ignore")
            # Fallback to html if plain text isn't available
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html":
                    return base64.urlsafe_b64decode(part["body"].get("data", "")).decode("utf-8", errors="ignore")
                elif "parts" in part:
                    res = extract_body(part)
                    if res:
                        return res
        return ""

    clean_body = extract_body(data.get("payload", {})) or snippet

    return {
        "id": msg_id,
        "from": sender,
        "subject": subject,
        "date": date,
        "snippet": snippet,
        "body": clean_body
    }


def send_email(service, to, subject, body_text):
    """Creates and sends a plain text email."""
    from email.mime.text import MIMEText
    
    message = MIMEText(body_text)
    message["to"] = to
    message["subject"] = subject
    
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    sent_message = service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
    return sent_message


def search_emails(service, query, max_results=5):
    """Helper search function leveraging standard Gmail query syntax."""
    return list_recent_emails(service, max_results=max_results, query=query)


def modify_email_labels(service, msg_id, add_labels=None, remove_labels=None):
    """Modifies email labels (e.g., mark as read, archive, apply custom label)."""
    body = {
        "addLabelIds": add_labels or [],
        "removeLabelIds": remove_labels or []
    }
    return service.users().messages().modify(userId="me", id=msg_id, body=body).execute()


def delete_email(service, msg_id):
    """Moves an email to the Trash bin."""
    return service.users().messages().trash(userId="me", id=msg_id).execute()


#==============
# Model Tools
#==============

def list_emails_tool(max_results:int=5, query:str="") -> str:
    """
    List recent emails or search with a query string.
    Returns formatted Markdown list for the LLM.
    """
    print("SYS: Listing Emails...")
    try:
        service = get_service()
        emails = list_recent_emails(service, max_results=max_results, query=query)
        
        if not emails:
            return "### Email List\nNo emails found matching your query."
        
        output = [f"### Recent Emails (Found {len(emails)})\n"]
        for idx, email in enumerate(emails, 1):
            output.append(
                f"**{idx}. Subject:** {email['subject']}\n"
                f"   * **ID:** `{email['id']}`\n"
                f"   * **From:** {email['from']}\n"
                f"   * **Date:** {email['date']}\n"
                f"   * **Snippet:** *{email['snippet']}*\n"
            )
        return "\n".join(output)
    except Exception as e:
        return f"**Error listing emails:** {str(e)}"


def read_email_tool(email_id:str) -> str:
    """
    Read full message content by Message ID.
    Returns structured Markdown with email metadata and plain text body.
    """
    print("Reading Emails...")
    try:
        service = get_service()
        data = read_msg(service, email_id)
        
        return (
            f"### Email Details\n"
            f"- **Subject:** {data['subject']}\n"
            f"- **From:** {data['from']}\n"
            f"- **Date:** {data['date']}\n"
            f"- **ID:** `{data['id']}`\n\n"
            f"--- \n"
            f"### Message Body:\n"
            f"{data['body']}\n"
        )
    except Exception as e:
        return f"**Error reading email ID `{email_id}`:** {str(e)}"


def send_email_tool(to:str, subject:str, body:str) -> str:
    """
    Send an email given recipient, subject, and body text.
    Returns confirmation status in Markdown format.
    """
    print("SYS: Sending Emails...")
    try:
        service = get_service()
        res = send_email(service, to, subject, body)
        return (
            f"### Email Sent Successfully\n"
            f"- **To:** {to}\n"
            f"- **Subject:** {subject}\n"
            f"- **Message ID:** `{res.get('id')}`"
        )
    except Exception as e:
        return f"**Error sending email:** {str(e)}"


def mark_as_read_tool(email_id:str) -> str:
    """
    Mark a specific email message as read.
    """
    print("Marking as Read..")
    try:
        service = get_service()
        modify_email_labels(service, email_id, remove_labels=["UNREAD"])
        return f"**Success:** Email `{email_id}` has been marked as read."
    except Exception as e:
        return f"**Error marking email as read:** {str(e)}"


def trash_email_tool(email_id:str) -> str:
    """
    Move an email message to Trash.
    """
    print("Moving Emails to Trash...")
    try:
        service = get_service()
        delete_email(service, email_id)
        return f"**Success:** Email `{email_id}` has been moved to Trash."
    except Exception as e:
        return f"**Error moving email to trash:** {str(e)}"