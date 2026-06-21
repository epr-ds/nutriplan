def _register(client, email="carol@example.com"):
    return client.post(
        "/auth/register",
        json={"email": email, "password": "supersecret", "name": "Carol"},
    ).json()


def _auth(tokens):
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


def test_update_profile_name_and_avatar(client):
    tokens = _register(client)
    response = client.put(
        "/users/me",
        headers=_auth(tokens),
        json={"name": "Carol Updated", "avatarUrl": "https://cdn.example.com/a.png"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Carol Updated"
    assert body["avatarUrl"] == "https://cdn.example.com/a.png"


def test_update_profile_requires_auth(client):
    response = client.put("/users/me", json={"name": "Nobody"})
    assert response.status_code == 401


def test_update_profile_rejects_short_name(client):
    tokens = _register(client)
    response = client.put("/users/me", headers=_auth(tokens), json={"name": "x"})
    assert response.status_code == 422


def test_dietary_preferences_round_trip_through_me(client):
    tokens = _register(client)
    prefs = {
        "dietType": "vegan",
        "allergies": ["peanuts"],
        "dailyCalorieTarget": 2200,
        "macroTargets": {"proteinGrams": 150, "carbsGrams": 200, "fatGrams": 70},
        "cuisinePreferences": ["mexican", "italian"],
        "appetiteSatisfactionLevel": 4,
    }
    put = client.put("/users/me/dietary-preferences", headers=_auth(tokens), json=prefs)
    assert put.status_code == 200
    assert put.json()["dietType"] == "vegan"

    me = client.get("/users/me", headers=_auth(tokens)).json()
    stored = me["dietaryPreferences"]
    assert stored["dietType"] == "vegan"
    assert stored["dailyCalorieTarget"] == 2200
    assert stored["cuisinePreferences"] == ["mexican", "italian"]
    assert stored["macroTargets"]["proteinGrams"] == 150


def test_dietary_preferences_partial_update_preserves_unset(client):
    tokens = _register(client)
    client.put("/users/me/dietary-preferences", headers=_auth(tokens), json={"dietType": "keto"})
    client.put(
        "/users/me/dietary-preferences",
        headers=_auth(tokens),
        json={"dailyCalorieTarget": 1800},
    )
    stored = client.get("/users/me", headers=_auth(tokens)).json()["dietaryPreferences"]
    assert stored["dietType"] == "keto"
    assert stored["dailyCalorieTarget"] == 1800


def test_dietary_preferences_rejects_invalid_enum(client):
    tokens = _register(client)
    response = client.put(
        "/users/me/dietary-preferences", headers=_auth(tokens), json={"dietType": "carnivore"}
    )
    assert response.status_code == 422


def test_dietary_preferences_rejects_out_of_range(client):
    tokens = _register(client)
    low_calories = client.put(
        "/users/me/dietary-preferences", headers=_auth(tokens), json={"dailyCalorieTarget": 999}
    )
    assert low_calories.status_code == 422

    bad_appetite = client.put(
        "/users/me/dietary-preferences",
        headers=_auth(tokens),
        json={"appetiteSatisfactionLevel": 9},
    )
    assert bad_appetite.status_code == 422
