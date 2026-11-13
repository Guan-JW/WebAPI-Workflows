"""Per-request checks for AudioTour (README "Measurement"), computed from the recorded HTTP calls.

classify()  names the Responses-API calls by the agent instructions they carry.
dataflow()  checks that the tour and the audio were produced from this request's own responses:
            the orchestrator prompt contains the research outputs in the app's order, the tour is
            the orchestrator's sections joined as manager.py L78-95 does, the speech request's input
            is the tour, and the returned audio is the speech response body.
mp3_seconds() decodes MPEG audio frame headers to get the duration (no dependencies).
"""
import hashlib
import json

AGENTS = [("planner", "You are the Planner Agent"), ("architecture", "You are the Architecture agent"),
          ("history", "You are the History agent"), ("culture", "You are the Culture agent"),
          ("culinary", "You are the Culinary agent"), ("orchestrator", "You are the Orchestrator Agent")]
SECTION_ORDER = ["Architecture", "History", "Culture", "Culinary"]   # manager.py L81-88


def classify(calls):
    """{name: HttpCall} for the successful calls of one request (the last one per name)."""
    out = {}
    for c in calls:
        if c.status != 200 or not c.req_body:
            continue
        if c.path().endswith("/v1/audio/speech"):
            out["tts"] = c
        elif c.path().endswith("/v1/responses"):
            instr = (json.loads(c.req_body.decode("utf-8")).get("instructions") or "")
            for name, marker in AGENTS:
                if marker in instr:
                    out[name] = c
                    break
    return out


def _structured_output(call):
    """The JSON object in the last output message of a Responses-API response body."""
    d = json.loads(call.resp_body.decode("utf-8"))
    msgs = [it for it in d.get("output", []) if it.get("type") == "message"]
    text = "".join(c.get("text", "") for c in msgs[-1].get("content", []) if c.get("type") == "output_text")
    return json.loads(text)


def _prompt_text(inp):
    if isinstance(inp, str):
        return inp
    parts = []
    for m in inp or []:
        c = m.get("content")
        parts.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    return "\n".join(parts)


def dataflow(calls, interests, tour, audio):
    out = {}
    try:
        research = {k: _structured_output(calls[k])["output"] for k in ("architecture", "history", "culture", "culinary")
                    if calls.get(k) is not None}
        orch = calls["orchestrator"]
        sections = [research[i.lower()] for i in interests if i.lower() in research]       # manager.py L168-171
        prompt = _prompt_text(json.loads(orch.req_body.decode("utf-8")).get("input"))
        out["orchestrator_input_ok"] = "\n\n".join(sections) in prompt
        ft = _structured_output(orch)
        out["tour_assembly_ok"] = tour == "\n\n".join(ft[s.lower()] for s in SECTION_ORDER if s in interests)
    except Exception as e:  # noqa: BLE001  a missing call or malformed body fails the check
        out["error"] = f"{type(e).__name__}: {e}"[:200]
    tts = calls.get("tts")
    out["tts_ok"] = bool(tts is not None and json.loads(tts.req_body.decode("utf-8")).get("input") == tour
                         and tts.resp_body is not None
                         and hashlib.sha256(audio).hexdigest() == hashlib.sha256(tts.resp_body).hexdigest())
    out["ok"] = all(out.get(k) is True for k in ("orchestrator_input_ok", "tour_assembly_ok", "tts_ok"))
    return out


_BITRATE = {3: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
            2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]}
_RATE = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def mp3_seconds(b):
    """Duration of MPEG-1/2/2.5 Layer III audio from its frame headers (skips an ID3v2 tag)."""
    i, secs = 0, 0.0
    if b[:3] == b"ID3" and len(b) >= 10:
        i = 10 + ((b[6] & 0x7F) << 21 | (b[7] & 0x7F) << 14 | (b[8] & 0x7F) << 7 | (b[9] & 0x7F))
    while i + 4 <= len(b):
        h = int.from_bytes(b[i:i + 4], "big")
        ver, layer, bri, sri, pad = (h >> 19) & 3, (h >> 17) & 3, (h >> 12) & 15, (h >> 10) & 3, (h >> 9) & 1
        if (h >> 21) != 0x7FF or ver == 1 or layer != 1 or bri in (0, 15) or sri == 3:
            i += 1
            continue
        sr = _RATE[ver][sri]
        spf = 1152 if ver == 3 else 576
        secs += spf / sr
        i += (spf // 8) * _BITRATE[3 if ver == 3 else 2][bri] * 1000 // sr + pad
    return secs
