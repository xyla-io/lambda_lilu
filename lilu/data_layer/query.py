from .base import run_query
from .sql_query import SQLQuery
from typing import Iterable, Tuple, Optional
from s3_layer import S3

class Query(SQLQuery):
  def __init__(self, query: str, parameters: Iterable[any]=[]):
    super().__init__(query=query, substitution_parameters=tuple(parameters))

  @property
  def parameters(self) -> Tuple[any]:
    return self.substitution_parameters

  @parameters.setter
  def parameters(self, parameters: Iterable[any]):
    self.substitution_parameters = tuple(parameters)

  def run(self, connection: any) -> any:
    return run_query(
      connection=connection,
      query=self.query,
      parameters=self.parameters
    )

class UnloadQuery(Query):
  bucket: str
  key: str
  access_key_id: str
  secret_access_key: str

  def __init__(self, select_query: Query, access_key_id: str, secret_access_key, bucket: str, key: str):
    self.bucket = bucket
    self.key = key
    self.access_key_id = access_key_id
    self.secret_access_key = secret_access_key
    access_query = Query(
      query = f'access_key_id %s secret_access_key %s',
      parameters=[self.access_key_id, self.secret_access_key]
    )
    unload_query = Query(
      query = f'''
unload (%s)
to %s
{access_query.query}
parallel off
format as csv
allowoverwrite
header;
    ''',
      parameters=[
        select_query.substituted_query,
        f's3://{self.bucket}/{self.key}',
        *access_query.parameters
      ]
    )
    super().__init__(query=unload_query.substituted_query)

  def unload(self, connection: any, bucket: Optional[str]=None, key: Optional[str]=None):
    if bucket is None:
      bucket = self.bucket
    if key is None:
      key = self.key

    cursor = self.run(connection=connection)
    cursor.close()
    s3 = S3(
      access_key_id=self.access_key_id,
      secret_access_key=self.secret_access_key
    )
    unload_key = f'{self.key}000'
    s3.move_object(
      existing_bucket=self.bucket,
      existing_key=unload_key,
      new_bucket=bucket,
      new_key=key,
      metadata={
        'content-type': 'text/csv',
      }
    )
    return f'https://{bucket}.s3.amazonaws.com/{key}'
