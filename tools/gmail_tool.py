import base64
import functools
import os
from email.mime.text import MIMEText
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

#==================
# Made by Claude
#==================

# This tool is still a prototype
#
# NOTE ON SCOPES:
# "gmail.modify" covers almost everything (read, send, label, trash, drafts,
# history, watch) but NOT permanent deletion of messages/threads, which Google
# gates behind the full "https://mail.google.com/" scope. Settings (filters,
# vacation responder, forwarding, send-as) need their own settings scopes.
# If you delete token.json and re-auth, Google will show a broader consent
# screen because of this. If you don't need permanent delete or settings
# management, you can drop back to just "gmail.modify" and remove those
# functions below.
SCOPES = [
    "https://mail.google.com/",  # full access, includes permanent delete
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/gmail.settings.sharing",
]

# ==================
# User Functions
# ==================

def get_service():
    """Authenticates the user and returns the Gmail API service object."""
    creds = None
    if os.path.exists("gmail_token.json"):
        creds = Credentials.from_authorized_user_file("gmmail_token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("gmail_token.json", "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


# ---- Messages ----

def list_recent_emails(service, max_results=10, query="", label_ids=None, include_spam_trash=False):
    """Lists recent emails matching an optional Gmail search query."""
    result = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        q=query,
        labelIds=label_ids,
        includeSpamTrash=include_spam_trash,
    ).execute()
    messages = result.get("messages", [])

    email_list = []
    for msg in messages:
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
    """Fetches full content, body, and attachment metadata of a specific email by ID."""
    data = service.users().messages().get(userId="me", id=msg_id).execute()

    headers = data.get("payload", {}).get("headers", [])
    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
    sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
    date = next((h["value"] for h in headers if h["name"].lower() == "date"), "Unknown Date")
    snippet = data.get("snippet", "")

    def extract_body(payload):
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")

        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    return base64.urlsafe_b64decode(part["body"].get("data", "")).decode("utf-8", errors="ignore")
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html":
                    return base64.urlsafe_b64decode(part["body"].get("data", "")).decode("utf-8", errors="ignore")
                elif "parts" in part:
                    res = extract_body(part)
                    if res:
                        return res
        return ""

    def extract_attachments(payload, found=None):
        if found is None:
            found = []
        for part in payload.get("parts", []) or []:
            filename = part.get("filename")
            body = part.get("body", {})
            if filename and body.get("attachmentId"):
                found.append({
                    "filename": filename,
                    "mimeType": part.get("mimeType", "application/octet-stream"),
                    "attachmentId": body["attachmentId"],
                    "size": body.get("size", 0),
                })
            if "parts" in part:
                extract_attachments(part, found)
        return found

    payload = data.get("payload", {})
    clean_body = extract_body(payload) or snippet
    attachments = extract_attachments(payload)

    return {
        "id": msg_id,
        "threadId": data.get("threadId"),
        "from": sender,
        "subject": subject,
        "date": date,
        "snippet": snippet,
        "body": clean_body,
        "attachments": attachments,
        "labelIds": data.get("labelIds", []),
    }

def send_email(service, to, subject, body, thread_id=None, attachment_paths=None):
    if attachment_paths:
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        message.attach(MIMEText(body, "plain"))

        for path in attachment_paths:
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Attachment not found: {path}")

            ctype, encoding = mimetypes.guess_type(path)
            if ctype is None or encoding is not None:
                ctype = "application/octet-stream"
            main_type, sub_type = ctype.split("/", 1)

            with open(path, "rb") as f:
                part = MIMEBase(main_type, sub_type)
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{os.path.basename(path)}"'
            )
            message.attach(part)
    else:
        # your existing plain-text path
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body_payload = {"raw": raw}
    if thread_id:
        body_payload["threadId"] = thread_id

    return service.users().messages().send(userId="me", body=body_payload).execute()


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
    """Moves an email to the Trash bin (recoverable)."""
    return service.users().messages().trash(userId="me", id=msg_id).execute()


def untrash_email(service, msg_id):
    """Removes an email from Trash, restoring it to its previous labels."""
    return service.users().messages().untrash(userId="me", id=msg_id).execute()


def permanently_delete_email(service, msg_id):
    """Immediately and permanently deletes a message. Cannot be undone. Requires the
    https://mail.google.com/ scope."""
    return service.users().messages().delete(userId="me", id=msg_id).execute()


def batch_modify_messages(service, msg_ids, add_labels=None, remove_labels=None):
    """Applies the same label changes to many messages in one quota-efficient call."""
    body = {
        "ids": msg_ids,
        "addLabelIds": add_labels or [],
        "removeLabelIds": remove_labels or [],
    }
    return service.users().messages().batchModify(userId="me", body=body).execute()


def batch_delete_messages(service, msg_ids):
    """Permanently deletes many messages at once. Cannot be undone. Requires the
    https://mail.google.com/ scope."""
    return service.users().messages().batchDelete(userId="me", body={"ids": msg_ids}).execute()


def insert_message(service, raw_rfc822_bytes, label_ids=None):
    """Directly inserts a message into the mailbox (bypasses SMTP sending, skips spam
    classification). raw_rfc822_bytes must be a full RFC822 message as bytes."""
    body = {"raw": base64.urlsafe_b64encode(raw_rfc822_bytes).decode("utf-8")}
    if label_ids:
        body["labelIds"] = label_ids
    return service.users().messages().insert(userId="me", body=body).execute()


def import_message(service, raw_rfc822_bytes, label_ids=None, process_for_calendar=False):
    """Imports a message like insert(), but also runs Gmail's spam classifier. Useful
    for migrating mail from another provider. By default no INBOX/UNREAD labels are
    applied unless you pass them in label_ids."""
    body = {"raw": base64.urlsafe_b64encode(raw_rfc822_bytes).decode("utf-8")}
    if label_ids:
        body["labelIds"] = label_ids
    return service.users().messages().import_(
        userId="me", body=body, processForCalendar=process_for_calendar
    ).execute()


def get_attachment(service, msg_id, attachment_id):
    """Fetches a message attachment's base64url-encoded data by its attachment ID
    (obtained from read_msg's 'attachments' list)."""
    return service.users().messages().attachments().get(
        userId="me", messageId=msg_id, id=attachment_id
    ).execute()


# ---- Threads ----

def list_threads(service, max_results=10, query="", label_ids=None):
    """Lists conversation threads matching an optional Gmail search query."""
    result = service.users().threads().list(
        userId="me", maxResults=max_results, q=query, labelIds=label_ids
    ).execute()
    return result.get("threads", [])


def get_thread(service, thread_id, format="full"):
    """Fetches a full thread (all messages in a conversation). format can be
    'full', 'metadata', or 'minimal'."""
    return service.users().threads().get(userId="me", id=thread_id, format=format).execute()


def trash_thread(service, thread_id):
    """Moves an entire thread to Trash."""
    return service.users().threads().trash(userId="me", id=thread_id).execute()


def untrash_thread(service, thread_id):
    """Removes an entire thread from Trash."""
    return service.users().threads().untrash(userId="me", id=thread_id).execute()


def delete_thread(service, thread_id):
    """Permanently deletes an entire thread. Cannot be undone."""
    return service.users().threads().delete(userId="me", id=thread_id).execute()


def modify_thread_labels(service, thread_id, add_labels=None, remove_labels=None):
    """Modifies labels across every message in a thread at once."""
    body = {"addLabelIds": add_labels or [], "removeLabelIds": remove_labels or []}
    return service.users().threads().modify(userId="me", id=thread_id, body=body).execute()


# ---- Labels ----

def list_labels(service):
    """Lists all labels (system + custom) in the mailbox."""
    result = service.users().labels().list(userId="me").execute()
    return result.get("labels", [])


def get_label(service, label_id):
    """Fetches a single label's details, including unread/total message counts."""
    return service.users().labels().get(userId="me", id=label_id).execute()


def create_label(service, name, label_list_visibility="labelShow", message_list_visibility="show"):
    """Creates a new custom label."""
    body = {
        "name": name,
        "labelListVisibility": label_list_visibility,
        "messageListVisibility": message_list_visibility,
    }
    return service.users().labels().create(userId="me", body=body).execute()


def update_label(service, label_id, name=None, label_list_visibility=None, message_list_visibility=None):
    """Updates a label's name or visibility settings (partial update)."""
    body = {}
    if name is not None:
        body["name"] = name
    if label_list_visibility is not None:
        body["labelListVisibility"] = label_list_visibility
    if message_list_visibility is not None:
        body["messageListVisibility"] = message_list_visibility
    return service.users().labels().patch(userId="me", id=label_id, body=body).execute()


def delete_label(service, label_id):
    """Permanently deletes a label and removes it from any messages/threads."""
    return service.users().labels().delete(userId="me", id=label_id).execute()


# ---- Drafts ----

def list_drafts(service, max_results=10):
    """Lists saved drafts."""
    result = service.users().drafts().list(userId="me", maxResults=max_results).execute()
    return result.get("drafts", [])


def get_draft(service, draft_id):
    """Fetches a single draft's full content."""
    return service.users().drafts().get(userId="me", id=draft_id).execute()


def create_draft(service, to, subject, body_text, thread_id=None):
    """Creates a new draft without sending it."""
    message = MIMEText(body_text)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    draft_body = {"message": {"raw": raw}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id
    return service.users().drafts().create(userId="me", body=draft_body).execute()


def update_draft(service, draft_id, to, subject, body_text):
    """Replaces the content of an existing draft."""
    message = MIMEText(body_text)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return service.users().drafts().update(userId="me", id=draft_id, body={"message": {"raw": raw}}).execute()


def send_draft(service, draft_id):
    """Sends an existing draft as-is."""
    return service.users().drafts().send(userId="me", body={"id": draft_id}).execute()


def delete_draft(service, draft_id):
    """Permanently deletes a draft (does not affect a sent copy, since it was never sent)."""
    return service.users().drafts().delete(userId="me", id=draft_id).execute()


# ---- History (incremental sync) ----

def list_history(service, start_history_id, history_types=None, label_id=None, max_results=100):
    """Lists mailbox changes (added/deleted messages, label changes) since a given
    historyId. Much cheaper than re-listing messages when polling for updates.
    Get a starting historyId from get_profile()['historyId']."""
    kwargs = {
        "userId": "me",
        "startHistoryId": start_history_id,
        "maxResults": max_results,
    }
    if history_types:
        kwargs["historyTypes"] = history_types
    if label_id:
        kwargs["labelId"] = label_id
    result = service.users().history().list(**kwargs).execute()
    return result.get("history", [])


# ---- Profile & Push Notifications ----

def get_profile(service):
    """Gets mailbox-wide info: email address, current historyId, total message/thread counts."""
    return service.users().getProfile(userId="me").execute()


def watch_mailbox(service, topic_name, label_ids=None):
    """Registers a Cloud Pub/Sub push notification watch on the mailbox. topic_name is
    a fully-qualified Pub/Sub topic, e.g. 'projects/my-project/topics/gmail-updates'.
    Watches expire after ~7 days and must be renewed."""
    body = {"topicName": topic_name}
    if label_ids:
        body["labelIds"] = label_ids
    return service.users().watch(userId="me", body=body).execute()


def stop_watch(service):
    """Stops push notifications for the mailbox."""
    return service.users().stop(userId="me").execute()


# ---- Settings ----

def list_filters(service):
    """Lists mail filters (auto-labeling/archiving/forwarding rules)."""
    result = service.users().settings().filters().list(userId="me").execute()
    return result.get("filter", [])


def get_filter(service, filter_id):
    """Fetches a single filter's criteria and action."""
    return service.users().settings().filters().get(userId="me", id=filter_id).execute()


def create_filter(service, criteria, action):
    """Creates a new mail filter. criteria and action are dicts matching the Gmail API
    filter schema, e.g. criteria={'from': 'x@y.com'}, action={'addLabelIds': ['IMPORTANT']}."""
    body = {"criteria": criteria, "action": action}
    return service.users().settings().filters().create(userId="me", body=body).execute()


def delete_filter(service, filter_id):
    """Deletes a mail filter."""
    return service.users().settings().filters().delete(userId="me", id=filter_id).execute()


def get_vacation_settings(service):
    """Fetches the current vacation responder (auto-reply) configuration."""
    return service.users().settings().getVacation(userId="me").execute()


def update_vacation_settings(service, enable_auto_reply, subject="", body_text="", start_time=None, end_time=None):
    """Enables/updates/disables the vacation auto-responder. start_time/end_time are
    epoch ms strings, if provided."""
    body = {
        "enableAutoReply": enable_auto_reply,
        "responseSubject": subject,
        "responseBodyPlainText": body_text,
    }
    if start_time is not None:
        body["startTime"] = start_time
    if end_time is not None:
        body["endTime"] = end_time
    return service.users().settings().updateVacation(userId="me", body=body).execute()


def list_forwarding_addresses(service):
    """Lists addresses configured for auto-forwarding."""
    result = service.users().settings().forwardingAddresses().list(userId="me").execute()
    return result.get("forwardingAddresses", [])


def list_send_as_aliases(service):
    """Lists send-as aliases (alternate 'From' addresses) configured on the account."""
    result = service.users().settings().sendAs().list(userId="me").execute()
    return result.get("sendAs", [])


# ==============
# Model Tools
# ==============

def _tool(action_desc: str = "Using a Tool"):
    """Decorator shared by all Model Tools: logs the action, catches exceptions, and
    returns a Markdown error string instead of raising, so the LLM always gets a
    usable response."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            print(f"SYS: {action_desc}...")
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return f"**Error during '{action_desc}':** {str(e)}"
        return wrapper
    return decorator


# ---- Messages ----

@_tool("Listing Emails")
def list_emails_tool(max_results: int = 5, query: str = "") -> str:
    """
    List recent emails or search with a query string.
    Returns formatted Markdown list for the LLM.
    """
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


@_tool("Reading Email")
def read_email_tool(email_id: str) -> str:
    """
    Read full message content by Message ID.
    Returns structured Markdown with email metadata, plain text body, and any attachments.
    """
    service = get_service()
    data = read_msg(service, email_id)

    attachments_md = ""
    if data["attachments"]:
        lines = [f"- **{a['filename']}** (`{a['attachmentId']}`, {a['mimeType']}, {a['size']} bytes)" for a in data["attachments"]]
        attachments_md = "\n\n### Attachments:\n" + "\n".join(lines)

    return (
        f"### Email Details\n"
        f"- **Subject:** {data['subject']}\n"
        f"- **From:** {data['from']}\n"
        f"- **Date:** {data['date']}\n"
        f"- **ID:** `{data['id']}`\n"
        f"- **Thread ID:** `{data['threadId']}`\n"
        f"- **Labels:** {', '.join(data['labelIds']) or 'None'}\n\n"
        f"--- \n"
        f"### Message Body:\n"
        f"{data['body']}\n"
        f"{attachments_md}"
    )


@_tool("Sending Email")
def send_email_tool(to: str, subject: str, body: str, thread_id: str = None, attachment_paths: list[str] = None) -> str:
    """
    Send an email given recipient, subject, and body text. Pass thread_id to send as
    a reply within an existing conversation. Pass attachment_paths (local file paths)
    to attach one or more files.
    Returns confirmation status in Markdown format.
    """
    service = get_service()
    res = send_email(service, to, subject, body, thread_id=thread_id, attachment_paths=attachment_paths)
    attach_note = f"\n- **Attachments:** {', '.join(attachment_paths)}" if attachment_paths else ""
    return (
        f"### Email Sent Successfully\n"
        f"- **To:** {to}\n"
        f"- **Subject:** {subject}\n"
        f"- **Message ID:** `{res.get('id')}`"
        f"{attach_note}"
    )


@_tool("Marking as Read")
def mark_as_read_tool(email_id: str) -> str:
    """
    Mark a specific email message as read.
    """
    service = get_service()
    modify_email_labels(service, email_id, remove_labels=["UNREAD"])
    return f"**Success:** Email `{email_id}` has been marked as read."


@_tool("Marking as Unread")
def mark_as_unread_tool(email_id: str) -> str:
    """
    Mark a specific email message as unread.
    """
    service = get_service()
    modify_email_labels(service, email_id, add_labels=["UNREAD"])
    return f"**Success:** Email `{email_id}` has been marked as unread."


@_tool("Applying Labels")
def apply_labels_tool(email_id: str, add_labels: list[str] = None, remove_labels: list[str] = None) -> str:
    """
    Add and/or remove label IDs on a specific email (e.g. add 'IMPORTANT', remove 'INBOX' to archive).
    Use list_labels_tool first to see available label IDs.
    """
    service = get_service()
    modify_email_labels(service, email_id, add_labels=add_labels, remove_labels=remove_labels)
    return (
        f"**Success:** Updated labels on `{email_id}`.\n"
        f"- Added: {', '.join(add_labels) if add_labels else 'none'}\n"
        f"- Removed: {', '.join(remove_labels) if remove_labels else 'none'}"
    )


@_tool("Moving Email to Trash")
def trash_email_tool(email_id: str) -> str:
    """
    Move an email message to Trash (recoverable via untrash_email_tool).
    """
    service = get_service()
    delete_email(service, email_id)
    return f"**Success:** Email `{email_id}` has been moved to Trash."


@_tool("Restoring Email from Trash")
def untrash_email_tool(email_id: str) -> str:
    """
    Restore an email message from Trash.
    """
    service = get_service()
    untrash_email(service, email_id)
    return f"**Success:** Email `{email_id}` has been restored from Trash."


@_tool("Permanently Deleting Email")
def permanently_delete_email_tool(email_id: str) -> str:
    """
    Permanently and irreversibly delete a message, bypassing Trash. Use with caution.
    """
    service = get_service()
    permanently_delete_email(service, email_id)
    return f"**Success:** Email `{email_id}` has been permanently deleted. This cannot be undone."


@_tool("Batch Updating Labels")
def batch_apply_labels_tool(email_ids: list[str], add_labels: list[str] = None, remove_labels: list[str] = None) -> str:
    """
    Add/remove labels across multiple messages at once (more quota-efficient than looping).
    """
    service = get_service()
    batch_modify_messages(service, email_ids, add_labels=add_labels, remove_labels=remove_labels)
    return f"**Success:** Updated labels on {len(email_ids)} messages."


@_tool("Batch Deleting Emails")
def batch_permanently_delete_tool(email_ids: list[str]) -> str:
    """
    Permanently and irreversibly delete multiple messages at once. Use with caution.
    """
    service = get_service()
    batch_delete_messages(service, email_ids)
    return f"**Success:** Permanently deleted {len(email_ids)} messages. This cannot be undone."


@_tool("Downloading Attachment")
def download_attachment_tool(email_id: str, attachment_id: str, filename: str, save_dir: str = ".") -> str:
    """
    Download a message attachment to local disk. Get attachment_id/filename from read_email_tool.
    """
    service = get_service()
    att = get_attachment(service, email_id, attachment_id)
    file_data = base64.urlsafe_b64decode(att["data"])
    save_path = os.path.join(save_dir, filename)
    with open(save_path, "wb") as f:
        f.write(file_data)
    return f"**Success:** Saved attachment to `{save_path}` ({len(file_data)} bytes)."


# ---- Threads ----

@_tool("Listing Threads")
def list_threads_tool(max_results: int = 5, query: str = "") -> str:
    """
    List conversation threads, optionally filtered by a Gmail search query.
    """
    service = get_service()
    threads = list_threads(service, max_results=max_results, query=query)
    if not threads:
        return "### Threads\nNo threads found matching your query."
    lines = [f"- **Thread ID:** `{t['id']}` — *{t.get('snippet', '')}*" for t in threads]
    return f"### Threads (Found {len(threads)})\n" + "\n".join(lines)


@_tool("Reading Thread")
def read_thread_tool(thread_id: str) -> str:
    """
    Read every message in a conversation thread, in order.
    """
    service = get_service()
    thread = get_thread(service, thread_id)
    messages = thread.get("messages", [])
    output = [f"### Thread `{thread_id}` ({len(messages)} messages)\n"]
    for i, msg in enumerate(messages, 1):
        headers = msg.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No Subject")
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown Sender")
        output.append(f"**{i}. From:** {sender} — **Subject:** {subject}\n   *{msg.get('snippet', '')}*")
    return "\n".join(output)


@_tool("Moving Thread to Trash")
def trash_thread_tool(thread_id: str) -> str:
    """
    Move an entire conversation thread to Trash.
    """
    service = get_service()
    trash_thread(service, thread_id)
    return f"**Success:** Thread `{thread_id}` has been moved to Trash."


@_tool("Restoring Thread from Trash")
def untrash_thread_tool(thread_id: str) -> str:
    """
    Restore an entire conversation thread from Trash.
    """
    service = get_service()
    untrash_thread(service, thread_id)
    return f"**Success:** Thread `{thread_id}` has been restored from Trash."


@_tool("Permanently Deleting Thread")
def permanently_delete_thread_tool(thread_id: str) -> str:
    """
    Permanently and irreversibly delete an entire thread. Use with caution.
    """
    service = get_service()
    delete_thread(service, thread_id)
    return f"**Success:** Thread `{thread_id}` has been permanently deleted. This cannot be undone."


@_tool("Applying Labels to Thread")
def apply_thread_labels_tool(thread_id: str, add_labels: list[str] = None, remove_labels: list[str] = None) -> str:
    """
    Add/remove labels across every message in a thread at once.
    """
    service = get_service()
    modify_thread_labels(service, thread_id, add_labels=add_labels, remove_labels=remove_labels)
    return f"**Success:** Updated labels on thread `{thread_id}`."


# ---- Labels ----

@_tool("Listing Labels")
def list_labels_tool() -> str:
    """
    List all labels (system and custom) in the mailbox, with IDs needed for other tools.
    """
    service = get_service()
    labels = list_labels(service)
    lines = [f"- **{l['name']}** — ID: `{l['id']}` ({l.get('type', 'user')})" for l in labels]
    return f"### Labels (Found {len(labels)})\n" + "\n".join(lines)


@_tool("Creating Label")
def create_label_tool(name: str) -> str:
    """
    Create a new custom label with the given name.
    """
    service = get_service()
    label = create_label(service, name)
    return f"**Success:** Created label **{label['name']}** with ID `{label['id']}`."


@_tool("Renaming Label")
def rename_label_tool(label_id: str, new_name: str) -> str:
    """
    Rename an existing custom label.
    """
    service = get_service()
    label = update_label(service, label_id, name=new_name)
    return f"**Success:** Label `{label_id}` renamed to **{label['name']}**."


@_tool("Deleting Label")
def delete_label_tool(label_id: str) -> str:
    """
    Permanently delete a label and remove it from any messages/threads it's applied to.
    """
    service = get_service()
    delete_label(service, label_id)
    return f"**Success:** Label `{label_id}` has been deleted."


# ---- Drafts ----

@_tool("Listing Drafts")
def list_drafts_tool(max_results: int = 5) -> str:
    """
    List saved but unsent drafts.
    """
    service = get_service()
    drafts = list_drafts(service, max_results=max_results)
    if not drafts:
        return "### Drafts\nNo drafts found."
    lines = [f"- **Draft ID:** `{d['id']}` (Message ID: `{d.get('message', {}).get('id', '?')}`)" for d in drafts]
    return f"### Drafts (Found {len(drafts)})\n" + "\n".join(lines)


@_tool("Creating Draft")
def create_draft_tool(to: str, subject: str, body: str) -> str:
    """
    Create a new draft email without sending it, for later review or editing.
    """
    service = get_service()
    draft = create_draft(service, to, subject, body)
    return f"**Success:** Draft created with ID `{draft['id']}`."


@_tool("Updating Draft")
def update_draft_tool(draft_id: str, to: str, subject: str, body: str) -> str:
    """
    Replace the content of an existing draft.
    """
    service = get_service()
    update_draft(service, draft_id, to, subject, body)
    return f"**Success:** Draft `{draft_id}` updated."


@_tool("Sending Draft")
def send_draft_tool(draft_id: str) -> str:
    """
    Send an existing draft as-is.
    """
    service = get_service()
    res = send_draft(service, draft_id)
    return f"**Success:** Draft `{draft_id}` sent as message `{res.get('id')}`."


@_tool("Deleting Draft")
def delete_draft_tool(draft_id: str) -> str:
    """
    Permanently delete a draft.
    """
    service = get_service()
    delete_draft(service, draft_id)
    return f"**Success:** Draft `{draft_id}` has been deleted."


# ---- History ----

@_tool("Checking Mailbox History")
def list_history_tool(start_history_id: str) -> str:
    """
    List what changed in the mailbox (new messages, deletions, label changes) since a
    given historyId. Get a starting ID from get_profile_tool.
    """
    service = get_service()
    history = list_history(service, start_history_id)
    if not history:
        return f"### History\nNo changes since historyId `{start_history_id}`."
    return f"### History (Found {len(history)} change records since `{start_history_id}`)\n" + \
        "\n".join(f"- historyId `{h['id']}`: {list(h.keys())}" for h in history)


# ---- Profile & Watch ----

@_tool("Fetching Mailbox Profile")
def get_profile_tool() -> str:
    """
    Get mailbox-wide info: email address, current historyId, total message and thread counts.
    """
    service = get_service()
    profile = get_profile(service)
    return (
        f"### Mailbox Profile\n"
        f"- **Email:** {profile.get('emailAddress')}\n"
        f"- **Total Messages:** {profile.get('messagesTotal')}\n"
        f"- **Total Threads:** {profile.get('threadsTotal')}\n"
        f"- **Current History ID:** `{profile.get('historyId')}`"
    )


@_tool("Starting Mailbox Watch")
def watch_mailbox_tool(topic_name: str) -> str:
    """
    Register a Cloud Pub/Sub push-notification watch on the mailbox for real-time
    updates. topic_name looks like 'projects/PROJECT_ID/topics/TOPIC_NAME'. Expires
    after ~7 days and must be renewed.
    """
    service = get_service()
    res = watch_mailbox(service, topic_name)
    return f"**Success:** Watch registered. Expires at `{res.get('expiration')}` (epoch ms). History ID: `{res.get('historyId')}`."


@_tool("Stopping Mailbox Watch")
def stop_watch_tool() -> str:
    """
    Stop push notifications for the mailbox.
    """
    service = get_service()
    stop_watch(service)
    return "**Success:** Mailbox watch stopped."


# ---- Settings ----

@_tool("Listing Filters")
def list_filters_tool() -> str:
    """
    List mail filters (auto-labeling/archiving/forwarding rules).
    """
    service = get_service()
    filters = list_filters(service)
    if not filters:
        return "### Filters\nNo filters configured."
    lines = [f"- **ID:** `{f['id']}` — Criteria: {f.get('criteria')} → Action: {f.get('action')}" for f in filters]
    return f"### Filters (Found {len(filters)})\n" + "\n".join(lines)


@_tool("Creating Filter")
def create_filter_tool(criteria: dict, action: dict) -> str:
    """
    Create a new mail filter. criteria e.g. {'from': 'x@y.com'}, action e.g.
    {'addLabelIds': ['IMPORTANT'], 'removeLabelIds': ['INBOX']}.
    """
    service = get_service()
    f = create_filter(service, criteria, action)
    return f"**Success:** Filter created with ID `{f['id']}`."


@_tool("Deleting Filter")
def delete_filter_tool(filter_id: str) -> str:
    """
    Delete a mail filter by ID.
    """
    service = get_service()
    delete_filter(service, filter_id)
    return f"**Success:** Filter `{filter_id}` has been deleted."


@_tool("Fetching Vacation Responder Settings")
def get_vacation_settings_tool() -> str:
    """
    Get the current vacation auto-responder configuration.
    """
    service = get_service()
    v = get_vacation_settings(service)
    return (
        f"### Vacation Responder\n"
        f"- **Enabled:** {v.get('enableAutoReply')}\n"
        f"- **Subject:** {v.get('responseSubject')}\n"
        f"- **Body:** {v.get('responseBodyPlainText')}"
    )


@_tool("Updating Vacation Responder")
def update_vacation_settings_tool(enable_auto_reply: bool, subject: str = "", body: str = "") -> str:
    """
    Enable/update or disable the vacation auto-responder.
    """
    service = get_service()
    update_vacation_settings(service, enable_auto_reply, subject=subject, body_text=body)
    state = "enabled" if enable_auto_reply else "disabled"
    return f"**Success:** Vacation responder {state}."


@_tool("Listing Forwarding Addresses")
def list_forwarding_addresses_tool() -> str:
    """
    List addresses configured for auto-forwarding.
    """
    service = get_service()
    addrs = list_forwarding_addresses(service)
    if not addrs:
        return "### Forwarding Addresses\nNone configured."
    lines = [f"- {a['forwardingEmail']} ({a.get('verificationStatus')})" for a in addrs]
    return "### Forwarding Addresses\n" + "\n".join(lines)


@_tool("Listing Send-As Aliases")
def list_send_as_aliases_tool() -> str:
    """
    List send-as aliases (alternate 'From' addresses) configured on the account.
    """
    service = get_service()
    aliases = list_send_as_aliases(service)
    lines = [f"- {a['sendAsEmail']}{' (default)' if a.get('isDefault') else ''}" for a in aliases]
    return f"### Send-As Aliases (Found {len(aliases)})\n" + "\n".join(lines)