"""Exercise name -> muscle buckets for the movement balance screen. Used AI to think through this architecture as the granularity got complex."""

import re

# leaf -> (group, pattern), so the small buckets can roll up cleanly.
LEAVES = {
    "upper_chest": ("chest", "upper_push"),
    "mid_chest": ("chest", "upper_push"),
    "lower_chest": ("chest", "upper_push"),
    "front_delts": ("shoulders", "upper_push"),
    "side_delts": ("shoulders", "upper_push"),
    "triceps": ("triceps", "upper_push"),
    "lats": ("back", "upper_pull"),
    "mid_back": ("back", "upper_pull"),
    "rear_delts": ("shoulders", "upper_pull"),
    "biceps": ("biceps", "upper_pull"),
    "quad_compound": ("quads", "lower_push"),
    "quad_isolation": ("quads", "lower_push"),
    "adductors": ("adductors", "lower_push"),
    "glutes": ("glutes", "lower_pull"),
    "ham_hinge": ("hamstrings", "lower_pull"),
    "ham_curl": ("hamstrings", "lower_pull"),
    "abductors": ("abductors", "lower_pull"),
    "calves": ("calves", "lower_pull"),
    "abs": ("core", "core"),
    "obliques": ("core", "core"),
    "lower_back": ("core", "core"),
}

# 1.0 for the main muscle, 0.5 for the stuff helping.
def P(leaf): return (leaf, 1.0)
def S(leaf): return (leaf, 0.5)

_BRANDS = (
    "m torture", "mtorture", "mts", "atlantis", "newtech", "new tech", "prime",
    "pendulum", "plate", "arsenal", "iso lateral", "isolateral", "hammer strength",
    "life fitness", "smith", "machine", "cable", "dumbbell", "barbell", "db",
)
_BRAND_RE = re.compile(r"\b(" + "|".join(_BRANDS) + r")\b")


def normalize(name):
    """Strip the equipment/brand noise before matching."""
    s = (name or "").lower()
    s = re.sub(r"\([^)]*\)", " ", s)      # drop stuff like "(Machine)"
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = _BRAND_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


# names I want pinned exactly instead of trusting the fallback.
EXERCISE_MAP = {
    "incline bench": {"targets": [P("upper_chest"), S("front_delts"), S("triceps")], "mechanic": "compound"},
    "hip thrust": {"targets": [P("glutes"), S("ham_hinge")], "mechanic": "compound"},
    "glute kickback": {"targets": [P("glutes")], "mechanic": "isolation"},
    "pullover": {"targets": [P("lats"), S("mid_chest")], "mechanic": "isolation"},
    "straight arm lat pulldown": {"targets": [P("lats")], "mechanic": "isolation"},
    "kneeling glute isolator": {"targets": [P("glutes")], "mechanic": "isolation"},
    "hip band ladder": {"targets": [P("abductors")], "mechanic": "isolation"},
    "clamshell": {"targets": [P("abductors")], "mechanic": "isolation"},
}

# wrist/grip stuff can stay unmapped for now.
_UNKNOWN_RE = re.compile(r"wrist|gripper")

# first match wins, so specific stuff has to stay above generic stuff.
FALLBACK_RULES = [
    (r"elliptical|treadmill|running|\brun\b|\bbike\b|cycle|rower|stair", None, "cardio"),

    (r"rear delt|reverse fly|bent over.*(lateral|rear)|reverse pec", [P("rear_delts")], "isolation"),
    (r"face pull", [P("rear_delts")], "isolation"),
    (r"upright\s*row", [P("side_delts"), S("mid_back")], "compound"),
    (r"front raise|front delt", [P("front_delts")], "isolation"),
    (r"lateral raise|side raise|\by raise\b|lat raise", [P("side_delts")], "isolation"),
    (r"shrug", [P("mid_back")], "isolation"),
    (r"shoulder press|overhead press|\bohp\b|military|bradford", [P("front_delts"), S("triceps"), S("side_delts")], "compound"),

    (r"incline.*(bench|press|chest|fly|pec)", [P("upper_chest"), S("front_delts"), S("triceps")], "compound"),
    (r"decline.*(bench|press|chest|push)", [P("lower_chest"), S("triceps")], "compound"),
    (r"chest dip", [P("lower_chest"), S("triceps")], "compound"),
    (r"pec dec|chest fly|cable fly|\bfly\b|\bpec\b", [P("mid_chest")], "isolation"),
    (r"bench|chest press|push\s*up|\bpress\b", [P("mid_chest"), S("front_delts"), S("triceps")], "compound"),

    (r"tricep|pushdown|skull\s*crusher|rope extension|overhead.*extension|\bdip\b", [P("triceps")], "isolation"),

    (r"leg curl|ham.*curl", [P("ham_curl")], "isolation"),
    (r"leg extension|\bquad\b", [P("quad_isolation")], "isolation"),
    (r"calf|calves", [P("calves")], "isolation"),
    (r"back extension|45 degree back|hyperextension", [P("lower_back")], "isolation"),

    (r"bicep|preacher|spider|\bcurl\b", [P("biceps")], "isolation"),

    (r"pullover", [P("lats"), S("mid_chest")], "isolation"),
    (r"pulldown|pull\s*up|chin|lat pull", [P("lats"), S("biceps")], "compound"),
    (r"\brow\b|seal row|t\s*bar|high row|low row|seated row", [P("mid_back"), S("lats"), S("biceps"), S("rear_delts")], "compound"),

    (r"adduction|adductor", [P("adductors")], "isolation"),
    (r"abduction|abductor|clamshell|hip band", [P("abductors")], "isolation"),
    (r"squat|hack|leg press|lunge|step up|belt squat", [P("quad_compound"), S("glutes"), S("adductors")], "compound"),

    (r"rdl|romanian|deadlift|good morning|\bhinge\b", [P("ham_hinge"), S("glutes"), S("lower_back")], "compound"),
    (r"glute|hip thrust|kickback|bridge", [P("glutes")], "isolation"),

    (r"rotation|pallof|twist|oblique|woodchop|side plank", [P("obliques")], "isolation"),
    (r"crunch|sit\s*up|ab wheel|\bab\b|abs|plank|leg raise|bird\s*dog", [P("abs")], "isolation"),
    (r"carry|farmer|suitcase", [P("abs")], "compound"),
]
FALLBACK_RULES = [(re.compile(p), t, m) for p, t, m in FALLBACK_RULES]


def classify(name):
    """Return targets/mechanic/source for one exercise name."""
    norm = normalize(name)
    if norm in EXERCISE_MAP:
        hit = EXERCISE_MAP[norm]
        return {"targets": hit["targets"], "mechanic": hit["mechanic"], "source": "exact"}
    if _UNKNOWN_RE.search(norm):
        return {"targets": [], "mechanic": None, "source": "unknown"}
    for rx, targets, mechanic in FALLBACK_RULES:
        if rx.search(norm):
            return {"targets": targets or [], "mechanic": mechanic, "source": "fallback"}
    return {"targets": [], "mechanic": None, "source": "unknown"}
