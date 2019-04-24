from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy
from sqlalchemy.sql import func
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from flask import Flask, abort, request, jsonify, g, url_for, Response
import uuid


from .config import SPACES
from .config import BUCKET

from itsdangerous import (TimedJSONWebSignatureSerializer
                          as Serializer, BadSignature, SignatureExpired)
from passlib.apps import custom_app_context as pwd_context

db = SQLAlchemy()
auth = HTTPBasicAuth()

#################
### FG import ###
#################
def get_total_bytes(s3, key):
    result = s3.list_objects(Bucket=BUCKET)
    for item in result['Contents']:
        if item['Key'] == key:
            return item['Size']

def get_object(s3, total_bytes,key):
    if total_bytes > 1000000:
        return get_object_range(s3, total_bytes, key)
    return s3.get_object(Bucket=BUCKET, Key=key)['Body'].read()

def get_object_range(s3, total_bytes, key):
    offset = 0
    while total_bytes > 0:
        end = offset + 999999 if total_bytes > 1000000 else ""
        total_bytes -= 1000000
        byte_range = 'bytes={offset}-{end}'.format(offset=offset, end=end)
        offset = end + 1 if not isinstance(end, str) else None
        yield s3.get_object(Bucket=BUCKET, Key=key, Range=byte_range)['Body'].read()

class Files(db.Model):
    def __init__(self,name,file,plate_type,order_uuid,status,plate_name,breadcrumb,plate_vendor_id):
        print(name)
        file_name = str(uuid.uuid4())
        def upload_file_to_spaces(file,file_name=file_name,bucket_name=BUCKET,spaces=SPACES):
            """
            Docs: http://boto3.readthedocs.io/en/latest/guide/s3.html
            http://zabana.me/notes/upload-files-amazon-s3-flask.html"""
            try:
                print('Attempting')
                spaces.upload_fileobj(file,bucket_name,file_name)
                print('Uploaded')
            except Exception as e:
                print("Failed: {}".format(e))
                return False
            return True
        if upload_file_to_spaces(file,file_name=file_name) == True:
            self.name = name
            self.file_name = file_name
            self.plate_type = plate_type
            self.order_uuid = order_uuid
            self.status = status
            self.breadcrumb = breadcrumb
            self.plate_name = plate_name
            self.plate_vendor_id = plate_vendor_id
            # Also include plate_name in json_file if uploading a glycerol stock or dna stock
    __tablename__ = 'files'
    uuid = db.Column(UUID(as_uuid=True), unique=True, nullable=False,default=sqlalchemy.text("uuid_generate_v4()"), primary_key=True)
    time_created = db.Column(db.DateTime(timezone=True), server_default=func.now())

    name = db.Column(db.String, nullable=False) # Name to be displayed to user
    file_name = db.Column(db.String, nullable=False) # Link to spaces
    plate_type = db.Column(db.String) # Plate type? 
    order_uuid = db.Column(UUID, db.ForeignKey('orders.uuid'), nullable=False)
    status = db.Column(db.String)
    breadcrumb = db.Column(db.String)
    plate_name = db.Column(db.String)
    plate_vendor_id = db.Column(db.String)
    
    def toJSON(self,full=None):
        return {'uuid':self.uuid,'name':self.name,'file_name':self.file_name,'plate_type':self.plate_type,'order_uuid':self.order_uuid,'breadcrumb':self.breadcrumb,'plate_name':self.plate_name,'status':self.status,'plate_vendor_id':self.plate_vendor_id}
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
    gene_uuid = db.Column(db.String)
    status = db.Column(db.String)
    evidence = db.Column(db.String)
    order_uuid = db.Column(UUID, db.ForeignKey('orders.uuid'), nullable=False)

    def toJSON(self,full=None):
        dictionary = {'uuid':self.uuid, 'sample_uuid':self.sample_uuid, 'gene_id':self.gene_id, 'gene_uuid':self.gene_uuid, 'status':self.status, 'evidence':self.evidence, 'order_uuid':self.order_uuid}
        return dictionary


