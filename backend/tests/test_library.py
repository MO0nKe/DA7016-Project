from .conftest import upload


def test_folders_nest_move_and_delete_safely(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    course = api.post("/api/folders", json={"name": "Course"}).json()
    week1 = api.post("/api/folders", json={"name": "Week 1", "parent": course["id"]}).json()
    assert api.put(f"/api/documents/{doc_id}/folder", json={"folder_id": week1["id"]}).status_code == 200
    assert api.get("/api/library").json()["placement"] == {doc_id: week1["id"]}

    # Renaming keeps the parent; moving a folder into its own child is refused.
    assert api.patch(f"/api/folders/{course['id']}", json={"name": "DA7016"}).json()["parent"] is None
    assert api.patch(f"/api/folders/{course['id']}", json={"parent": week1["id"], "move": True}).status_code == 400
    assert api.post("/api/folders", json={"name": "x", "parent": "nope"}).status_code == 400
    assert api.post("/api/folders", json={"name": ""}).status_code == 422

    # Deleting Week 1 moves its document up to the course folder; deleting that moves it to the top.
    assert api.delete(f"/api/folders/{week1['id']}").status_code == 200
    assert api.get("/api/library").json()["placement"] == {doc_id: course["id"]}
    api.delete(f"/api/folders/{course['id']}")
    lib = api.get("/api/library").json()
    assert lib == {"folders": [], "placement": {}}
    assert [d["id"] for d in api.get("/api/documents").json()] == [doc_id]


def test_deleting_a_document_forgets_its_folder(api):
    doc_id = upload(api, "sample_en.pdf")["id"]
    folder = api.post("/api/folders", json={"name": "Keep"}).json()
    api.put(f"/api/documents/{doc_id}/folder", json={"folder_id": folder["id"]})
    api.delete(f"/api/documents/{doc_id}")
    assert api.get("/api/library").json()["placement"] == {}
