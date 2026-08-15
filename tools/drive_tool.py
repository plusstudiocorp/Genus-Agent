import functools
import os
import io
import mimetypes

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_PATH = "drive_token.json"
CREDENTIALS_PATH = "credentials.json"


# ---- Service setup (built once, at import time) ----

def _build_service():
    """Authenticates and builds the Drive API service. Called once at module import."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


_service = _build_service()  # built once, when this module is imported


# ---- Tool decorator (same as your Gmail tools) ----

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


#==================
# User Functions
#==================

def list_files(service, query: str = "", max_results: int = 10, order_by: str = "modifiedTime desc") -> list[dict]:
    res = service.files().list(
        q=query if query else None,
        pageSize=max_results,
        orderBy=order_by,
        fields="files(id, name, mimeType, modifiedTime, size, parents, webViewLink)"
    ).execute()
    return res.get("files", [])


def get_file_metadata(service, file_id: str) -> dict:
    return service.files().get(
        fileId=file_id,
        fields="id, name, mimeType, modifiedTime, size, parents, webViewLink, owners"
    ).execute()

def create_file(service, name: str, content: str, mime_type: str = "text/plain", parent_folder_id: str = None) -> dict:
    file_metadata = {"name": name}
    if parent_folder_id:
        file_metadata["parents"] = [parent_folder_id]

    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")),
        mimetype=mime_type
    )
    return service.files().create(
        body=file_metadata, media_body=media, fields="id, name, webViewLink"
    ).execute()


def upload_file(service, local_path: str, name: str = None, parent_folder_id: str = None) -> dict:
    if not os.path.isfile(local_path):
        raise FileNotFoundError(f"Local file not found: {local_path}")

    file_name = name or os.path.basename(local_path)
    mime_type, _ = mimetypes.guess_type(local_path)
    mime_type = mime_type or "application/octet-stream"

    file_metadata = {"name": file_name}
    if parent_folder_id:
        file_metadata["parents"] = [parent_folder_id]

    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
    return service.files().create(
        body=file_metadata, media_body=media, fields="id, name, webViewLink"
    ).execute()


def download_file(service, file_id: str, save_path: str) -> str:
    meta = service.files().get(fileId=file_id, fields="mimeType, name").execute()

    export_map = {
        "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
        "application/vnd.google-apps.spreadsheet": ("application/pdf", ".pdf"),
        "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    }

    if meta["mimeType"] in export_map:
        export_mime, ext = export_map[meta["mimeType"]]
        if not save_path.endswith(ext):
            save_path += ext
        request = service.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        request = service.files().get_media(fileId=file_id)

    with io.FileIO(save_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    return save_path


def create_folder(service, name: str, parent_folder_id: str = None) -> dict:
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_folder_id:
        metadata["parents"] = [parent_folder_id]
    return service.files().create(body=metadata, fields="id, name, webViewLink").execute()


def move_file(service, file_id: str, new_parent_folder_id: str) -> dict:
    file = service.files().get(fileId=file_id, fields="parents").execute()
    previous_parents = ",".join(file.get("parents", []))
    return service.files().update(
        fileId=file_id,
        addParents=new_parent_folder_id,
        removeParents=previous_parents,
        fields="id, name, parents"
    ).execute()


def copy_file(service, file_id: str, new_name: str = None) -> dict:
    body = {"name": new_name} if new_name else {}
    return service.files().copy(fileId=file_id, body=body, fields="id, name, webViewLink").execute()


def rename_file(service, file_id: str, new_name: str) -> dict:
    return service.files().update(fileId=file_id, body={"name": new_name}, fields="id, name").execute()


def trash_file(service, file_id: str) -> dict:
    return service.files().update(fileId=file_id, body={"trashed": True}, fields="id, name, trashed").execute()


def untrash_file(service, file_id: str) -> dict:
    return service.files().update(fileId=file_id, body={"trashed": False}, fields="id, name, trashed").execute()


def permanently_delete_file(service, file_id: str) -> None:
    service.files().delete(fileId=file_id).execute()


def share_file(service, file_id: str, email: str, role: str = "reader") -> dict:
    permission = {"type": "user", "role": role, "emailAddress": email}
    return service.permissions().create(
        fileId=file_id, body=permission, fields="id", sendNotificationEmail=True
    ).execute()


def list_permissions(service, file_id: str) -> list[dict]:
    res = service.permissions().list(
        fileId=file_id, fields="permissions(id, type, role, emailAddress)"
    ).execute()
    return res.get("permissions", [])


#===================
# Model Functions
#===================

@_tool("Listing Drive Files")
def list_files_tool(query: str = "", max_results: int = 10) -> str:
    """
    List files in Google Drive, optionally filtered with a Drive search query
    (e.g. "name contains 'report'" or "mimeType='application/pdf'").
    """
    files = list_files(_service, query=query, max_results=max_results)
    if not files:
        return "### Drive Files\nNo files found matching your query."
    lines = [f"- **{f['name']}** (`{f['id']}`) — {f['mimeType']}" for f in files]
    return f"### Drive Files (Found {len(files)})\n" + "\n".join(lines)


@_tool("Fetching File Metadata")
def get_file_metadata_tool(file_id: str) -> str:
    """
    Get metadata for a specific Drive file: name, type, size, modified time, link.
    """
    meta = get_file_metadata(_service, file_id)
    return (
        f"### File Details\n"
        f"- **Name:** {meta.get('name')}\n"
        f"- **Type:** {meta.get('mimeType')}\n"
        f"- **Modified:** {meta.get('modifiedTime')}\n"
        f"- **Size:** {meta.get('size', 'N/A')} bytes\n"
        f"- **Link:** {meta.get('webViewLink')}"
    )

@_tool("Creating File")
def create_file_tool(name: str, content: str, mime_type: str = "text/plain", parent_folder_id: str = None) -> str:
    """
    Create a new file directly in Drive from text content — no local file or upload
    needed. Use this for notes, generated reports, CSVs, JSON, code, or any text-based
    content the model itself is producing. mime_type examples: "text/plain",
    "text/csv", "text/markdown", "application/json". parent_folder_id is optional —
    use list_files_tool to find folder IDs.
    """
    result = create_file(_service, name, content, mime_type=mime_type, parent_folder_id=parent_folder_id)
    return (
        f"**Success:** Created **{result['name']}**\n"
        f"- **ID:** `{result['id']}`\n"
        f"- **Link:** {result['webViewLink']}"
    )

@_tool("Uploading File")
def upload_file_tool(local_path: str, name: str = None, parent_folder_id: str = None) -> str:
    """
    Upload a local file to Google Drive. Optionally rename it and/or place it in a
    specific folder (use list_files_tool to find folder IDs).
    """
    result = upload_file(_service, local_path, name=name, parent_folder_id=parent_folder_id)
    return (
        f"**Success:** Uploaded as **{result['name']}**\n"
        f"- **ID:** `{result['id']}`\n"
        f"- **Link:** {result['webViewLink']}"
    )


@_tool("Downloading File")
def download_file_tool(file_id: str, save_path: str) -> str:
    """
    Download a Drive file to local disk. Google Docs/Sheets/Slides are exported as PDF.
    """
    final_path = download_file(_service, file_id, save_path)
    return f"**Success:** Saved to `{final_path}`."


@_tool("Creating Folder")
def create_folder_tool(name: str, parent_folder_id: str = None) -> str:
    """
    Create a new folder in Drive, optionally nested inside a parent folder.
    """
    result = create_folder(_service, name, parent_folder_id=parent_folder_id)
    return f"**Success:** Created folder **{result['name']}** with ID `{result['id']}`."


@_tool("Moving File")
def move_file_tool(file_id: str, new_parent_folder_id: str) -> str:
    """
    Move a file into a different folder.
    """
    move_file(_service, file_id, new_parent_folder_id)
    return f"**Success:** File `{file_id}` moved to folder `{new_parent_folder_id}`."


@_tool("Copying File")
def copy_file_tool(file_id: str, new_name: str = None) -> str:
    """
    Create a copy of a file, optionally with a new name.
    """
    result = copy_file(_service, file_id, new_name=new_name)
    return f"**Success:** Copied to **{result['name']}** (`{result['id']}`)."


@_tool("Renaming File")
def rename_file_tool(file_id: str, new_name: str) -> str:
    """
    Rename an existing Drive file or folder.
    """
    result = rename_file(_service, file_id, new_name)
    return f"**Success:** Renamed to **{result['name']}**."


@_tool("Moving File to Trash")
def trash_file_tool(file_id: str) -> str:
    """
    Move a file to Trash (recoverable via untrash_file_tool).
    """
    trash_file(_service, file_id)
    return f"**Success:** File `{file_id}` moved to Trash."


@_tool("Restoring File from Trash")
def untrash_file_tool(file_id: str) -> str:
    """
    Restore a file from Trash.
    """
    untrash_file(_service, file_id)
    return f"**Success:** File `{file_id}` restored from Trash."


@_tool("Permanently Deleting File")
def permanently_delete_file_tool(file_id: str) -> str:
    """
    Permanently and irreversibly delete a file, bypassing Trash. Use with caution.
    """
    permanently_delete_file(_service, file_id)
    return f"**Success:** File `{file_id}` permanently deleted. This cannot be undone."


@_tool("Sharing File")
def share_file_tool(file_id: str, email: str, role: str = "reader") -> str:
    """
    Share a file with a specific email address. role is one of: reader, writer, commenter.
    """
    share_file(_service, file_id, email, role=role)
    return f"**Success:** Shared `{file_id}` with {email} as **{role}**."


@_tool("Listing File Permissions")
def list_permissions_tool(file_id: str) -> str:
    """
    List who has access to a file and their permission level.
    """
    perms = list_permissions(_service, file_id)
    if not perms:
        return "### Permissions\nNo permissions found (may be owner-only)."
    lines = [f"- {p.get('emailAddress', 'Unknown')} — **{p['role']}**" for p in perms]
    return f"### Permissions (Found {len(perms)})\n" + "\n".join(lines)