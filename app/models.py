from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy
from sqlalchemy.sql import func
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from flask import Flask, abort, request, jsonify, g, url_for, Response
import uuid

from .config import SPACES
from .config import BUCKET

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


#################
### FG import ###
#################
class Files(db.Model):
    def __init__(self,name,file,plate_type,order_uuid):
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
            self.plate_type = plate_type
            self.order_uuid = order_uuid
    __tablename__ = 'files'
    uuid = db.Column(UUID(as_uuid=True), unique=True, nullable=False,default=sqlalchemy.text("uuid_generate_v4()"), primary_key=True)
    time_created = db.Column(db.DateTime(timezone=True), server_default=func.now())

    name = db.Column(db.String, nullable=False) # Name to be displayed to user
    file_name = db.Column(db.String, nullable=False) # Link to spaces
    plate_type = db.Column(db.String) # Plate type? 
    order_uuid = db.Column(UUID, db.ForeignKey('orders.uuid'), nullable=False)
    
    def toJSON(self,full=None):
        return {'uuid':self.uuid,'name':self.name,'file_name':self.file_name,'plate_type':self.plate_type,'order_uuid':self.order_uuid}
    def download(self):
        s3 = SPACES
        key = self.file_name
        total_bytes = get_total_bytes(s3,key)
        return Response(
            get_object(s3, total_bytes, key),
            mimetype='text/plain',
            headers={"Content-Disposition": "attachment;filename={}".format(self.name)})

    
class Order(db.Model):
    __tablename__ = 'orders'
    uuid = db.Column(UUID(as_uuid=True), unique=True, nullable=False,default=sqlalchemy.text("uuid_generate_v4()"), primary_key=True)
    time_created = db.Column(db.DateTime(timezone=True), server_default=func.now())
    time_updated = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    name = db.Column(db.String)
    description = db.Column(db.String)

    vendor = db.Column(db.String)
    order_id = db.Column(db.String)
    quote = db.Column(db.String)
    price = db.Column(db.Float)
    status = db.Column(db.String)
    

    files = db.relationship('Files',backref='order')
    geneids = db.relationship('GeneId',backref='order')

    def toJSON(self,full=None):
        dictionary = {'uuid':self.uuid, 'name':self.name, 'description':self.description, 'vendor':self.vendor, 'order_id':self.order_id, 'quote':self.quote, 'status':self.status}
        if full=='full':
            dictionary['files'] = [file.uuid for file in self.files]
            dictionary['geneids'] = [geneid.uuid for geneid in self.geneids]
        return dictionary

class GeneId(db.Model):
    __tablename__ = 'geneids'
    uuid = db.Column(UUID(as_uuid=True), unique=True, nullable=False,default=sqlalchemy.text("uuid_generate_v4()"), primary_key=True)
    time_created = db.Column(db.DateTime(timezone=True), server_default=func.now())
    time_updated = db.Column(db.DateTime(timezone=True), onupdate=func.now())
    sample_uuid = db.Column(UUID(as_uuid=True), unique=True, nullable=False,default=sqlalchemy.text("uuid_generate_v4()"))

    gene_id = db.Column(db.String)
    status = db.Column(db.String)
    evidence = db.Column(db.String)
    order_uuid = db.Column(UUID, db.ForeignKey('orders.uuid'), nullable=False)

    def toJSON(self,full=None):
        dictionary = {'uuid':self.uuid, 'sample_uuid':self.sample_uuid, 'gene_id':self.gene_id, 'status':self.status, 'evidence':self.evidence, 'order_uuid':order_uuid}
        return dictionary


