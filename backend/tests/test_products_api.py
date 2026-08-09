"""End-to-end HTTP tests for the product model and the five-slot upload."""

from __future__ import annotations

import pytest

from tests.conftest import make_image

EARRING = {
    "code": "E425",
    "name": "Cascade Drop Earrings",
    "category": "earrings",
    "description": "Waterproof gold-tone with a freshwater pearl.",
    "dimensions_mm": {"drop": 36, "width": 12},
}


def test_meta_endpoints_are_reachable(client):
    """Guards the FastAPI 0.141 include_router nesting change."""
    for path, expected in [
        ("/api/asset-types", 7),
        ("/api/formats", 7),
        ("/api/categories", 6),
    ]:
        res = client.get(path)
        assert res.status_code == 200, path
        assert len(res.json()) == expected, path

    assert client.get("/api/angles").json()["required"] == ["front"]


def test_categories_expose_exactly_one_primary_dimension(client):
    for cat in client.get("/api/categories").json():
        primaries = [d for d in cat["dimensions"] if d["primary"]]
        assert len(primaries) == 1, cat["key"]


def test_create_read_update_delete(client):
    created = client.post("/api/products", json=EARRING)
    assert created.status_code == 201
    product = created.json()
    assert product["id"] == "e425"
    assert product["code"] == "E425"
    assert product["primary_dimension_key"] == "drop"
    assert product["primary_mm"] == 36

    assert client.get(f"/api/products/{product['id']}").status_code == 200
    assert len(client.get("/api/products").json()) == 1

    patched = client.patch(f"/api/products/{product['id']}", json={"name": "Cascade Drops"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Cascade Drops"

    assert client.delete(f"/api/products/{product['id']}").status_code == 204
    assert client.get(f"/api/products/{product['id']}").status_code == 404


def test_duplicate_code_is_rejected(client):
    assert client.post("/api/products", json=EARRING).status_code == 201
    assert client.post("/api/products", json=EARRING).status_code == 409


def test_blockers_explain_why_generate_is_disabled(client):
    """A draft must say what is missing, not just be un-generatable."""
    res = client.post("/api/products", json={**EARRING, "dimensions_mm": {"drop": 36}})
    product = res.json()
    assert product["is_ready"] is False
    assert product["status"] == "draft"
    assert "Missing dimension: Width at widest point" in product["blockers"]
    assert "Missing required angle: front" in product["blockers"]


def test_product_becomes_ready_once_dimensions_and_front_angle_land(client):
    pid = client.post("/api/products", json=EARRING).json()["id"]
    assert client.get(f"/api/products/{pid}").json()["is_ready"] is False

    res = client.put(
        f"/api/products/{pid}/angles/front",
        files={"file": ("front.jpg", make_image(), "image/jpeg")},
    )
    assert res.status_code == 200
    product = res.json()
    assert product["is_ready"] is True
    assert product["status"] == "ready"
    assert product["blockers"] == []
    assert product["angles"]["front"]["width"] == 1200


@pytest.mark.parametrize(
    "payload,field",
    [
        ({**EARRING, "dimensions_mm": {"drop": 0, "width": 12}}, "greater than 0"),
        ({**EARRING, "dimensions_mm": {"drop": 5000, "width": 12}}, "millimetres"),
        ({**EARRING, "dimensions_mm": {"length": 36}}, "Unknown dimension"),
        ({**EARRING, "code": "bad code!"}, "Code must be"),
    ],
)
def test_invalid_products_are_rejected_with_a_useful_message(client, payload, field):
    res = client.post("/api/products", json=payload)
    assert res.status_code == 422
    assert field in res.text


def test_upload_rejects_non_images(client):
    pid = client.post("/api/products", json=EARRING).json()["id"]
    res = client.put(
        f"/api/products/{pid}/angles/front",
        files={"file": ("notes.txt", b"this is not an image", "text/plain")},
    )
    assert res.status_code == 400
    assert "not a readable image" in res.text.lower()


def test_upload_rejects_images_too_small_to_export(client):
    pid = client.post("/api/products", json=EARRING).json()["id"]
    res = client.put(
        f"/api/products/{pid}/angles/front",
        files={"file": ("tiny.jpg", make_image(300, 300), "image/jpeg")},
    )
    assert res.status_code == 400
    assert "512" in res.text


def test_reupload_replaces_rather_than_accumulates(client):
    pid = client.post("/api/products", json=EARRING).json()["id"]
    client.put(
        f"/api/products/{pid}/angles/front",
        files={"file": ("a.png", make_image(800, 800, "PNG"), "image/png")},
    )
    res = client.put(
        f"/api/products/{pid}/angles/front",
        files={"file": ("b.jpg", make_image(900, 900), "image/jpeg")},
    )
    product = res.json()
    assert product["angles"]["front"]["width"] == 900

    from app.core.store import get_store

    stored = list(get_store().upload_dir(pid).glob("front.*"))
    assert len(stored) == 1, f"stale files left behind: {stored}"


def test_all_five_angle_slots_accept_uploads(client):
    pid = client.post("/api/products", json=EARRING).json()["id"]
    for angle in ("front", "back", "left", "right", "extra"):
        res = client.put(
            f"/api/products/{pid}/angles/{angle}",
            files={"file": (f"{angle}.jpg", make_image(), "image/jpeg")},
        )
        assert res.status_code == 200, angle
    assert len(res.json()["angles"]) == 5

    assert client.get(f"/api/products/{pid}/angles/left/raw").status_code == 200

    removed = client.delete(f"/api/products/{pid}/angles/left")
    assert removed.status_code == 200
    assert "left" not in removed.json()["angles"]
    assert client.get(f"/api/products/{pid}/angles/left/raw").status_code == 404


def test_deleting_a_product_removes_its_uploads(client):
    pid = client.post("/api/products", json=EARRING).json()["id"]
    client.put(
        f"/api/products/{pid}/angles/front",
        files={"file": ("front.jpg", make_image(), "image/jpeg")},
    )
    from app.core.store import get_store

    upload_dir = get_store().upload_dir(pid)
    assert list(upload_dir.iterdir())

    client.delete(f"/api/products/{pid}")
    assert not upload_dir.exists()


def test_dimensions_phrase_feeds_prompts(client):
    from app.core.store import get_store

    pid = client.post("/api/products", json=EARRING).json()["id"]
    product = get_store().get(pid)
    assert product.dimensions_phrase() == "36 mm drop, 12 mm width at widest point"
