from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class RegisterForm(FlaskForm):
    name = StringField('Name', id='name', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email', id='email', validators=[DataRequired(), Email(), Length(max=100)])
    mobile_number = StringField('Mobile Number', id='mobile_number', validators=[DataRequired(), Length(min=7, max=20)])
    password = PasswordField('Password', id='password', validators=[DataRequired(), Length(min=6)])
    city = StringField('City', id='city', validators=[DataRequired(), Length(max=50)])
    country = StringField('Country', id='country', validators=[DataRequired(), Length(max=50)])


class LoginForm(FlaskForm):
    email = StringField('Email', id='email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', id='password', validators=[DataRequired()])


class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', id='email', validators=[DataRequired(), Email()])


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', id='password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField(
        'Confirm Password',
        id='confirm_password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match.')],
    )
