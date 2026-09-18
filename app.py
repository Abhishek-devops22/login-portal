import hashlib
import os
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash, session
from flask_mail import Mail, Message
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from models import User, db
from forms import RegisterForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    raise RuntimeError(
        'SECRET_KEY is not set. Copy .env.example to .env and fill in a random value '
        '(e.g. `python -c "import secrets; print(secrets.token_hex(32))"`).'
    )

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///job_portal.db'
db.init_app(app)

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', '')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])
mail = Mail(app)

reset_serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
RESET_TOKEN_SALT = 'password-reset'
RESET_TOKEN_MAX_AGE = 3600  # 1 hour

@app.after_request
def add_no_cache_headers(response):
    # Prevents the browser (and its back-forward cache) from replaying
    # authenticated pages like /home after logout without hitting the server.
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response

DUMMY_JOBS = [
    {
        'title': 'Frontend Developer',
        'company': 'Acme Corp',
        'location': 'Remote',
        'description': 'Build delightful user interfaces with React and TypeScript.',
    },
    {
        'title': 'Backend Engineer',
        'company': 'Globex Inc',
        'location': 'Bangalore, India',
        'description': 'Design and scale APIs powering millions of requests a day.',
    },
    {
        'title': 'Data Analyst',
        'company': 'Initech',
        'location': 'New York, NY',
        'description': 'Turn raw data into insights that drive product decisions.',
    },
    {
        'title': 'Product Designer',
        'company': 'Umbrella Co',
        'location': 'Berlin, Germany',
        'description': 'Craft intuitive experiences from concept to launch.',
    },
]

@app.route('/')
def index():
    if session.get('username'):
        return redirect(url_for('home'))
    form = LoginForm()
    return render_template('login.html', form=form)

@app.route('/home')
def home():
    if not session.get('username'):
        return redirect(url_for('index'))
    user = User.query.filter_by(email=session['username']).first()
    return render_template('home.html', user=user, jobs=DUMMY_JOBS)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash('An account with that email already exists')
            return render_template('register.html', form=form)
        user = User(email=form.email.data, name=form.name.data, mobile_number=form.mobile_number.data, password=generate_password_hash(form.password.data), city=form.city.data, country=form.country.data)
        db.session.add(user)
        db.session.commit()
        flash('User Created')
        return redirect(url_for('index'))
    return render_template('register.html', form=form)

@app.route('/sign_in', methods=['GET', 'POST'])
def sign_in():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password, form.password.data):
            session['username'] = user.email
            flash('Logged In')
            return redirect(url_for('home'))
        flash('Invalid email or password')
    return render_template('login.html', form=form)

def reset_fingerprint(user):
    # Derived from the current password hash, so it changes the moment the
    # password is reset - any token issued before that stops matching,
    # making every reset link single-use without a separate "used" column.
    raw = f'{user.password}{app.config["SECRET_KEY"]}'.encode()
    return hashlib.sha256(raw).hexdigest()

def send_reset_email(user):
    token = reset_serializer.dumps(
        {'email': user.email, 'fp': reset_fingerprint(user)},
        salt=RESET_TOKEN_SALT,
    )
    reset_url = url_for('reset_password', token=token, _external=True)
    if app.config['MAIL_SERVER']:
        message = Message('Reset your Job Portal password', recipients=[user.email])
        message.body = (
            f'Click the link below to reset your password:\n{reset_url}\n\n'
            'This link expires in 1 hour. If you did not request this, ignore this email.'
        )
        mail.send(message)
    else:
        # No SMTP configured: log the link instead of emailing it, so the
        # flow is still testable locally without real mail credentials.
        app.logger.info('Password reset link for %s: %s', user.email, reset_url)
    return reset_url

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if session.get('username'):
        return redirect(url_for('home'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            reset_url = send_reset_email(user)
            if not app.config['MAIL_SERVER']:
                flash(f'MAIL_SERVER not configured; reset link (dev only): {reset_url}')
        # Same message whether or not the email exists, so this endpoint
        # can't be used to discover which emails are registered.
        flash('If that email is registered, a password reset link has been sent.')
        return redirect(url_for('index'))
    return render_template('forgot_password.html', form=form)

RESET_LINK_EXPIRED_MESSAGE = 'This reset link has expired. Please request a new one from the Forgot Password page.'

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if session.get('username'):
        return redirect(url_for('home'))
    try:
        payload = reset_serializer.loads(token, salt=RESET_TOKEN_SALT, max_age=RESET_TOKEN_MAX_AGE)
        email = payload['email']
        fingerprint = payload['fp']
    except SignatureExpired:
        flash(RESET_LINK_EXPIRED_MESSAGE)
        return redirect(url_for('forgot_password'))
    except (BadSignature, TypeError, KeyError):
        # Covers a malformed token, or one issued before the payload shape
        # changed (old links only signed a bare email string).
        flash(RESET_LINK_EXPIRED_MESSAGE)
        return redirect(url_for('forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user or fingerprint != reset_fingerprint(user):
        flash(RESET_LINK_EXPIRED_MESSAGE)
        return redirect(url_for('forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = generate_password_hash(form.password.data)
        db.session.commit()
        flash('Your password has been updated. Please log in.')
        return redirect(url_for('index'))
    return render_template('reset_password.html', form=form)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
