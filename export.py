import sys
import os
import subprocess
import json
import re
import yaml
import base64

# DRIVE UPLOAD IMPORTS
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

""" DRIVE UPLOAD STARTS HERE """
SCOPES = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = "drive_credentials.json"


def create_drive_service():
    creds = None
    # The file token.json stores the user's access and refresh tokens.
    # if os.path.exists('token.json'):
    # creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def find_file_in_folder(service, folder_id, file_name):
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    response = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    for file in response.get("files", []):
        return file.get("id")
    return None


def get_or_create_folder(service, folder_name, parent_folder_id=None):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_folder_id:
        query += f" and '{parent_folder_id}' in parents"
    query += " and trashed=false"
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    folders = results.get("files", [])
    if folders:
        return folders[0]["id"]
    else:
        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_folder_id:
            folder_metadata["parents"] = [parent_folder_id]
        folder = service.files().create(body=folder_metadata, fields="id").execute()
        return folder["id"]


def upload_or_update_file(service, folder_id, file_name, file_path):
    file_id = find_file_in_folder(service, folder_id, file_name)
    # Removed 'parents' from here for update
    file_metadata = {"name": file_name}
    media = MediaFileUpload(file_path, mimetype="application/pdf")
    if file_id:
        service.files().update(
            fileId=file_id, body=file_metadata, media_body=media
        ).execute()
    else:
        file_metadata["parents"] = [folder_id]
        service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()


def write_part(part, pdf, exports, title):
    section = get_section(part)
    export_path = f"{exports}/{section}"
    os.makedirs(export_path, exist_ok=True)
    filename = f"{title}-{re.sub(r'[ ()]', '', part)}.pdf"
    filepath = f"{export_path}/{filename}"
    with open(filepath, "wb") as file:
        file.write(base64.b64decode(pdf))


def upload_directory(service, folder_id, folder_path):
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            relative_path = os.path.relpath(root, folder_path)
            current_folder_id = folder_id
            if relative_path != ".":
                for folder_name in relative_path.split(os.sep):
                    current_folder_id = get_or_create_folder(
                        service, folder_name, current_folder_id
                    )
            upload_or_update_file(service, current_folder_id, filename, file_path)


""" DRIVE UPLOAD ENDS HERE """

sections = {
    "Strings": ["Violin", "Viola", "Violoncello", "Contrabass", "Strings"],
    "Woodwinds": [
        "Piccolo",
        "Flute",
        "Oboe",
        "English Horn",
        "Clarinet",
        "Bass Clarinet",
        "Bassoon",
        "Alto Saxophone",
        "Tenor Saxophone",
        "Baritone Saxophone",
        "Woodwinds",
    ],
    "Brass": ["French Horn", "Trumpet", "Trombone", "Euphonium", "Tuba", "Brass"],
    "Percussion": [
        "Timpani",
        "Drumset",
        "Tambourine",
        "Cymbal",
        "Cymbals",
        "Shaker",
        "Bass Drum",
        "Glockenspiel",
        "Xylophone",
        "Snare Drum",
        "Suspended Cymbal",
        "Crash Cymbal",
        "Percussion",
    ],
    "Vocals": ["Soprano", "Alto", "Tenor", "Bass", "Vocals"],
}

for section, instruments in sections.items():
    sections[section] = re.compile(
        f"^(?:{'|'.join(re.escape(instrument) for instrument in instruments)})(?: \d+|\s*\(.*\))?$"
    )


def get_section(part):
    for section, pattern in sections.items():
        if pattern.match(part):
            return section
    return "Other"


def export_parts(path):
    print(f"Exporting parts for {path}...")
    command = ["mscore", path, "--score-parts-pdf"]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = json.loads(result.stdout.decode("utf-8"))

    dir = os.path.dirname(path)
    exports = os.path.join(dir, "Exports")
    os.system(f"rm -rf {exports}")
    os.makedirs(exports)

    config_path = os.path.join(dir, "config.yaml")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r") as file:
            config = yaml.safe_load(file)
    title = config.get("title", os.path.basename(path)[:-5])

    for part, pdf in zip(output["parts"], output["partsBin"]):
        write_part(part, pdf, exports, title)

    print("Exporting score...")
    command = ["mscore", path, "-o", f"{exports}/{title}.pdf"]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    command = ["mscore", path, "-o", f"{exports}/{title}.mscz"]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    command = ["mscore", path, "-o", f"{exports}/{title}.mp3"]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    drive_folder_id = config.get("drive")
    if drive_folder_id:
        print("Uploading to Google Drive...")
        service = create_drive_service()
        upload_directory(service, drive_folder_id, exports)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python export.py <score>")
        sys.exit(1)
    path = sys.argv[1]
    export_parts(path)
