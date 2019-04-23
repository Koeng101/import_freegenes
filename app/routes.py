import json
import requests
from .models import *
from flask_restplus import Api, Resource, fields, Namespace 
from flask import Flask, abort, request, jsonify, g, url_for, redirect

from .config import PREFIX
from .config import LOGIN_KEY
from .config import SPACES
from .config import BUCKET        
from .config import FG_API

import pandas as pd
import io

################
# Generic auth #
################
import os
import jwt
from functools import wraps
from flask import make_response, jsonify
PUBLIC_KEY = os.environ['PUBLIC_KEY']
def requires_auth(roles):
    def requires_auth_decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            def decode_token(token):
                return jwt.decode(token.encode("utf-8"), PUBLIC_KEY, algorithms='RS256')
            try:
                decoded = decode_token(str(request.headers['Token']))
            except Exception as e:
                post_token = False
                if request.json != None:
                    if 'token' in request.json:
                        try:
                            decoded = decode_token(request.json.get('token'))
                            post_token=True
                        except Exception as e:
                            return make_response(jsonify({'message': str(e)}),401)
                if not post_token:
                    return make_response(jsonify({'message': str(e)}), 401)
            if set(roles).isdisjoint(decoded['roles']):
                return make_response(jsonify({'message': 'Not authorized for this endpoint'}),401)
            return f(*args, **kwargs)
        return decorated
    return requires_auth_decorator
ns_token = Namespace('auth_test', description='Authorization_test')
@ns_token.route('/')
class ResourceRoute(Resource):
    @ns_token.doc('token_resource',security='token')
    @requires_auth(['user','moderator','admin'])
    def get(self):
        return jsonify({'message': 'Success'})
###


def request_to_class(dbclass,json_request):
    tags = []
    for k,v in json_request.items():
        if k == 'tags' and v != []:
            dbclass.tags = []
            for tag in v:
                tags_in_db = Tag.query.filter_by(tag=tag).all()
                if len(tags_in_db) == 0:
                    tags.append(Tag(tag=tag))
                else:
                    tags.append(tags_in_db[0])
        elif k == 'files' and v != []:
            for file_uuid in v:
                files_in_db = File.query.filter_by(uuid=file_uuid).first()
                if len(files_in_db) == 0:
                    pass
                else: 
                    dbclass.files.append(files_in_db[0])
        else:
            setattr(dbclass,k,v)
    for tag in tags:
        dbclass.tags.append(tag)
    return dbclass

def crud_get_list(cls,full=None):
    return jsonify([obj.toJSON(full=full) for obj in cls.query.all()])

def crud_post(cls,post,database):
    obj = request_to_class(cls(),post)
    database.session.add(obj)
    database.session.commit()
    return jsonify(obj.toJSON())

def crud_get(cls,uuid,full=None,jsonify_results=True):
    obj = cls.query.filter_by(uuid=uuid).first()
    if obj == None:
        return jsonify([])
    if jsonify_results == True:
        return jsonify(obj.toJSON(full=full))
    else:
        return obj

def crud_delete(cls,uuid,database):
    database.session.delete(cls.query.get(uuid))
    database.session.commit()
    return jsonify({'success':True})

def crud_put(cls,uuid,post,database):
    obj = cls.query.filter_by(uuid=uuid).first()
    updated_obj = request_to_class(obj,post)
    db.session.commit()
    return jsonify(obj.toJSON())

class CRUD():
    def __init__(self, namespace, cls, model, name, security='token'):
        self.ns = namespace
        self.cls = cls
        self.model = model
        self.name = name

        @self.ns.route('/')
        class ListRoute(Resource):
            @self.ns.doc('{}_list'.format(self.name))
            def get(self):
                return crud_get_list(cls)

            @self.ns.doc('{}_create'.format(self.name),security=security)
            @self.ns.expect(model)
            @requires_auth(['moderator','admin'])
            def post(self):
                return crud_post(cls,request.get_json(),db)

        @self.ns.route('/<uuid>')
        class NormalRoute(Resource):
            @self.ns.doc('{}_get'.format(self.name))
            def get(self,uuid):
                return crud_get(cls,uuid)

            @self.ns.doc('{}_delete'.format(self.name),security=security)
            @requires_auth(['moderator','admin'])
            def delete(self,uuid):
                return crud_delete(cls,uuid,db)

            @self.ns.doc('{}_put'.format(self.name),security=security)
            @self.ns.expect(self.model)
            @requires_auth(['moderator','admin'])
            def put(self,uuid):
                return crud_put(cls,uuid,request.get_json(),db)

        @self.ns.route('/full/')
        class FullListRoute(Resource):
            @self.ns.doc('{}_full'.format(self.name))
            def get(self):
                return crud_get_list(cls,full='full')

        @self.ns.route('/full/<uuid>')
        class FullRoute(Resource):
            @self.ns.doc('{}_full'.format(self.name))
            def get(self,uuid):
                return crud_get(cls,uuid,full='full')

#========#
# Routes #
#========#
        
ns_file = Namespace('files', description='Files')

@ns_file.route('/')
class AllFiles(Resource):
    def get(self):
        return crud_get_list(Files)

@ns_file.route('/<uuid>')
class SingleFile(Resource):
    def get(self,uuid):
        return crud_get(Files,uuid)
    @ns_file.doc('file_delete',security='token')
    @requires_auth(['moderator','admin'])
    def delete(self,uuid):
        file = Files.query.get(uuid)
        SPACES.delete_object(Bucket=BUCKET,Key=file.file_name)
        db.session.delete(file)
        db.session.commit()
        return jsonify({'success':True})

@ns_file.route('/upload')
class NewFile(Resource):
    @ns_file.doc('file_upload', security='token')
    @requires_auth(['moderator','admin'])
    def post(self):
        file_to_upload = request.files['file'].read()
        json_file = json.loads(request.files['json'].read())
        if request.headers['Token'] != None:
            token = str(request.headers['Token'])
        elif 'token' in json_file:
            token = json_file['token']
        df = pd.read_csv(io.BytesIO(file_to_upload))
        order = Order.query.filter_by(uuid=json_file['order_uuid']).first()
        if order == None:
            return jsonify({'message': 'No order found'})
        status='saved'
        if order.vendor == 'Twist':
            if json_file['plate_type'] == 'order':
                for index,row in df.iterrows():
                    r = requests.get('https://{}/parts/get/gene_id/{}'.format(FG_API,row['Name']))
                    if r.status_code == 200:
                        gene_uuid = r.json()[0]['uuid']
                        new_gene = GeneId(gene_id=row['Name'],status='ordered',order_uuid=json_file['order_uuid'],evidence='',gene_uuid=gene_uuid)
                        db.session.add(GeneId(gene_id=row['Name'],status='ordered',order_uuid=json_file['order_uuid'],evidence='',gene_uuid=gene_uuid))
            else:
                ordered = 0
                for file in order.files:
                    if file.plate_type == 'order':
                        ordered+=1
                if ordered != 1:
                    return jsonify({'message': 'Irregular number of order files: {}'.format(str(ordered))})
                if json_file['plate_type'] in ['glycerol_stock', 'dna_stock']:
                    # Handle plate
                    plate_uuid = str(uuid.uuid4())
                    if json_file['plate_type'] == 'glycerol_stock':
                        new_plate = {'token':token, 'plate_name': json_file['plate_name'], 'plate_form': 'standard96', 'plate_type': 'glycerol_stock', 'notes': 'Glycerol stock from Twist Bioscience', 'uuid': plate_uuid, 'breadcrumb':json_file['breadcrumb'], 'status': 'Stocked'}
                        new_plate = requests.post('{}/plates'.format(FG_API), json=new_plate)

                    # Iterate through rows
                    for index,row in df.iterrows():
                        geneid = GeneId.query.filter_by(gene_id=row['Name']).first()
                        if geneid == None:
                            return make_response(jsonify({'message': 'geneid not found'}),204)

                        # Handle sample
                        sample_url = '{}/samples/{}'.format(FG_API,str(geneid.sample_uuid))
                        print(sample_url)
                        sample = requests.get(sample_url).json()
                        if sample == []: 
                            new_sample = {'token':token, 'part_uuid': str(geneid.gene_uuid), 'uuid': str(geneid.sample_uuid), 'status': 'Confirmed', 'evidence': 'Twist_Confirmed'}
                            print(new_sample)
                            new_sample = requests.post('{}/samples'.format(FG_API), json=new_sample)

                        # Handle wells
                        new_well = {'token':token, 'plate_uuid':plate_uuid, 'address':row['Well Location'], 'volume': 50, 'media': 'glycerol_lb', 'well_type':'glycerol_stock'}
                        new_well = requests.post('{}/wells'.format(FG_API), json=new_well)         
        new_file = Files(json_file['name'],io.BytesIO(file_to_upload),json_file['plate_type'],json_file['order_uuid'],status, json_file['plate_name'], json_file['breadcrumb'])
        db.session.add(new_file)
        db.session.commit()
        return jsonify(new_file.toJSON())

@ns_file.route('/download/<uuid>')
class DownloadFile(Resource):
    def get(self,uuid):
        obj = Files.query.filter_by(uuid=uuid).first()
        return obj.download()

###

ns_order = Namespace('orders', description='Orders')
order_model = ns_order.model('order', {
    'name': fields.String(),
    'description': fields.String(),
    'vendor': fields.String(),
    'order_id': fields.String(),
    'quote': fields.String(),
    'price': fields.Float(),
    'status': fields.String()
    })
CRUD(ns_order,Order,order_model,'order')

###

ns_geneid = Namespace('geneid', description='GeneId')
geneid_model = ns_geneid.model('geneid', {
    'gene_id': fields.String(),
    'status': fields.String(),
    'evidence': fields.String(),
    'order_uuid': fields.String(),
    })
CRUD(ns_geneid,GeneId,geneid_model,'geneid')

###


