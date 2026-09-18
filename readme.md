Job Portal Login Application

## Application Workflow

```mermaid
flowchart TD
    Start([Visit "/"]) --> LoggedIn{Session has username?}
    LoggedIn -- Yes --> Home[/Home: browse jobs/]
    LoggedIn -- No --> Login[Login page]

    Login -- New user --> Register[Register page]
    Register -- Submit valid form --> RegCheck{Email already exists?}
    RegCheck -- Yes --> Register
    RegCheck -- No --> CreateUser[Create user in DB] --> Login

    Login -- Submit credentials --> AuthCheck{Email + password match?}
    AuthCheck -- No --> Login
    AuthCheck -- Yes --> SetSession[Set session username] --> Home

    Login -- Forgot password --> Forgot[Forgot Password page]
    Forgot -- Submit email --> LookupUser{Email registered?}
    LookupUser -- Yes --> SendMail[Generate signed token & email/log reset link]
    LookupUser -- No --> SameMsg[Show same generic message]
    SendMail --> SameMsg --> Login

    SendMail -.-> ResetLink[User opens reset link]
    ResetLink --> TokenCheck{Token valid & not expired?}
    TokenCheck -- No --> Forgot
    TokenCheck -- Yes --> ResetForm[Reset Password page]
    ResetForm -- Submit new password --> UpdatePw[Update password hash in DB] --> Login

    Home -- Logout --> Logout[Clear session] --> Login
```

Project Structure:


job_portal/
app.py
models.py
routes.py
templates/
base.html
login.html
register.html
forgot_password.html
templates_static/
static/
css/
style.css
js/
script.js
requirements.txt
venv


Step 1: Create a new virtual environment



Run the following command to create a new venv (virtual environment):
python -m venv


Step 2: Activate the virtual environment



Run the following command to activate the venv:
venv\Scripts\activate


Step 3: Install the required packages



Run the following command to install the required packages:
pip install -r requirements.txt


Step 4: Run the application



Run the following command to run the application:
python app.py


Step 5: Access the application



Access the application at http://localhost:5000/


Step 6: Create a new user



Go to http://localhost:5000/register to create a new user.

Fill in the registration form with your details.

Click on the "Register" button to create a new user.


Step 7: Log in



Go to http://localhost:5000/sign_in to log in with your email and password.

Fill in the email and password fields.

Click on the "Sign In" button to log in.


Step 8: Forgot Password



Go to http://localhost:5000/forgot_password to reset your password.

Fill in your email address.

Click on the "Reset Password" button to reset your password.


Step 9: Logout



Go to http://localhost:5000/logout to log out.


Step 10: Run the application in debug mode



Run the following command to run the application in debug mode:
python app.py debug


Step 11: Add a new job



Go to http://localhost:5000/jobs to add a new job.

Fill in the job details.

Click on the "Add Job" button to add a new job.


Requirements:



Python 3.8+

Flask

Flask-WTF

Flask-WTF Debug

Flask-Mail

Flask-SQLAlchemy

Flask-SQLAlchemy Debug


Features:



User Registration and Login

Forgot Password

Job Portal

Add and Delete Jobs


Note:



Make sure to replace the app.py and models.py files with your own code.

You can customize the application as per your requirements.

You can add more features and functionality as per your needs.

Make sure to run the application in the correct environment (development, production, etc.)

Make sure to handle errors and exceptions properly.

Make sure to test the application thoroughly.