import uuid
from datetime import datetime
from subprocess import Popen, PIPE

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
import jwt
from pydantic import BaseModel
from starlette.responses import JSONResponse

from db.db import collection, coderunner

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# @app.get("/checkdb", response_class=HTMLResponse)
# async def db(request: Request):
#     users = collection.find()
#     return templates.TemplateResponse("testdb.html", {"request": request, "users": users})


@app.get("/", response_class=HTMLResponse)
async def home_get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# Route for handling POST request to the home page
@app.post("/", response_class=HTMLResponse)
async def home_get(request: Request):
    token = request.cookies.get("token")
    username = None
    if token:
        try:
            decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            username = decoded_token.get("username")
            print(username)
        except jwt.exceptions.DecodeError:
            pass

    return templates.TemplateResponse("index.html", {"request": request, "username": username})


# JWT configuration
JWT_SECRET_KEY = "%UO;tBrhxoU|[')"  # Replace with your secret key
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_TIME_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login", response_class=RedirectResponse)
async def login_submit(request: Request):
    form = await request.form()
    email = form.get("email")
    password = form.get("password")

    # Verify user authentication
    user = collection.find_one({"email": email})
    if user and verify_password(password, user["hashed_password"]):
        # Generate JWT token
        token = generate_jwt_token(email)
        return RedirectResponse(url="/", headers={"Set-Cookie": f"token={token}; HttpOnly"}, status_code=307)
    else:
        return RedirectResponse(url="/login?error=1")  # Redirect back to the login page with an error parameter


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def generate_jwt_token(email: str) -> str:
    username = email.split("@")[0]  # Extract the username from the email
    payload = {"email": email, "username": username}
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


def verify_jwt_token(token: str) -> bool:
    try:
        jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return True
    except:
        return False


@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/signup", response_class=RedirectResponse)
async def signup_submit(request: Request):
    form = await request.form()
    email = form.get("email")
    password = form.get("password")

    # Check if the email already exists
    existing_user = collection.find_one({"email": email})
    if existing_user:
        return RedirectResponse(url="/signup?error=1")  # Redirect back to the signup page with an error parameter

    # Hash the password
    hashed_password = hash_password(password)

    # Save the user details in the database
    user = {"email": email, "hashed_password": hashed_password}
    collection.insert_one(user)

    # Generate JWT token
    token = generate_jwt_token(email)

    return RedirectResponse(url="/", headers={"Set-Cookie": f"token={token}; HttpOnly"}, status_code=307)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


@app.get("/logout", response_class=RedirectResponse)
async def logout_get(request: Request):
    response = RedirectResponse(url="/")
    response.delete_cookie("token")  # Remove the token cookie
    return response


def get_user_id(email: str) -> str:
    user = collection.find_one({"email": email})  # Retrieve the user document from the database
    if user:
        user_id = str(user["_id"])  # Retrieve the user ID from the user document
        print(user_id)
        return user_id
    else:
        raise ValueError("User not found in the database")


class CodeRequest(BaseModel):
    code: str


@app.post("/submit-code")
async def submit_code(request: Request, code_request: CodeRequest):
    code = code_request.code
    token = request.cookies.get("token")
    if token:
        try:
            decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            email = decoded_token.get("email")
            user_id = get_user_id(email)
        except (jwt.exceptions.DecodeError, ValueError):
            return JSONResponse({"error": "Invalid token"})
    else:
        return JSONResponse({"error": "Token not found"})

    submission = {
        "submission_id": generate_submission_id(),
        "user_id": user_id,
        "code": code,
        "output": "",
        "timestamp": datetime.now()
    }
    coderunner.insert_one(submission)

    # Execute the code in a sandbox environment
    execution_result = execute_code(code)

    # Update the submission with the execution result
    coderunner.update_one(
        {"submission_id": submission["submission_id"]},
        {"$set": {"output": execution_result}}
    )

    return templates.TemplateResponse("result.html", {"request": request, "output": execution_result})


def generate_submission_id():
    return str(uuid.uuid4())


def execute_code(code: str) -> str:
    process = Popen(["python", "-c", code], stdout=PIPE, stderr=PIPE, text=True)
    stdout, stderr = process.communicate()

    if stderr:
        return f"Error: {stderr}"
    else:
        return stdout
