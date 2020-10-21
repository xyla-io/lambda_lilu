import pg8000
from typing import Iterable, Union, Dict, Optional

def get_connection(database: str, host: str, port: int, user: str, password: str, ssl: Union[Dict[str, any], bool]=True) -> any:
  connection = pg8000.connect(database=database, host=host, port=port, user=user, password=password, ssl=ssl)
  return connection

def run_query(connection: any, query: str, parameters: Iterable[str]=[]) -> any:
  cursor = connection.cursor()
  cursor.execute(query, tuple(parameters))
  return cursor