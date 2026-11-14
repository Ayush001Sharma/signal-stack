"""Deterministic NLP utilities: cleaning, keyphrases, entities, dates, sentiment, similarity.

These run without any AI service so the platform works fully offline-from-LLM. The optional LLM
layer (services/llm.py) only refines wording; it never supplies evidence.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from app.core.config import get_settings

log = logging.getLogger(__name__)

STOPWORDS = set(
    """a about above after again against all am an and any are aren't as at be because been before being below between both but by
can cannot could did do does doing don't down during each few for from further had has have having he her here hers herself him himself
his how i if in into is it its itself let's me more most my myself no nor not of off on once only or other ought our ours ourselves out
over own same she should so some such than that the their theirs them themselves then there these they this those through to too under
until up very was we were what when where which while who whom why with would you your yours yourself yourselves will just also get
us via new news one two three per may can't won't it's we're you're they're isn't don't doesn't didn't via vs etc more less many much
every across within without upon among like make makes made help helps helping best top get gets using use used way ways need needs
home contact login sign signup started start learn read click page here privacy policy terms cookie cookies copyright rights reserved
menu search blog know today now year years day days time free great world global leading trusted team support services service
""".split()
)

COUNTRIES = {
    "United States": ["united states", "usa", "u.s.", "us visa", "america", "american"],
    "United Kingdom": ["united kingdom", "uk", "britain", "england", "scotland"],
    "Canada": ["canada", "canadian"],
    "Australia": ["australia", "australian"],
    "Germany": ["germany", "german"],
    "Ireland": ["ireland", "irish"],
    "New Zealand": ["new zealand"],
    "India": ["india", "indian"],
    "France": ["france", "french"],
    "Netherlands": ["netherlands", "dutch"],
    "Singapore": ["singapore"],
    "United Arab Emirates": ["uae", "dubai", "united arab emirates"],
    "Japan": ["japan"],
    "China": ["china", "chinese"],
    "Italy": ["italy", "italian"],
    "Spain": ["spain"],
    "Sweden": ["sweden"],
    "Brazil": ["brazil"],
    "Mexico": ["mexico"],
    "South Africa": ["south africa"],
    "Nigeria": ["nigeria"],
    "Kenya": ["kenya"],
    "Indonesia": ["indonesia"],
    "Philippines": ["philippines"],
    "Malaysia": ["malaysia"],
    "Europe": ["europe", "european union", "eu"],
}

SEGMENT_LEXICON = {
    "Students": ["student", "students", "aspirant", "aspirants", "learners"],
    "Parents": ["parent", "parents"],
    "Universities / institutions": ["universities", "institutions", "colleges", "schools"],
    "Small & medium businesses": ["small business", "smb", "smbs", "sme", "smes", "small and medium"],
    "Enterprises": ["enterprise", "enterprises", "large organizations", "fortune 500"],
    "Developers": ["developer", "developers", "engineers", "devops"],
    "Startups": ["startup", "startups", "founders"],
    "Consumers": ["consumers", "customers", "shoppers", "households"],
    "Working professionals": ["professionals", "working professionals", "employees"],
    "Healthcare providers": ["clinics", "hospitals", "doctors", "patients"],
    "Retailers / merchants": ["merchants", "retailers", "sellers", "d2c brands", "e-commerce brands"],
    "Financial institutions": ["banks", "lenders", "nbfc", "fintechs"],
    "Freelancers / creators": ["freelancers", "creators", "influencers"],
    "Government / public sector": ["government", "public sector", "municipal"],
}

BUSINESS_MODEL_CUES = {
    "Subscription / SaaS": ["subscription", "per month", "/month", "per user", "saas", "monthly plan", "annual plan", "free trial"],
    "Freemium": ["free plan", "freemium", "free forever", "upgrade to pro"],
    "Marketplace / commission": ["marketplace", "commission", "take rate", "sellers and buyers", "listings"],
    "Services / consulting fees": ["consultation", "consulting", "counselling", "counseling", "advisors", "expert guidance", "end-to-end support", "agency"],
    "Transaction / payments fees": ["transaction fee", "payment processing", "per transaction", "mdr"],
    "Advertising / lead generation": ["advertis", "sponsored", "lead generation", "leads"],
    "Lending / financing": ["loan", "loans", "financing", "emi", "credit"],
    "E-commerce / product sales": ["add to cart", "buy now", "shop now", "free shipping", "checkout"],
    "Institution partnerships / referral fees": ["partner universities", "university partners", "partnered with", "trusted university", "institution partners"],
}

INDUSTRY_TAXONOMY = {
    "Education / study-abroad services": "study abroad overseas education university admissions student visa counselling scholarships international students test preparation ielts gre",
    "EdTech / online learning": "online courses e-learning edtech upskilling certification learning platform students teachers lms",
    "Fintech / payments": "payments payment gateway upi fintech banking cards transactions merchants checkout payouts lending credit",
    "Developer tools / SaaS": "api developers software platform cloud deployment code saas integration devops observability",
    "E-commerce / retail": "online shopping store products delivery ecommerce retail brands cart orders",
    "Healthcare / healthtech": "health healthcare patients doctors clinics telemedicine pharmacy diagnostics hospital",
    "Food delivery / quick commerce": "food delivery restaurants groceries quick commerce dark stores orders",
    "Travel / hospitality": "travel hotels flights bookings tourism holidays hospitality",
    "Real estate / proptech": "property real estate homes rent buy apartments housing proptech",
    "HR tech / recruitment": "hiring recruitment jobs candidates hr payroll talent employees",
    "Marketing / adtech": "marketing advertising campaigns seo social media brands agencies analytics",
    "Logistics / supply chain": "logistics shipping freight warehouse supply chain courier fleet",
    "Mobility / automotive": "cars vehicles electric vehicles ev mobility rides automotive",
    "Media / content": "news media content video streaming publishing creators",
    "Cybersecurity": "security threats cyber protection identity zero trust vulnerabilities",
    "AI / machine learning": "artificial intelligence machine learning models llm genai ai platform",
    "Insurance / insurtech": "insurance policy claims premiums insurtech cover",
    "Energy / climate": "energy solar renewable climate carbon batteries power",
    "Agriculture / agritech": "farmers agriculture crops agritech farm",
    "Gaming": "games gaming players esports",
}

POS_WORDS = set("growth launch launches surge record wins win award expands expansion partnership raise raises opportunity relaxes eased boost increase increases rising demand approve approved scholarship scholarships simplify simplified cheaper cut cuts".split())


# ---------------------------------------------------------------- text helpers
def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
        tag.decompose()
    return clean_text(soup.get_text(" "))


def truncate(text: str | None, n: int = 400) -> str:
    text = clean_text(text)
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def title_key(title: str) -> str:
    t = re.sub(r"\s[-|–]\s[^-|–]{2,60}$", "", title or "")  # strip " - Publisher"
    t = re.sub(r"[^a-z0-9 ]", " ", t.lower())
    words = [w for w in t.split() if w not in STOPWORDS]
    return " ".join(words)[:280]


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid", "mc_cid", "mc_eid", "ocid"}


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urlparse(url)
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", p.path) or ""
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    q.sort()
    return urlunparse(("https", host, path, "", urlencode(q), ""))


def domain_of(url: str) -> str:
    host = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


# ---------------------------------------------------------------- dates
def parse_date(value) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (tuple, list)) and len(value) >= 6:  # feedparser struct_time
            dt = datetime(*value[:6])
        else:
            dt = dateparser.parse(str(value), fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # reject absurd dates (future > 2 days or before 1995)
        now = datetime.now(timezone.utc)
        if dt.year < 1995 or (dt - now).days > 2:
            return None
        return dt
    except (ValueError, OverflowError, TypeError):
        return None


def extract_html_date(soup: BeautifulSoup) -> tuple[datetime | None, str]:
    for attr, name in (("property", "article:published_time"), ("name", "date"), ("name", "pubdate"), ("itemprop", "datePublished"), ("name", "publish-date"), ("property", "og:updated_time")):
        tag = soup.find("meta", attrs={attr: name})
        if tag and tag.get("content"):
            d = parse_date(tag["content"])
            if d:
                return d, "html_meta"
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict):
                for key in ("datePublished", "dateCreated", "dateModified"):
                    if it.get(key):
                        d = parse_date(it[key])
                        if d:
                            return d, "jsonld"
    t = soup.find("time")
    if t and (t.get("datetime") or t.text):
        d = parse_date(t.get("datetime") or t.text)
        if d:
            return d, "html_time"
    return None, "unknown"


# ---------------------------------------------------------------- keyphrases
def keyphrases(texts: list[str], top_k: int = 25, boost: list[str] | None = None) -> list[str]:
    """Frequency-based uni/bi/tri-gram keyphrase extraction (stopword-delimited, RAKE-like)."""
    counts: Counter[str] = Counter()
    for text in texts:
        text = text.lower()
        text = re.sub(r"[^a-z0-9&+\- ]", " | ", text)
        for chunk in re.split(r"\|", text):
            words = [w for w in chunk.split() if w]
            phrase: list[str] = []
            for w in words + ["the"]:
                if w in STOPWORDS or len(w) < 3 or w.isdigit():
                    if 1 <= len(phrase) <= 3:
                        counts[" ".join(phrase)] += 1
                    elif len(phrase) > 3:
                        for i in range(len(phrase) - 1):
                            counts[" ".join(phrase[i : i + 2])] += 1
                    phrase = []
                else:
                    phrase.append(w)
    for b in boost or []:
        b = b.lower().strip()
        if b and len(b) > 2:
            counts[b] += 3
    scored = []
    for p, c in counts.items():
        n = len(p.split())
        scored.append((c * (1.0 + 0.6 * (n - 1)), p))
    scored.sort(reverse=True)
    out: list[str] = []
    for _, p in scored:
        if any(p in o or o in p for o in out if len(o.split()) > 1 or len(p.split()) > 1) and len(out) > 5:
            continue
        out.append(p)
        if len(out) >= top_k:
            break
    return out


def find_countries(text: str) -> dict[str, str]:
    t = " " + (text or "") + " "
    found = {}
    for country, aliases in COUNTRIES.items():
        for a in aliases:
            a = a.strip()
            flags = 0 if a in ("UK", "US", "EU") else re.I
            pat = re.compile(r"(?<![A-Za-z])" + re.escape(a if flags == 0 else a) + r"(?![A-Za-z])", flags)
            if a.lower() in ("uk", "eu"):
                pat = re.compile(r"(?<![A-Za-z])" + a.upper() + r"(?![A-Za-z])")
            m = pat.search(t)
            if m:
                found[country] = clean_text(t[max(0, m.start() - 60) : m.end() + 80])
                break
    return found


def find_segments(text: str) -> dict[str, str]:
    t = " " + (text or "").lower() + " "
    found = {}
    for seg, words in SEGMENT_LEXICON.items():
        for w in words:
            m = re.search(r"\b" + re.escape(w) + r"\b", t)
            if m:
                found[seg] = clean_text(t[max(0, m.start() - 70) : m.end() + 70])
                break
    return found


def business_model_cues(text: str) -> dict[str, list[str]]:
    t = (text or "").lower()
    out: dict[str, list[str]] = {}
    for model, cues in BUSINESS_MODEL_CUES.items():
        hits = [c for c in cues if c in t]
        if hits:
            out[model] = hits
    return out


# ---------------------------------------------------------------- entities
ORG_SUFFIX = r"(?:Edu|Education|Technologies|Tech|Labs|Inc|Ltd|Pvt|Group|Global|Pay|AI|Health|Bank|Capital|Learning|Scholar|Abroad|Ventures|Systems|Software|Cloud|Studio)"
ENTITY_STOP = set(
    """The A An This That These Those In On At For With From By Of And Or But Is Are Was Were Be How Why What When Where Who Which New
India Indian US UK USA Canada Australia Germany Ireland Europe European America American British China Chinese Japan Delhi Mumbai Bengaluru Bangalore
January February March April May June July August September October November December Monday Tuesday Wednesday Thursday Friday Saturday Sunday
Study Students Student University Universities College Visa Visas Government Ministry Report Reports Exclusive Top Best Why How Here Budget
CEO CTO CFO COO Series Funding Startup Startups Edtech EdTech Fintech Crore Lakh Million Billion Covid IPO AI GenAI Global Week Today News Live
Know Read Watch Check Explained Opinion Analysis Update Updates Latest Breaking Big Major First Last Next Inside More Most Says Said""".split()
)


def candidate_entities(text: str) -> list[str]:
    """Extract capitalised multi-token names (likely organisations/brands) from a headline/text."""
    text = re.sub(r"[‘’“”\"]", " ", text or "")
    pattern = re.compile(r"\b([A-Z][a-zA-Z0-9&\.]+(?:[\s\-][A-Z][a-zA-Z0-9&\.]+){0,3})\b")
    out = []
    for m in pattern.finditer(text):
        cand = m.group(1).strip(" .-")
        toks = cand.split()
        while toks and toks[0] in ENTITY_STOP:
            toks = toks[1:]
        while toks and toks[-1] in ENTITY_STOP:
            toks = toks[:-1]
        if not toks:
            continue
        cand = " ".join(toks)
        if len(cand) < 3 or cand.upper() == cand and len(cand) <= 3:
            continue
        if cand.lower() in STOPWORDS:
            continue
        out.append(cand)
    # camel-case brands like "LeapScholar", "upGrad"
    for m in re.finditer(r"\b([a-z]+[A-Z][a-zA-Z]+|[A-Z][a-z]+[A-Z][a-zA-Z]+)\b", text):
        out.append(m.group(1))
    return out


# ---------------------------------------------------------------- sentiment
_vader = None


def sentiment(text: str) -> float:
    global _vader
    if _vader is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        _vader = SentimentIntensityAnalyzer()
    return float(_vader.polarity_scores(text or "")["compound"])


# ---------------------------------------------------------------- similarity
class Embedder:
    """Sentence-transformer embeddings when available; TF-IDF cosine otherwise."""

    def __init__(self):
        self.backend = "tfidf"
        self._model = None
        self._lock = threading.Lock()
        s = get_settings()
        if s.embeddings_backend in ("auto", "sentence-transformers"):
            try:
                from sentence_transformers import SentenceTransformer  # noqa: WPS433

                self._model = SentenceTransformer(s.embeddings_model, device="cpu")
                self.backend = "sentence-transformers"
            except Exception as exc:  # pragma: no cover - depends on optional install
                if s.embeddings_backend == "sentence-transformers":
                    raise
                log.info("sentence-transformers unavailable, using TF-IDF: %s", exc)

    def similarity_matrix(self, queries: list[str], docs: list[str]):
        import numpy as np

        if not queries or not docs:
            return np.zeros((len(queries), len(docs)))
        if self._model is not None:
            with self._lock:
                q = self._model.encode(queries, normalize_embeddings=True, show_progress_bar=False)
                d = self._model.encode(docs, normalize_embeddings=True, show_progress_bar=False)
            sims = q @ d.T
            # MiniLM cosine for related text ~0.3-0.7; rescale to 0..1
            return np.clip((sims - 0.05) / 0.6, 0, 1)
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        m = vec.fit_transform(queries + docs)
        qm, dm = m[: len(queries)], m[len(queries) :]
        sims = (qm @ dm.T).toarray()
        return np.clip(sims * 2.2, 0, 1)

    def similarity(self, a: str, docs: list[str]) -> list[float]:
        return [float(x) for x in self.similarity_matrix([a], docs)[0]]


_embedder: Embedder | None = None
_emb_lock = threading.Lock()


def get_embedder() -> Embedder:
    global _embedder
    with _emb_lock:
        if _embedder is None:
            _embedder = Embedder()
        return _embedder


def tfidf_similarity_matrix(a: list[str], b: list[str]):
    """Pure lexical similarity (used for duplicate/novelty checks where wording overlap matters)."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer

    if not a or not b:
        return np.zeros((len(a), len(b)))
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    m = vec.fit_transform(a + b)
    return (m[: len(a)] @ m[len(a) :].T).toarray()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
