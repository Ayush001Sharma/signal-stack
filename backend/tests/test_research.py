from app.models import ProfileFact
from app.services.research import research_company
from tests.conftest import rss

HOME = """<html><head><title>Acme Study | Study abroad made simple</title>
<meta name="description" content="Acme Study helps international students with university admissions, student visa assistance and scholarships.">
<meta name="keywords" content="study abroad, university admissions, student visa assistance"></head>
<body><h1>Study abroad made simple</h1>
<h2>University Selection and Application</h2><p>Our counsellors help students choose universities in the UK, Canada and Australia.</p>
<h2>Visa and Immigration Support</h2><p>Expert guidance for student visa applications for students and parents.</p>
<h2>Why Choose Us</h2><p>Students trust our consultation and end-to-end support.</p>
<a href="/about">About</a><a href="/services">Services</a><a href="mailto:hello@acme.example">mail</a><a href="tel:+91 99999 99999">call</a></body></html>"""
ABOUT = "<html><head><title>About Acme</title></head><body><h2>Scholarship Planning Service</h2><p>We support students and parents across India.</p></body></html>"


def setup_site(web):
    web.add("https://acme.example", HOME)
    web.add("https://acme.example/about", ABOUT)
    web.add("https://acme.example/services", ABOUT.replace("About", "Services"))
    feed = rss([
        {"title": "Acme Study launches scholarship finder for international students", "link": "https://news.example/acme-1", "desc": "Acme Study, a study abroad platform, launched a tool for university admissions and scholarships."},
        {"title": "Acme Study FC wins football derby", "link": "https://news.example/sport", "desc": "Acme Study football club won the derby match with three goals in the stadium."},
    ])
    web.add("https://www.bing.com/news/search*", feed, headers={"content-type": "application/rss+xml"})


def test_research_builds_provenance_tracked_profile(db, make_company, web):
    setup_site(web)
    c = make_company()
    summary = research_company(db, c, fetcher=web.fetcher(), use_llm=False)
    facts = db.query(ProfileFact).filter_by(company_id=c.id).all()
    by = {}
    for f in facts:
        by.setdefault(f.field, []).append(f)
    # positioning quoted from the site => verified with source URL
    pos = by["positioning"][0]
    assert pos.status == "verified" and pos.source_url.startswith("https://acme.example") and "international students" in pos.value
    # offerings extracted from headings, verified with evidence
    products = [f.value for f in by["products"]]
    assert "Visa and Immigration Support" in products and "Why Choose Us" not in products
    # business model is only an assumption; revenue streams need confirmation
    assert all(f.status in ("assumption", "needs_confirmation", "verified") for f in by["business_model"])
    assert any(f.status == "needs_confirmation" for f in by["revenue_streams"])
    assert any(f.status == "assumption" for f in by["industry"])
    # geographies + segments from text
    geos = " ".join(f.value for f in by["geographies"])
    assert "United Kingdom" in geos and "Canada" in geos
    assert any("Students" in f.value for f in by["customer_segments"])
    # news is unverified third-party information
    devs = by["developments"]
    assert all(f.status in ("unverified", "needs_confirmation") for f in devs)
    assert c.status == "researched" and summary["pages_crawled"]
    assert c.keywords and "study abroad" in c.keywords[:12]
    assert c.profile["products"]


def test_research_handles_unreachable_site(db, make_company, web):
    c = make_company(website="https://down.example")
    summary = research_company(db, c, fetcher=web.fetcher(), use_llm=False)
    assert c.status == "error" and summary["errors"]


def test_robots_disallow_is_respected(db, make_company, web):
    web.add("https://acme.example/robots.txt", "User-agent: *\nDisallow: /", headers={"content-type": "text/plain"})
    web.add("https://acme.example", HOME)
    c = make_company()
    research_company(db, c, fetcher=web.fetcher(), use_llm=False)
    assert "https://acme.example/" not in [u.rstrip("/") + "/" for u in web.calls if "robots" not in u]
    assert c.status == "error"
