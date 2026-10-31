"""Property value samplers: spec values first, then cross-project priors, then name-shape fallbacks."""
import math, random, re, uuid, datetime as dt
from specio import num, shape_of

VOCAB = {
    "status": ["active", "pending", "completed", "failed", "cancelled"],
    "state": ["open", "closed", "in_progress", "archived"],
    "source": ["web", "ios", "android", "api", "email", "import"],
    "channel": ["organic", "paid", "referral", "email", "direct"],
    "platform": ["web", "ios", "android", "desktop"],
    "type": ["default", "standard", "custom", "advanced"],
    "kind": ["default", "standard", "custom"],
    "category": ["general", "billing", "product", "support", "other"],
    "plan": ["free", "starter", "pro", "team", "enterprise"],
    "tier": ["free", "basic", "premium", "enterprise"],
    "role": ["owner", "admin", "member", "viewer"],
    "method": ["email", "google", "github", "sso"],
    "currency": ["USD", "EUR", "GBP", "CAD", "AUD"],
    "language": ["en", "es", "de", "fr", "pt", "ja"],
    "locale": ["en-US", "en-GB", "de-DE", "fr-FR", "es-ES"],
    "country": ["US", "GB", "DE", "IN", "CA", "FR", "BR", "AU"],
    "environment": ["production", "staging", "development"],
    "env": ["production", "staging", "development"],
    "browser": ["Chrome", "Safari", "Firefox", "Edge"],
    "device": ["desktop", "mobile", "tablet"],
    "provider": ["openai", "anthropic", "google"],
    "model": ["gpt-4o-mini", "claude-sonnet-4-5", "gemini-2.5-flash"],
    "action": ["create", "update", "delete", "view"],
    "step": ["start", "details", "review", "confirm"],
    "variant": ["control", "test"],
    "result": ["success", "error"],
    "error": ["timeout", "invalid_input", "not_found", "rate_limited"],
    "reason": ["user_cancelled", "timeout", "payment_failed", "other"],
    "format": ["csv", "pdf", "json", "png"],
    "mode": ["light", "dark", "auto"],
    "theme": ["light", "dark", "system"],
    "interval": ["monthly", "yearly"],
    "frequency": ["daily", "weekly", "monthly"],
}


def zipf_weights(n, s=0.9):
    return [1.0 / (k + 1) ** s for k in range(n)]


def coerce(v, typ):
    if typ == "Numeric":
        x = num(v)
        if x is None:
            return None
        return int(x) if x == int(x) and abs(x) < 1e15 else x
    if typ == "Boolean":
        lv = str(v).strip().lower()
        if lv in ("true", "1", "yes"):
            return True
        if lv in ("false", "0", "no"):
            return False
        return None
    return str(v)


def value_class(v):
    v = str(v)
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", v, re.I):
        return "uuid"
    if re.fullmatch(r"-?\d+", v):
        return "int"
    if re.fullmatch(r"[a-z]+_[A-Za-z0-9]{6,}", v):
        return "prefixed_id"
    if re.fullmatch(r"[0-9a-f]{16,}", v, re.I):
        return "hex"
    return "other"


def stem_of(name):
    n = name.lstrip("$").lower()
    n = re.sub(r"(_id|_ids|_count|_at|_date|_time|_ms|_seconds|_name|_type|_url|_key)$", "", n)
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_") or "value"


class Sampler:
    """Callable producing a JSON-ready value for one (event, property). `ctx` is a per-event context dict."""

    def __init__(self, name, typ, values=None, more=None, prior=None, shape_prior=None, rnd=None, project=None):
        self.name = name
        self.rnd = rnd or random.Random(0)
        self.project = project
        self.shape = shape_of(name)
        if typ is None:
            typ = self._infer_type(values, prior, shape_prior)
        self.type = typ
        self.choices = []
        self.weights = []
        self.mode = None
        vals = []
        for v in values or []:
            c = coerce(v, typ)
            if c is not None and c != "":
                vals.append(c)
        src = "spec"
        if self.shape == "email" and not vals:
            # round 3: the cross-project prior holds anonymized userN@example.com placeholders, drawn per row; an email
            # property follows the row's person (anonymous persons have none)
            self.mode, self.source = "person_email", "shape"
            return
        if not vals and prior and prior.get("values"):
            pv = [(coerce(v, typ), c) for v, c in prior["values"]]
            pv = [(v, c) for v, c in pv if v is not None and v != ""]
            if pv:
                self.choices = [v for v, _ in pv]
                self.weights = [float(c) for _, c in pv]
                src = "prior"
        self.pending = list(dict.fromkeys(vals)) if vals else []
        self.p_force = 0.05
        if vals:
            self.choices = vals
            self.weights = zipf_weights(len(vals))
            if more:
                extra = self._synthetic_pool(vals, more)
                if extra:
                    tot = sum(self.weights)
                    self.choices = self.choices + extra
                    self.weights = self.weights + [0.35 * tot / len(extra)] * len(extra)
        if self.choices:
            self.mode = "choice"
            self.source = src
            self._cum = []
            acc = 0.0
            for w in self.weights:
                acc += w
                self._cum.append(acc)
            # Numeric spec values with few samples: jitter around them for realism
            self.jitter = typ == "Numeric" and len(set(self.choices)) >= 3 and all(isinstance(c, (int, float)) for c in self.choices)
        else:
            self.source = "shape"
            self._setup_shape(prior, shape_prior)

    def _infer_type(self, values, prior, shape_prior):
        if prior and prior.get("type"):
            return prior["type"]
        if values:
            if all(num(v) is not None for v in values) and self.shape in ("count", "duration", "money"):
                return "Numeric"
            if all(str(v).lower() in ("true", "false") for v in values):
                return "Boolean"
            return "String"
        if shape_prior and shape_prior.get("types"):
            return max(shape_prior["types"].items(), key=lambda kv: kv[1])[0]
        return "String"

    def _synthetic_pool(self, vals, more):
        n = 30 if more == "many" else min(30, int(more) if str(more).isdigit() else 10)
        classes = [value_class(v) for v in vals]
        cls = max(set(classes), key=classes.count)
        r = self.rnd
        if cls == "uuid":
            return [str(uuid.UUID(int=r.getrandbits(128), version=4)) for _ in range(n)]
        if cls == "int":
            ints = [int(v) for v in vals if re.fullmatch(r"-?\d+", str(v))]
            lo, hi = min(ints), max(ints)
            if hi <= lo:
                hi = lo + 100
            return [str(r.randint(lo, hi)) if isinstance(vals[0], str) else r.randint(lo, hi) for _ in range(n)]
        if cls == "prefixed_id":
            pre = str(vals[0]).split("_")[0]
            return [f"{pre}_{''.join(r.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(10))}" for _ in range(n)]
        if cls == "hex":
            return ["%032x" % r.getrandbits(128) for _ in range(n)]
        return []

    def _setup_shape(self, prior, shape_prior):
        r = self.rnd
        t, sh, nm = self.type, self.shape, self.name.lower()
        self.mode = "shape_" + {"Numeric": "num", "Boolean": "bool", "DateTime": "dt"}.get(t, "str")
        if t == "Numeric":
            if "_ms" in nm or nm.endswith("ms") or "latency" in nm:
                self.med, self.sig, self.is_int = 800.0, 1.0, True
            elif "second" in nm or "duration" in nm:
                self.med, self.sig, self.is_int = 45.0, 1.1, True
            elif sh == "money":
                self.med, self.sig, self.is_int = 49.0, 1.0, False
            elif sh == "count":
                self.med, self.sig, self.is_int = 4.0, 0.9, True
            elif "percent" in nm or "pct" in nm or "rate" in nm or "score" in nm:
                self.med, self.sig, self.is_int = 50.0, 0.5, False
            elif sh == "id":
                self.med, self.sig, self.is_int = 50000.0, 1.0, True
            else:
                p50 = ((prior or {}).get("numeric") or {}).get("p50")
                self.med = float(p50) if p50 and p50 > 0 else 10.0
                self.sig, self.is_int = 1.0, True
        elif t == "Boolean":
            self.p = r.uniform(0.15, 0.75)
        elif t == "String":
            pool = None
            if sh == "id":
                cls = "uuid"
                vc = (shape_prior or {}).get("value_classes") or {}
                if vc:
                    opts = [(k, v) for k, v in vc.items() if k in ("uuid", "int", "prefixed_id", "slug")]
                    if opts:
                        cls = r.choices([k for k, _ in opts], [v for _, v in opts])[0]
                self.id_class = cls
                self.mode = "shape_id"
                self.id_pool = None
                if "user" in nm or "person" in nm or "customer" in nm or "distinct" in nm or "member" in nm:
                    self.mode = "person_id"
                elif "session" in nm:
                    self.mode = "session_id"
                else:
                    # bounded id cardinality makes breakdowns realistic
                    self.id_pool = [self._make_id(cls, stem_of(self.name)) for _ in range(r.randint(20, 400))]
                return
            if sh == "email":
                self.mode = "person_email"
                return
            if sh == "url":
                self.mode = "page_url"
                return
            if sh == "path":
                self.mode = "page_path"
                return
            toks = re.split(r"[^a-z]+", nm.lstrip("$"))
            for tok in reversed(toks):
                if tok in VOCAB:
                    pool = VOCAB[tok]
                    break
            if pool is None:
                stem = stem_of(self.name)
                if sh == "name":
                    pool = [f"{stem.replace('_', ' ').title()} {i}" for i in range(1, r.randint(4, 25))]
                else:
                    pool = [f"{stem}_{c}" for c in "abcdefghijkl"[: r.randint(3, 8)]]
            self.mode = "choice"
            self.choices = pool
            self.weights = zipf_weights(len(pool), 1.1)
            acc = 0.0
            self._cum = []
            for w in self.weights:
                acc += w
                self._cum.append(acc)
            self.jitter = False

    def _make_id(self, cls, stem):
        r = self.rnd
        if cls == "int":
            return str(r.randint(1000, 999999))
        if cls == "prefixed_id":
            return f"{stem[:4]}_{''.join(r.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(12))}"
        if cls == "slug":
            return f"{stem}-{r.randint(1, 9999)}"
        return str(uuid.UUID(int=r.getrandbits(128), version=4))

    def plan(self, n_calls):
        """Make sure every spec value is emitted at least once over roughly the first third of n_calls."""
        if self.pending:
            self.p_force = min(1.0, 3.0 * len(self.pending) / max(1, n_calls))

    def __call__(self, ctx):
        r = self.rnd
        m = self.mode
        if self.pending and r.random() < self.p_force:
            return self.pending.pop(r.randrange(len(self.pending)))
        if m == "choice":
            import bisect
            x = r.random() * self._cum[-1]
            v = self.choices[min(len(self.choices) - 1, bisect.bisect_left(self._cum, x))]
            if self.jitter and r.random() < 0.3:
                v = v * r.uniform(0.7, 1.3)
                v = int(round(v)) if isinstance(self.choices[0], int) else round(v, 2)
            return v
        if m == "shape_num":
            v = self.med * math.exp(r.gauss(0, self.sig))
            return int(round(v)) if self.is_int else round(v, 2)
        if m == "shape_bool":
            return r.random() < self.p
        if m == "shape_dt":
            ts = ctx["ts"] - dt.timedelta(days=r.expovariate(1 / 20))
            return ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        if m == "shape_id":
            return r.choice(self.id_pool)
        if m == "person_id":
            return ctx["person"]["user_id"]
        if m == "session_id":
            return ctx.get("session_id")
        if m == "person_email":
            return ctx["person"]["email"]
        if m == "page_url":
            return ctx.get("url") or self.project.page()[0]
        if m == "page_path":
            return ctx.get("path") or self.project.page()[2]
        return None
