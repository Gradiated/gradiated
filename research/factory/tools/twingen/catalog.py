"""Built-in public catalogs used when neither the spec nor the spec-derived priors supply values.

Everything here is generic public knowledge (browser names, countries, screen sizes, SDK names); nothing is taken
from the traces.
"""

BROWSERS = [  # (browser, weight, (major_min, major_max))
    ("Chrome", 0.55, (118, 131)), ("Safari", 0.18, (15, 18)), ("Mobile Safari", 0.10, (15, 18)),
    ("Edge", 0.05, (118, 131)), ("Firefox", 0.04, (115, 132)), ("Chrome iOS", 0.03, (118, 131)),
    ("Samsung Internet", 0.02, (20, 26)), ("Opera", 0.015, (100, 114)), ("Facebook Mobile", 0.01, (400, 480)),
    ("Android Mobile", 0.005, (100, 131)),
]
OS_BY_DEVICE = {
    "Desktop": [("Mac OS X", 0.48, "10.15.7"), ("Windows", 0.44, "10.0"), ("Linux", 0.06, ""), ("Chrome OS", 0.02, "")],
    "Mobile": [("iOS", 0.55, "18.1"), ("Android", 0.45, "14.0")],
    "Tablet": [("iOS", 0.65, "17.6"), ("Android", 0.35, "13.0")],
}
DEVICE_TYPES = [("Desktop", 0.64), ("Mobile", 0.33), ("Tablet", 0.03)]
DEVICES_MOBILE = ["iPhone", "Samsung Galaxy S23", "Pixel 8", "Samsung Galaxy A54", "iPhone 15", "OnePlus 11"]
SCREENS = {
    "Desktop": [(1920, 1080), (1440, 900), (1536, 864), (2560, 1440), (1366, 768), (1680, 1050), (1280, 800)],
    "Mobile": [(390, 844), (393, 852), (414, 896), (412, 915), (360, 800), (430, 932)],
    "Tablet": [(820, 1180), (768, 1024), (1024, 1366), (800, 1280)],
}
LANGS = [("en-US", 0.55), ("en-GB", 0.1), ("de-DE", 0.05), ("fr-FR", 0.05), ("es-ES", 0.05), ("pt-BR", 0.05),
         ("ja-JP", 0.03), ("nl-NL", 0.03), ("en-IN", 0.05), ("ko-KR", 0.02), ("it-IT", 0.02)]
# country code, name, continent code, continent name, weight, [(city, subdivision, subdivision code, postal, lat, lon, tz)]
COUNTRIES = [
    ("US", "United States", "NA", "North America", 0.38, [
        ("San Francisco", "California", "CA", "94103", 37.77, -122.42, "America/Los_Angeles"),
        ("New York", "New York", "NY", "10001", 40.71, -74.0, "America/New_York"),
        ("Austin", "Texas", "TX", "78701", 30.27, -97.74, "America/Chicago"),
        ("Seattle", "Washington", "WA", "98101", 47.61, -122.33, "America/Los_Angeles"),
        ("Chicago", "Illinois", "IL", "60601", 41.88, -87.63, "America/Chicago"),
        ("Denver", "Colorado", "CO", "80202", 39.74, -104.99, "America/Denver"),
        ("Boston", "Massachusetts", "MA", "02108", 42.36, -71.06, "America/New_York"),
        ("Miami", "Florida", "FL", "33101", 25.76, -80.19, "America/New_York"),
        ("Ashburn", "Virginia", "VA", "20147", 39.04, -77.49, "America/New_York")]),
    ("GB", "United Kingdom", "EU", "Europe", 0.08, [
        ("London", "England", "ENG", "EC1A", 51.51, -0.13, "Europe/London"),
        ("Manchester", "England", "ENG", "M1", 53.48, -2.24, "Europe/London")]),
    ("DE", "Germany", "EU", "Europe", 0.06, [
        ("Berlin", "Land Berlin", "BE", "10115", 52.52, 13.40, "Europe/Berlin"),
        ("Munich", "Bavaria", "BY", "80331", 48.14, 11.58, "Europe/Berlin")]),
    ("IN", "India", "AS", "Asia", 0.07, [
        ("Bengaluru", "Karnataka", "KA", "560001", 12.97, 77.59, "Asia/Kolkata"),
        ("Mumbai", "Maharashtra", "MH", "400001", 19.08, 72.88, "Asia/Kolkata")]),
    ("CA", "Canada", "NA", "North America", 0.05, [
        ("Toronto", "Ontario", "ON", "M5H", 43.65, -79.38, "America/Toronto"),
        ("Vancouver", "British Columbia", "BC", "V6B", 49.28, -123.12, "America/Vancouver")]),
    ("FR", "France", "EU", "Europe", 0.04, [("Paris", "Île-de-France", "IDF", "75001", 48.86, 2.35, "Europe/Paris")]),
    ("BR", "Brazil", "SA", "South America", 0.04, [
        ("São Paulo", "São Paulo", "SP", "01000", -23.55, -46.63, "America/Sao_Paulo")]),
    ("AU", "Australia", "OC", "Oceania", 0.03, [
        ("Sydney", "New South Wales", "NSW", "2000", -33.87, 151.21, "Australia/Sydney")]),
    ("NL", "Netherlands", "EU", "Europe", 0.03, [
        ("Amsterdam", "North Holland", "NH", "1012", 52.37, 4.90, "Europe/Amsterdam")]),
    ("ES", "Spain", "EU", "Europe", 0.025, [("Madrid", "Madrid", "MD", "28001", 40.42, -3.70, "Europe/Madrid")]),
    ("SG", "Singapore", "AS", "Asia", 0.02, [("Singapore", "Central Singapore", "01", "018956", 1.29, 103.85, "Asia/Singapore")]),
    ("JP", "Japan", "AS", "Asia", 0.02, [("Tokyo", "Tokyo", "13", "100-0001", 35.68, 139.69, "Asia/Tokyo")]),
    ("MX", "Mexico", "NA", "North America", 0.02, [("Mexico City", "Mexico City", "CMX", "06000", 19.43, -99.13, "America/Mexico_City")]),
    ("IL", "Israel", "AS", "Asia", 0.01, [("Tel Aviv", "Tel Aviv", "TA", "61000", 32.08, 34.78, "Asia/Jerusalem")]),
    ("KR", "South Korea", "AS", "Asia", 0.01, [("Seoul", "Seoul", "11", "04524", 37.57, 126.98, "Asia/Seoul")]),
    ("PL", "Poland", "EU", "Europe", 0.01, [("Warsaw", "Mazovia", "14", "00-001", 52.23, 21.01, "Europe/Warsaw")]),
    ("SE", "Sweden", "EU", "Europe", 0.01, [("Stockholm", "Stockholm", "AB", "111 20", 59.33, 18.07, "Europe/Stockholm")]),
    ("NG", "Nigeria", "AF", "Africa", 0.01, [("Lagos", "Lagos", "LA", "100001", 6.52, 3.38, "Africa/Lagos")]),
]
# For projects with a non-US timezone, tilt the geography toward that region.
TZ_COUNTRY_TILT = {
    "Asia/Kolkata": "IN", "Europe/Berlin": "DE", "Europe/London": "GB", "Australia/Sydney": "AU", "Asia/Seoul": "KR",
    "Asia/Tokyo": "JP", "America/Sao_Paulo": "BR", "Asia/Singapore": "SG", "Asia/Jerusalem": "IL", "Israel": "IL",
    "Europe/Paris": "FR", "Europe/Amsterdam": "NL", "Asia/Shanghai": "SG", "Asia/Hong_Kong": "SG",
    "Australia/Adelaide": "AU", "Australia/Perth": "AU", "NZ": "AU", "Europe/Athens": "PL", "Africa/Lagos": "NG",
    "Asia/Jakarta": "SG", "Asia/Bangkok": "SG",
}
REFERRERS = [("$direct", 0.45), ("https://www.google.com/", 0.3), ("https://www.bing.com/", 0.03),
             ("https://t.co/", 0.03), ("https://www.linkedin.com/", 0.04), ("https://news.ycombinator.com/", 0.02),
             ("https://duckduckgo.com/", 0.02), ("https://www.reddit.com/", 0.03), ("https://github.com/", 0.04),
             ("https://chatgpt.com/", 0.04)]
SEARCH_ENGINES = {"www.google.com": "google", "www.bing.com": "bing", "duckduckgo.com": "duckduckgo"}
UTM_SOURCES = [("google", 0.35), ("newsletter", 0.15), ("linkedin", 0.12), ("twitter", 0.1), ("facebook", 0.1),
               ("partner", 0.08), ("producthunt", 0.05), ("reddit", 0.05)]
UTM_MEDIUMS = {"google": "cpc", "newsletter": "email", "linkedin": "social", "twitter": "social",
               "facebook": "paid_social", "partner": "referral", "producthunt": "referral", "reddit": "social"}
UTM_CAMPAIGNS = ["spring_launch", "brand", "retargeting", "webinar", "q3_promo", "onboarding_drip", "black_friday"]
WEB_LIBS = [("web", 0.9, "1.2"), ("posthog-node", 0.06, "4.2"), ("posthog-python", 0.04, "3.6")]
MOBILE_LIBS = [("posthog-ios", 0.5, "3.13"), ("posthog-android", 0.35, "3.9"), ("posthog-react-native", 0.15, "3.3")]
FIRST_NAMES = ["Ava", "Liam", "Noah", "Emma", "Olivia", "Mia", "Lucas", "Amir", "Priya", "Chen", "Sofia", "Mateo",
               "Hana", "Yuki", "Leo", "Zara", "Omar", "Ines", "Kai", "Nora", "Ravi", "Elena", "Jonas", "Maya",
               "Theo", "Ana", "Felix", "Lena", "Sam", "Ivy", "Diego", "Aisha", "Tom", "Grace", "Ben", "Chloe"]
LAST_NAMES = ["Smith", "Garcia", "Chen", "Patel", "Kim", "Nguyen", "Müller", "Rossi", "Silva", "Cohen", "Okafor",
              "Johnson", "Brown", "Lee", "Martin", "Lopez", "Wilson", "Tanaka", "Novak", "Haddad", "Singh", "Clark"]
EMAIL_DOMAINS = [("gmail.com", 0.45), ("outlook.com", 0.06), ("yahoo.com", 0.05), ("icloud.com", 0.05),
                 ("company", 0.39)]  # "company" -> a per-project fake company domain
COMPANY_WORDS = ["acme", "globex", "initech", "umbrella", "hooli", "vandelay", "stark", "wayne", "tyrell", "soylent",
                 "cyberdyne", "wonka", "oscorp", "aperture", "massive", "pied", "dunder", "monarch", "nakatomi"]
PLANS = [("free", 0.62), ("starter", 0.15), ("pro", 0.14), ("team", 0.06), ("enterprise", 0.03)]
AI_MODELS = [("gpt-4o-mini", 0.3, "openai"), ("gpt-4.1", 0.15, "openai"), ("claude-sonnet-4-5", 0.25, "anthropic"),
             ("claude-haiku-4-5", 0.1, "anthropic"), ("gemini-2.5-flash", 0.12, "google"), ("o4-mini", 0.08, "openai")]
EXCEPTION_TYPES = [("TypeError", "Cannot read properties of undefined (reading 'map')", 0.3),
                   ("Error", "Network request failed", 0.2), ("ReferenceError", "x is not defined", 0.1),
                   ("UnhandledRejection", "Non-Error promise rejection captured", 0.15),
                   ("SyntaxError", "Unexpected token '<'", 0.1), ("ChunkLoadError", "Loading chunk failed", 0.15)]
GROUP_TYPE_NAMES = ["organization", "company", "project", "workspace", "team"]
DEFAULT_PATHS = ["/", "/pricing", "/login", "/signup", "/dashboard", "/settings", "/docs", "/blog", "/features",
                 "/about", "/onboarding", "/account", "/billing", "/integrations", "/search", "/contact"]
WEB_VITALS = {"$web_vitals_LCP_value": (2200, 0.5), "$web_vitals_FCP_value": (1400, 0.5),
              "$web_vitals_CLS_value": (0.05, 0.9), "$web_vitals_INP_value": (180, 0.6)}
