from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from atlas.api import create_app
from atlas.config import Settings


@pytest.fixture
def client(tmp_path):
    config = Settings(_env_file=None, database_url='sqlite:///'+str(tmp_path/'test.db'),
        chroma_path=str(tmp_path/'chroma'), data_dir=str(Path('data').resolve()),
        admin_api_key='test-operator-key', atlas_mode='demo', demo_access=True)
    with TestClient(create_app(config)) as c:
        yield c


def login(client, customer='C0001'):
    response = client.post('/api/sessions', json={'customer_id':customer})
    assert response.status_code == 200, response.text
    return {'Authorization':'Bearer '+response.json()['token']}
