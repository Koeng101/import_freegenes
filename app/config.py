import boto3
import os
SECRET_KEY = os.environ['SECRET_KEY']
URL = os.environ['URL']
DEV = os.environ['DEV']
LOGIN_KEY = os.environ['LOGIN_KEY']
PREFIX = os.environ['PREFIX'] # BBF10K_

FG_API = os.environ['FG_API']
session = boto3.session.Session()
SPACES = session.client('s3',
                        region_name=os.environ['REGION_NAME'],
                        endpoint_url=os.environ['ENDPOINT_URL'],
                        aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
                        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])
BUCKET = os.environ['BUCKET']

API_TITLE = os.environ['API_TITLE']
API_DESCRIPTION = os.environ['API_DESCRIPTION']

