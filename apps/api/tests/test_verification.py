from app.verification import verify_workspace
def test_verify_workspace(tmp_path)->None:
    (tmp_path/"result.txt").write_text("done")
    results=verify_workspace(str(tmp_path),["result.txt","missing.txt"])
    assert results[0].passed and not results[1].passed
