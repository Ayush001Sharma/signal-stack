import io

from openpyxl import Workbook

CSV = """lead_id,stage,destination,lost_reason,notes
1,Closed Lost,UK,too expensive,Parent said the counselling fee is too expensive compared to free agents
2,Closed Lost,Canada,too expensive,Student felt the package price is too expensive for them
3,Closed Won,UK,,Enrolled after visa guidance session
4,Closed Lost,Canada,went with competitor,Went with a competitor offering free applications
5,Closed Won,UK,,Happy with scholarship support; asked us to add accommodation search
6,Closed Won,Australia,,Requested support for education loan and accommodation search
7,Closed Lost,Canada,visa rejected,Visa rejected after study permit cap; family worried about policy change
8,Closed Won,UK,,Enrolled; complained about slow document review delays
9,Closed Lost,Canada,too expensive,Budget concern: price too expensive for the family
10,Closed Won,UK,,Converted after webinar but documents review was slow with delays
"""


def _company(client, name="Acme", site="https://acme.example"):
    return client.post("/api/companies", json={"name": name, "website": site, "run_setup": False}).json()["id"]


def test_csv_upload_extracts_patterns(client):
    cid = _company(client)
    r = client.post(f"/api/companies/{cid}/documents", files={"file": ("SYNTHETIC_crm.csv", CSV, "text/csv")}, data={"description": "synthetic test data"})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["status"] == "processed" and doc["record_count"] == 10 and doc["file_type"] == "csv"
    labels = doc["insights"]["labels"]
    assert labels.get("objection", 0) >= 3 and labels.get("product_request", 0) >= 2
    titles = " ".join(t["title"] for t in doc["insights"]["themes"])
    assert "Win rate" in titles and "Lost-deal reason" in titles
    sigs = client.get(f"/api/companies/{cid}/signals?category=internal").json()
    assert sigs["total"] >= 3 and all(s["verification_status"] == "internal_document" for s in sigs["items"])
    assert all("row" in s["evidence_snippet"] or "aggregate" in s["evidence_snippet"] or "Won" in s["evidence_snippet"] for s in sigs["items"])


def test_xlsx_txt_and_pdf_uploads(client):
    cid = _company(client)
    wb = Workbook()
    ws = wb.active
    ws.append(["ticket", "message"])
    ws.append([1, "The app is slow and the document upload is broken again"])
    ws.append([2, "Upload of documents is broken and slow, very frustrating"])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post(f"/api/companies/{cid}/documents", files={"file": ("tickets.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 201 and r.json()["record_count"] == 2 and r.json()["insights"]["labels"]["recurring_problem"] == 2
    txt = "Customer call notes.\n\nCustomer asked if we can add an IELTS coaching integration.\n\nAnother customer would like IELTS coaching integration too."
    r = client.post(f"/api/companies/{cid}/documents", files={"file": ("calls.txt", txt, "text/plain")})
    assert r.status_code == 201 and r.json()["insights"]["labels"].get("product_request", 0) >= 2
    from xhtml2pdf import pisa

    pdf = io.BytesIO()
    pisa.CreatePDF("<p>Several clients said the pricing is too expensive.</p><p>Pricing is too expensive for small teams.</p>", dest=pdf)
    r = client.post(f"/api/companies/{cid}/documents", files={"file": ("report.pdf", pdf.getvalue(), "application/pdf")})
    assert r.status_code == 201 and r.json()["status"] == "processed"


def test_upload_validation_and_isolation(client):
    a = _company(client)
    b = _company(client, "Beta", "https://beta.example")
    assert client.post(f"/api/companies/{a}/documents", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 422
    assert client.post(f"/api/companies/{a}/documents", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")}).status_code == 422
    assert client.post(f"/api/companies/{a}/documents", files={"file": ("empty.csv", b"", "text/csv")}).status_code == 422
    big = b"a," * (6 * 1024 * 1024)
    assert client.post(f"/api/companies/{a}/documents", files={"file": ("big.csv", big, "text/csv")}).status_code == 422
    doc = client.post(f"/api/companies/{a}/documents", files={"file": ("crm.csv", CSV, "text/csv")}).json()
    assert client.get(f"/api/companies/{b}/documents").json() == []
    assert client.get(f"/api/companies/{b}/signals?category=internal").json()["total"] == 0
    assert client.delete(f"/api/companies/{b}/documents/{doc['id']}").status_code == 404
    assert client.delete(f"/api/companies/{a}/documents/{doc['id']}").status_code == 204
