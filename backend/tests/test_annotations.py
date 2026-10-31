from .conftest import upload


def test_annotation_crud(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    url = f"/api/documents/{doc_id}/annotations"
    hl = api.post(
        url, json={"page": 0, "rects": [[63, 155, 300, 168]], "quote": "This report", "color": "#fde047"}
    ).json()
    note = api.post(
        url, json={"kind": "note", "page": 1, "rects": [[100, 100, 120, 120]], "comment": "Check this"}
    ).json()
    box = api.post(
        url, json={"kind": "text", "page": 0, "rects": [[300, 700, 500, 730]], "comment": "Added text"}
    ).json()
    assert hl["id"] and hl["created"] and len(api.get(url).json()) == 3

    # A highlight on a language view keeps its language; an unknown one is refused.
    hi = {"page": 0, "rects": [[63, 155, 300, 168]], "quote": "यह रिपोर्ट", "lang": "hi"}
    hi = api.post(url, json=hi).json()
    assert hi["lang"] == "hi" and hl["lang"] == ""
    assert api.put(f"{url}/{hi['id']}", json={**hi, "lang": "ta", "comment": "मुख्य"}).json()["lang"] == "hi"
    assert api.post(url, json={**hi, "lang": "xx"}).status_code == 400
    assert api.delete(f"{url}/{hi['id']}").status_code == 200

    hl["comment"] = "Key point"
    assert api.put(f"{url}/{hl['id']}", json=hl).json()["comment"] == "Key point"
    assert api.post(url, json={"page": 9, "rects": [[0, 0, 1, 1]]}).status_code == 400
    assert api.put(f"{url}/nope", json=hl).status_code == 404

    # Translation slips were removed: new ones are refused.
    slip = {"kind": "slip", "page": 0, "rects": [[63, 155, 300, 190]], "quote": "x", "lang": "hi"}
    assert api.post(url, json=slip).status_code == 400

    assert api.delete(f"{url}/{note['id']}").status_code == 200
    assert [a["id"] for a in api.get(url).json()] == [hl["id"], box["id"]]
