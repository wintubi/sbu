def test_ui_is_served_without_inline_script(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "default-src 'none'" in page.headers["content-security-policy"]
    assert "script-src 'self'" in page.headers["content-security-policy"]
    body = page.text
    assert '<script src="/static/app.js"' in body
    assert "<script>" not in body
    assert "style=" not in body

    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "text/javascript" in script.headers["content-type"]

    css = client.get("/static/style.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
