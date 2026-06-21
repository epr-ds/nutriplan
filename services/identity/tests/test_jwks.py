def test_jwks_endpoint_serves_public_key(client):
    response = client.get("/.well-known/jwks.json")
    assert response.status_code == 200
    key = response.json()["keys"][0]
    assert key["kty"] == "RSA"
    assert key["use"] == "sig"
    assert key["alg"] == "RS256"
