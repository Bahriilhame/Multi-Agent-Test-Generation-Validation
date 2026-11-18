import pytest

from app import app


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def test_multiply_endpoint(client):
    response = client.post("/multiply", json={"left": 3, "right": 4})
    assert response.status_code == 200
    assert response.json == {"result": 12}
