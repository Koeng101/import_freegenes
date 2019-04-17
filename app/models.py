from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy
from sqlalchemy.sql import func
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from flask import Flask, abort, request, jsonify, g, url_for, Response
import uuid

#from .config import SPACES
#from .config import BUCKET

from .config import SECRET_KEY
from itsdangerous import (TimedJSONWebSignatureSerializer
                          as Serializer, BadSignature, SignatureExpired)
from passlib.apps import custom_app_context as pwd_context

db = SQLAlchemy()
auth = HTTPBasicAuth()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), unique=True, nullable=False,default=sqlalchemy.text("uuid_generate_v4()"), primary_key=True)
    username = db.Column(db.String, index=True)
    password_hash = db.Column(db.String(150))

    def hash_password(self, password):
        self.password_hash = pwd_context.hash(password)

    def verify_password(self, password):
        return pwd_context.verify(password, self.password_hash)

    def generate_auth_token(self, expiration=600):
        s = Serializer(SECRET_KEY, expires_in=expiration)
        return s.dumps({'id': str(self.id)})

    @staticmethod
    def verify_auth_token(token):
        s = Serializer(SECRET_KEY)
        try:
            data = s.loads(token)
        except SignatureExpired:
            return None    # valid token, but expired
        except BadSignature:
            return None    # invalid token
        user = User.query.get(data['id'])
        return user

@auth.verify_password
def verify_password(username_or_token, password):
    # first try to authenticate by token
    user = User.verify_auth_token(username_or_token)
    if not user:
        # try to authenticate with username/password
        user = User.query.filter_by(username=username_or_token).first()
        if not user or not user.verify_password(password):
            return False
    g.user = user
    return True


##############
### MiaDNA ###
##############
class Files(db.Model):
    def __init__(self,name,file):
        file_name = str(uuid.uuid4())
        def upload_file_to_spaces(file,file_name=file_name,bucket_name=BUCKET,spaces=SPACES):
            """
            Docs: http://boto3.readthedocs.io/en/latest/guide/s3.html
            http://zabana.me/notes/upload-files-amazon-s3-flask.html"""
            try:
                spaces.upload_fileobj(file,bucket_name,file_name)
            except Exception as e:
                print("Failed: {}".format(e))
                return False
            return True
        if upload_file_to_spaces(file,file_name=file_name) == True:
            self.name = name
            self.file_name = file_name
    __tablename__ = 'files'
    uuid = db.Column(UUID(as_uuid=True), unique=True, nullable=False,default=sqlalchemy.text("uuid_generate_v4()"), primary_key=True)
    time_created = db.Column(db.DateTime(timezone=True), server_default=func.now())

    name = db.Column(db.String, nullable=False) # Name to be displayed to user
    file_name = db.Column(db.String, nullable=False) # Link to spaces

