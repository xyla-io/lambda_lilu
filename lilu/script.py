import os
import json
import requests

from pathlib import Path
from hashlib import sha256
from cryptography.hazmat.backends import default_backend
from data_layer import locator_factory, ResourceLocator, Encryptor, Decryptor
from datetime import datetime
from typing import Optional, Dict
from enum import Enum

class Command(Enum):
  refresh_tokens = 'refresh_tokens'
  receive_code = 'receive_code'

def register_decryptors(access_credentials: Dict[str, any]):
  for name, private_key_url in access_credentials['secrets'].items():
    locator = locator_factory(url=private_key_url)
    private_key_bytes = locator.get()
    password = locator.get_locator_parameter(parameter='password')
    decryptor = Decryptor(
      private_key=private_key_bytes,
      password=password.encode(),
      name=name
    )
    Decryptor.register_decryptor(decryptor=decryptor)

def refresh_tokens():
  with open(Path(__file__).parent / 'local_access_credentials.json') as f:
    access_credentials = json.load(f)
  register_decryptors(access_credentials=access_credentials)
  credentials_locator = locator_factory(url=access_credentials['credentials_url'])
  credentials = json.loads(credentials_locator.get().decode())
  payload = {
    'app_id': credentials['app_id'],
    'secret': credentials['secret'],
    'grant_type': 'refresh_token',
    'refresh_token': credentials['refresh_token'], 
  }
  response = requests.post('https://ads.tiktok.com/open_api/oauth2/refresh_token/', json=payload)
  response_json = response.json()['data']
  refreshed_credentials = {
    **credentials,
    'refresh_token': response_json['refresh_token'],
    'access_token': response_json['access_token'],
  }
  credentials_locator.put(resource=json.dumps(refreshed_credentials, indent=2).encode())
  return response_json


class ReceiveCode:
  event: Dict[str, any]
  configuration: Dict[str, any]

  @property
  def api_key_error_response(self) -> Dict[str, any]:
    return {
      'statusCode': 401,
      'body': json.dumps({
        'code': 401,
        'message': 'Invalid API Key',
      }),
    }

  @property
  def invalid_state_error_response(self) -> Dict[str, any]:
    return {
      'statusCode': 400,
      'body': json.dumps({
        'code': 400,
        'message': 'Invalid State',
      }),
    }

  @property
  def duplicate_state_error_response(self) -> Dict[str, any]:
    return {
      'statusCode': 409,
      'body': json.dumps({
        'code': 409,
        'message': 'Duplicate State',
      }),
    }

  @property
  def invalid_code_error_response(self) -> Dict[str, any]:
    return {
      'statusCode': 400,
      'body': json.dumps({
        'code': 400,
        'message': 'Invalid Code',
      }),
    }

  @property
  def success_response(self) -> Dict[str, any]:
    return {
      'statusCode': 200,
      'body': json.dumps({
        'code': 200,
        'message': 'Code Received',
      }),
    }

  def __init__(self, event: Dict[str, any], configuration: Dict[str, any]):
    self.event = event
    self.configuration = configuration

  def verify_state_signature(self, raw_state: str, initialization_vector: str) -> bool:
    if len(raw_state) <= 64:
      return False
    state_hash = raw_state[-64:]
    state = raw_state[:-64]
    rehash = sha256()
    rehash.update(state.encode())
    rehash.update(initialization_vector.encode())
    return rehash.digest().hex() == state_hash

  def decipher_state(self, raw_state: str, cipher_key: str, initialization_vector: str) -> Dict[str, any]:
    enciphered_data = bytes.fromhex(raw_state[:-64])
    deciphered_data = Encryptor.decipher(
      data=enciphered_data,
      key=bytes.fromhex(cipher_key),
      initialization_vector=bytes.fromhex(initialization_vector),
      backend=default_backend()
    )
    deciphered_state = json.loads(deciphered_data.decode())
    return deciphered_state

  def retrieve_access_token(self, app_id: str, app_secret: str, code: str) -> Optional[Dict[str, any]]:
    payload = {
      'app_id': app_id,
      'secret': app_secret,
      'auth_code': code,
    }
    response = requests.post('https://ads.tiktok.com/open_api/oauth2/access_token_v2/', json=payload)
    response_json = response.json()['data']
    if 'access_token' not in response_json:
      return None
    return response_json

  def create_response_locator(self, name: str, store_url: str):
    store_url = ResourceLocator.dealias_url(url=store_url)
    response_url = ResourceLocator.join_path(
      url=store_url,
      path=f'{name}.json'
    )
    response_locator = locator_factory(url=response_url)
    return response_locator

  def register_encryptor(self, certificate_url: str, name: str):
    locator = locator_factory(url=certificate_url)
    public_key_bytes = locator.get()
    encryptor = Encryptor(
      public_key=public_key_bytes,
      name=name
    )
    Encryptor.register_encryptor(encryptor=encryptor)

  def run(self, credentials: Dict[str, any]):
    now = datetime.utcnow()
    if self.event['pathParameters']['api_key'] not in credentials['api_keys']:
      return self.api_key_error_response
    raw_state = self.event['queryStringParameters']['state']
    if not self.verify_state_signature(
      raw_state=raw_state,
      initialization_vector=credentials['initialization_vector']
    ):
      return self.invalid_state_error_response

    state = self.decipher_state(
      raw_state=raw_state,
      cipher_key=credentials['cipher_key'],
      initialization_vector=credentials['initialization_vector']
    )
    if state['expire'] < datetime.timestamp(now):
      return self.invalid_state_error_response
    if state['app_id'] not in credentials['app_secrets']:
      return self.invalid_state_error_response

    response_locator = self.create_response_locator(
      name=state['name'],
      store_url=credentials['store_url']
    )
    encryptor_name = response_locator.get_locator_parameter('encrypt')
    self.register_encryptor(
      certificate_url=credentials['encryptors'][encryptor_name],
      name=encryptor_name
    )

    response = self.retrieve_access_token(
      app_id=state['app_id'],
      app_secret=credentials['app_secrets'][state['app_id']],
      code=self.event['queryStringParameters']['auth_code']
    )
    if response is None:
      return self.invalid_code_error_response
    store_locator = locator_factory(url=credentials['store_url'])
    store_list = store_locator.list()
    if store_list and f'{state["name"]}.json' in store_list:
      return self.duplicate_state_error_response
    response_locator.put(resource=json.dumps(response).encode())

    return self.success_response

def run(event: any, context: any):
  os.chdir(str(Path(__file__).parent))
  with open(Path(__file__).parent / 'local_configuration.json') as f:
    configuration = json.load(f)
  command = Command(configuration['command'])
  if command is Command.refresh_tokens:
    return refresh_tokens()
  elif command is Command.receive_code:
    with open(Path(__file__).parent / 'local_access_credentials.json') as f:
      credentials = json.load(f)
    return ReceiveCode(
      event=event,
      configuration=configuration
    ).run(credentials=credentials)
