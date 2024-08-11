from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from lollms_webui import LOLLMSWebUI
from pydantic import BaseModel
from pathlib import Path
import shutil
import uuid
import os
import requests
import yaml
from lollms.security import check_access, sanitize_path
import os
import subprocess
import yaml
import uuid
import platform
from ascii_colors import ASCIIColors, trace_exception
import pipmaster as pm
if not pm.is_installed("httpx"):
    pm.install("httpx")
import httpx
from lollms.utilities import PackageManager

# Pull the repository if it already exists
def check_lollms_models_zoo():
    if not PackageManager.check_package_installed("zipfile"):
        PackageManager.install_or_update("zipfile36")
ASCIIColors.execute_with_animation("Checking zip library.", check_lollms_models_zoo)


from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import zipfile
import io

router = APIRouter()
lollmsElfServer: LOLLMSWebUI = LOLLMSWebUI.get_instance()

class AuthRequest(BaseModel):
    client_id: str

class AppInfo:
    def __init__(self, uid: str, name: str, folder_name: str, icon: str, category:str, description: str, author:str, version:str, model_name:str, disclaimer:str, installed: bool):
        self.uid = uid
        self.name = name
        self.folder_name = folder_name
        self.icon = icon
        self.category = category
        self.description = description
        self.author = author
        self.version = version
        self.model_name = model_name
        self.disclaimer = disclaimer
        self.installed = installed

@router.get("/apps")
async def list_apps():
    apps = []
    apps_zoo_path = lollmsElfServer.lollms_paths.apps_zoo_path
    
    for app_name in apps_zoo_path.iterdir():
        if app_name.is_dir():
            icon_path = app_name / "icon.png"
            description_path = app_name / "description.yaml"
            description = ""
            author = ""
            version = ""
            model_name = ""
            disclaimer = ""
            
            if description_path.exists():
                with open(description_path, 'r') as file:
                    data = yaml.safe_load(file)
                    application_name = data.get('name', app_name.name)
                    category = data.get('category', 'generic')
                    description = data.get('description', '')
                    author = data.get('author', '')
                    version = data.get('version', '')
                    model_name = data.get('model_name', '')
                    disclaimer = data.get('disclaimer', 'No disclaimer provided.')
                    installed = True
            else:
                installed = False
                    
            if icon_path.exists():
                uid = str(uuid.uuid4())
                apps.append(AppInfo(
                    uid=uid,
                    name=application_name,
                    folder_name = app_name.name,
                    icon=f"/apps/{app_name.name}/icon.png",
                    category=category,
                    description=description,
                    author=author,
                    version=version,
                    model_name=model_name,
                    disclaimer=disclaimer,
                    installed=installed
                ))
    
    return apps


class ShowAppsFolderRequest(BaseModel):
    client_id: str = Field(...)

@router.post("/show_apps_folder")
async def open_folder_in_vscode(request: ShowAppsFolderRequest):
    check_access(lollmsElfServer, request.client_id)
    # Get the current operating system
    current_os = platform.system()

    try:
        if current_os == "Windows":
            # For Windows
            subprocess.run(['explorer', lollmsElfServer.lollms_paths.apps_zoo_path])
        elif current_os == "Darwin":
            # For macOS
            subprocess.run(['open', lollmsElfServer.lollms_paths.apps_zoo_path])
        elif current_os == "Linux":
            # For Linux
            subprocess.run(['xdg-open', lollmsElfServer.lollms_paths.apps_zoo_path])
        else:
            print("Unsupported operating system.")
    except Exception as e:
        print(f"An error occurred: {e}")

class OpenFolderRequest(BaseModel):
    client_id: str = Field(...)
    app_name: str = Field(...)

@router.post("/open_app_in_vscode")
async def open_folder_in_vscode(request: OpenFolderRequest):
    check_access(lollmsElfServer, request.client_id)
    sanitize_path(request.app_name)
    # Construct the folder path
    folder_path = lollmsElfServer.lollms_paths.apps_zoo_path/ request.app_name

    # Check if the folder exists
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    # Open the folder in VSCode
    try:
        os.system(f'code -n "{folder_path}"')  # This assumes 'code' is in the PATH
        return {"message": f"Opened {folder_path} in VSCode."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {str(e)}")


@router.get("/apps/{app_name}/{file}")
async def get_app_file(app_name: str, file: str):
    file=sanitize_path(file)
    app_path = lollmsElfServer.lollms_paths.apps_zoo_path / app_name / file
    if not app_path.exists():
        raise HTTPException(status_code=404, detail="App file not found")
    return FileResponse(app_path)

class AppNameInput(BaseModel):
    client_id: str
    app_name: str


@router.post("/download_app")
async def download_app(input_data: AppNameInput):
    check_access(lollmsElfServer, input_data.client_id)
    app_name = sanitize_path(input_data.app_name)
    app_path = lollmsElfServer.lollms_paths.apps_zoo_path / app_name

    if not app_path.exists():
        raise HTTPException(status_code=404, detail="App not found")

    # Create a BytesIO object to store the zip file
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file in app_path.rglob('*'):
            if file.is_file() and '.git' not in file.parts:
                relative_path = file.relative_to(app_path)
                zip_file.write(file, arcname=relative_path)

    # Seek to the beginning of the BytesIO object
    zip_buffer.seek(0)

    # Create a StreamingResponse to return the zip file
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={app_name}.zip"}
    )

import os
import yaml
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import zipfile
import shutil

@router.post("/upload_app")
async def upload_app(client_id: str, file: UploadFile = File(...)):
    check_access(lollmsElfServer, client_id)
    
    # Create a temporary directory to extract the zip file
    temp_dir = lollmsElfServer.lollms_paths.personal_path / "temp"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # Save the uploaded file temporarily
        temp_file = temp_dir / file.filename
        with open(temp_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Extract the zip file
        with zipfile.ZipFile(temp_file, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        # Check for required files
        required_files = ['index.html', 'description.yaml', 'icon.png']
        for required_file in required_files:
            if not os.path.exists(os.path.join(temp_dir, required_file)):
                raise HTTPException(status_code=400, detail=f"Missing required file: {required_file}")

        # Read the description.yaml file
        with open(os.path.join(temp_dir, 'description.yaml'), 'r') as yaml_file:
            description = yaml.safe_load(yaml_file)

        # Get the app name from the description
        app_name = description.get('name')
        if not app_name:
            raise HTTPException(status_code=400, detail="App name not found in description.yaml")

        # Create the app directory
        app_dir = lollmsElfServer.lollms_paths.apps_zoo_path / app_name
        if os.path.exists(app_dir):
            raise HTTPException(status_code=400, detail="An app with this name already exists")

        # Move the extracted files to the app directory
        shutil.move(temp_dir, app_dir)

        return JSONResponse(content={"message": f"App '{app_name}' uploaded successfully"}, status_code=200)

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip file")
    except yaml.YAMLError:
        raise HTTPException(status_code=400, detail="Invalid YAML in description.yaml")
    finally:
        # Clean up temporary files
        if os.path.exists(temp_file):
            os.remove(temp_file)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


@router.post("/install/{app_name}")
async def install_app(app_name: str, auth: AuthRequest):
    check_access(lollmsElfServer, auth.client_id)
    REPO_DIR = lollmsElfServer.lollms_paths.personal_path/"apps_zoo_repo"
    
    # Create the app directory
    app_path = lollmsElfServer.lollms_paths.apps_zoo_path/app_name  # Adjust the path as needed
    os.makedirs(app_path, exist_ok=True)

    # Define the local paths for the files to copy
    files_to_copy = {
        "icon.png":         REPO_DIR/app_name/"icon.png",
        "description.yaml": REPO_DIR/app_name/"description.yaml",
        "index.html":       REPO_DIR/app_name/"index.html"
    }

    # Copy each file from the local repo
    for file_name, local_path in files_to_copy.items():
        if local_path.exists():
            with open(local_path, 'rb') as src_file:
                with open(app_path/file_name, 'wb') as dest_file:
                    dest_file.write(src_file.read())
        else:
            raise HTTPException(status_code=404, detail=f"{file_name} not found in the local repository")

    return {"message": f"App {app_name} installed successfully."}

@router.post("/uninstall/{app_name}")
async def uninstall_app(app_name: str, auth: AuthRequest):
    app_path = lollmsElfServer.lollms_paths.apps_zoo_path / app_name
    if app_path.exists():
        shutil.rmtree(app_path)
        return {"message": f"App {app_name} uninstalled successfully."}
    else:
        raise HTTPException(status_code=404, detail="App not found")
    

REPO_URL = "https://github.com/ParisNeo/lollms_apps_zoo.git"

class ProxyRequest(BaseModel):
    url: str

@router.post("/api/proxy")
async def proxy(request: ProxyRequest):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(request.url)
            return {"content": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
def clone_repo():
    REPO_DIR = Path(lollmsElfServer.lollms_paths.personal_path) / "apps_zoo_repo"
    
    # Check if the directory exists and if it is empty
    if REPO_DIR.exists():
        if any(REPO_DIR.iterdir()):  # Check if the directory is not empty
            print(f"Directory {REPO_DIR} is not empty. Aborting clone.")
            return
    else:
        REPO_DIR.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist

    # Clone the repository
    subprocess.run(["git", "clone", REPO_URL, str(REPO_DIR)], check=True)
    print(f"Repository cloned into {REPO_DIR}")

def pull_repo():
    REPO_DIR = lollmsElfServer.lollms_paths.personal_path/"apps_zoo_repo"
    subprocess.run(["git", "-C", str(REPO_DIR), "pull"], check=True)

def load_apps_data():
    apps = []
    REPO_DIR = lollmsElfServer.lollms_paths.personal_path/"apps_zoo_repo"
    for item in os.listdir(REPO_DIR):
        item_path = os.path.join(REPO_DIR, item)
        if os.path.isdir(item_path):
            description_path = os.path.join(item_path, "description.yaml")
            icon_url = f"https://github.com/ParisNeo/lollms_apps_zoo/blob/main/{item}/icon.png?raw=true"
            
            if os.path.exists(description_path):
                with open(description_path, 'r') as file:
                    description_data = yaml.safe_load(file)
                    apps.append(AppInfo(
                        uid=str(uuid.uuid4()),
                        name=description_data.get("name",item),
                        folder_name=item,
                        icon=icon_url,
                        category=description_data.get('category', 'generic'),
                        description=description_data.get('description', ''),
                        author=description_data.get('author', ''),
                        version=description_data.get('version', ''),
                        model_name=description_data.get('model_name', ''),
                        disclaimer=description_data.get('disclaimer', 'No disclaimer provided.'),
                        installed=True
                    ))
    return apps

@router.get("/lollms_assets/{asset_type}/{file_name}", response_class=PlainTextResponse)
async def lollms_assets(asset_type: str, file_name: str):
    # Define the base path
    base_path = Path(__file__).parent

    # Determine the correct directory based on asset_type
    if asset_type == "js":
        directory = base_path / "libraries"
        file_extension = ".js"
    elif asset_type == "css":
        directory = base_path / "styles"
        file_extension = ".css"
    else:
        raise HTTPException(status_code=400, detail="Invalid asset type")

    # Sanitize the file name to prevent path traversal
    safe_file_name = sanitize_path(file_name)

    # Construct the full file path
    file_path = directory / f"{safe_file_name}{file_extension}"

    # Check if the file exists and is within the allowed directory
    if not file_path.is_file() or not file_path.is_relative_to(directory):
        raise HTTPException(status_code=404, detail="File not found")

    # Read and return the file content
    try:
        with file_path.open('r') as file:
            content = file.read()
        return content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


@router.get("/template")
async def lollms_js():
    return {
        "start_header_id_template": lollmsElfServer.config.start_header_id_template,
        "end_header_id_template": lollmsElfServer.config.end_header_id_template,
        "separator_template": lollmsElfServer.config.separator_template,
        "start_user_header_id_template": lollmsElfServer.config.start_user_header_id_template,
        "end_user_header_id_template": lollmsElfServer.config.end_user_header_id_template,
        "end_user_message_id_template": lollmsElfServer.config.end_user_message_id_template,
        "start_ai_header_id_template": lollmsElfServer.config.start_ai_header_id_template,
        "end_ai_header_id_template": lollmsElfServer.config.end_ai_header_id_template,
        "end_ai_message_id_template": lollmsElfServer.config.end_ai_message_id_template,
        "system_message_template": lollmsElfServer.config.system_message_template
    }

@router.get("/github/apps")
async def fetch_github_apps():
    try:
        clone_repo()
        pull_repo()
    except:
        ASCIIColors.error("Couldn't interact with ")
        lollmsElfServer.error("Couldn't interact with github.\nPlease verify your internet connection")
    apps = load_apps_data()
    return {"apps": apps}

@router.get("/apps/{app_name}/icon")
async def get_app_icon(app_name: str):
    icon_path = lollmsElfServer.lollms_paths.apps_zoo_path / app_name / "icon.png"
    if not icon_path.exists():
        raise HTTPException(status_code=404, detail="Icon not found")
    return FileResponse(icon_path)
