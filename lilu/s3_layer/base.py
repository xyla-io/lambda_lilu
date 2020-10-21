import boto3

from typing import Optional, Dict

class S3:
  access_key_id: str
  secret_access_key: str

  def __init__(self, access_key_id: str, secret_access_key: str):
    self.access_key_id = access_key_id
    self.secret_access_key = secret_access_key
    
  def move_object(self, existing_bucket: str, existing_key: str, new_bucket: Optional[str], new_key: Optional[str], metadata: Optional[Dict[str, str]]):
    if new_bucket is None:
      new_bucket = existing_bucket
    if new_key is None:
      new_key = existing_key

    s3_resource = boto3.resource(
      's3',
      aws_access_key_id=self.access_key_id,
      aws_secret_access_key=self.secret_access_key
    )
    s3_object = s3_resource.Object(new_bucket, new_key)
    metadata_args = {}
    if metadata is not None:
      remaining_metadata = {**metadata}
      if 'content-type' in remaining_metadata:
        metadata_args['ContentType'] = remaining_metadata['content-type']
        del remaining_metadata['content-type']
      if 'content-encoding' in remaining_metadata:
        metadata_args['ContentEncoding'] = remaining_metadata['content-encoding']
        del remaining_metadata['content-encoding']
      if remaining_metadata:
        metadata_args['Metadata'] = remaining_metadata
      metadata_args['MetadataDirective'] = 'REPLACE'
    s3_object.copy_from(
      CopySource={'Bucket': existing_bucket, 'Key': existing_key},
      **metadata_args
    )
    if new_key != existing_key:
      s3_client = boto3.client(
        's3',
        aws_access_key_id=self.access_key_id,
        aws_secret_access_key=self.secret_access_key
      )
      s3_client.delete_object(Bucket=existing_bucket, Key=existing_key)
