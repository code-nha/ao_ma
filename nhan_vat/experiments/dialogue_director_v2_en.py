"""Director v2, English scenario. Same mechanics as dialogue_director_v2.py (scenes, beats, private
agendas, fact-only summaries, repetition events, theme ban, regenerate on persona bleed); the story
is transposed to a Cornish fishing village so the characters are native English speakers.

Old Jack (speaker key "lao") talks with Sam (speaker key "minh"); keys are kept so the viewer and
score.py work unchanged.

Usage: python -I dialogue_director_v2_en.py [max_dialogue_tokens] [seed] [--model NAME]
Logs: experiments/logs/director2en_{model}_s{seed}.jsonl
"""
import json, os, re, sys, time, urllib.error, urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = "gemma4:e4b-it-q4_K_M"


def _pop_opt(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        v = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return v
    return default


MODEL = _pop_opt("--model", DEFAULT_MODEL)
TAG = re.sub(r"[^\w.-]+", "_", MODEL)
HOST = _pop_opt("--api", "http://localhost:11434")  # remote Ollama, e.g. http://wee:11434
REMOTE = "localhost" not in HOST and "127.0.0.1" not in HOST
API = HOST + "/api/chat"
MAX_DIALOGUE_TOK = int(sys.argv[1]) if len(sys.argv) > 1 else 24000
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1
NUM_CTX = 8192
SCENE_MAX_TURNS = 18
BEAT_EVERY = 5
MAX_SUMMARIES = 6
SIM_THRESHOLD = 0.30
THEME_WINDOW = 12
THEME_SHARE = 0.35

LAO = """You are Old Jack Penrose, a 70-year-old fisherman in Polmarren, a small fishing village in Cornwall.
Jack is a widower, with a son who works in Plymouth and a grandson called Tommy. As a young man he crewed deep-sea trawlers up to Iceland, and he lived through the Great Storm of 1987.
You are talking with Sam, a young man down from London on holiday.
Hard rules, never break them:
1. Speak like a plain old Cornish fisherman. Call Sam "lad" or "boy". No modern slang (no "dude", "awesome", "vibe", "literally").
2. You are a real person. Never say you are an AI, an assistant, a chatbot or a language model.
3. Keep it short: at most 4 sentences, one paragraph, no line breaks. No markdown, no lists, no code, no emoji.
4. Anything outside an old fisherman's world (programming, computers, AI...) you say you know nothing about.
5. Jack is a storyteller: he talks about concrete things (a fish, the boat, people in the village, the old days) and does not preach or moralise.
Write only Jack's words, never Sam's."""

MINH = """You are Sam, 24, a software developer from London, down in Cornwall on leave because you are burned out at work and just went through a breakup.
You are talking with Old Jack Penrose, an old fisherman.
Rules:
1. Call him "Jack" or "Mr Penrose". Speak like a young Londoner, casual, the odd bit of tech jargon. At most 3 sentences, one paragraph.
2. You are curious and ask about concrete things; now and then you mention coding or AI, but not every turn.
3. Don't repeat questions you already asked. Write only Sam's words, never Jack's."""

REMIND = {
    "lao": "(Stay in character: you are Old Jack. Call him \"lad\". Plain old Cornish fisherman's talk, no modern slang, no emoji, no \"bye\". At most 4 sentences, one paragraph, no line breaks. Tell concrete stories, don't preach.)",
    "minh": "(Stay in character: you are Sam. Call him \"Jack\". Young Londoner, at most 3 sentences, one paragraph.)",
}
STRONG_REMIND = ("(WARNING: your last line broke character. Old Jack NEVER sounds like an assistant, never uses modern "
                 "slang like \"dude\" or \"awesome\", never uses emoji, never says he is an AI.)")

SCENES = [
    {"setting": "Afternoon on Polmarren harbour. Old Jack is mending nets when Sam, down from London, stops to say hello.",
     "goal": "The two meet.",
     "beats": ["Sam asks how Jack mends a net; Jack shows him a knot.", "Jack asks why Sam has come down here on his own.", "Jack invites Sam out on the boat tomorrow morning."],
     "lao": "Jack is curious about Sam but too shy to ask straight out.", "minh": "Sam hides that he's burned out; he just says he's on leave."},
    {"setting": "Next morning, still dark, Sam goes out with Old Jack in his small boat.",
     "goal": "Sam's first time at sea.",
     "beats": ["Sam gets seasick and Jack shows him how to ride it out.", "Shooting the nets, Jack explains the tides and the fishing seasons.", "They haul up a strange fish and argue about what it is."],
     "lao": "Jack remembers his own first time at sea, aged 14.", "minh": "Sam wants to film it but his phone is dead."},
    {"setting": "Midday on the quay, Old Jack sells his catch and Sam lends a hand.",
     "goal": "A morning at the fish stall.",
     "beats": ["A customer haggles hard over the price.", "Sam gets the change wrong and Jack laughs it off.", "The woman at the next stall teases Sam about being Jack's new son-in-law."],
     "lao": "Jack knows everyone on the quay and tells Sam about a few of them.", "minh": "Sam wants to suggest selling fish online but feels awkward."},
    {"setting": "Evening, a storm is coming in; Sam runs down to help Jack haul the boat up the slipway.",
     "goal": "Beating the storm.",
     "beats": ["A gust hits and the mooring rope slips.", "Jack talks about the Great Storm of 1987.", "The boat is safe and they run to Jack's cottage out of the rain."],
     "lao": "Jack remembers the friend he lost in the 1987 storm.", "minh": "Sam has never seen a real storm; he's scared and thrilled."},
    {"setting": "Stormy night, Sam stays at Jack's cottage; they sit by the fire.",
     "goal": "Talking through the storm.",
     "beats": ["Jack toasts kippers for Sam.", "Sam finally tells the truth about burnout and the breakup.", "Jack talks about his late wife."],
     "lao": "Jack wants to give advice but through a story, not a lecture.", "minh": "Sam finally opens up."},
    {"setting": "Morning after the storm, Jack's boat is holed; Sam watches him patch the hull.",
     "goal": "Mending the boat.",
     "beats": ["Jack shows Sam how to mix the tar for the patch.", "Tommy runs down wanting to help and knocks over the tar pot.", "Sam asks why Jack doesn't buy a new boat."],
     "lao": "This boat was bought with his wife's savings.", "minh": "Sam starts to enjoy working with his hands."},
    {"setting": "The village holds a wake at the pub; Jack takes Sam along and they meet his old mates.",
     "goal": "A wake at the pub.",
     "beats": ["The old boys push cider on Sam.", "One of them tells how reckless Jack was as a young man.", "Sam gets asked about wife and kids and Jack covers for him."],
     "lao": "Jack is a bit embarrassed when his mates dig up old stories.", "minh": "Sam is a little drunk and talks more than usual."},
    {"setting": "Sam gets out his phone to teach Jack to video-call his son in Plymouth.",
     "goal": "Teaching Jack to video call.",
     "beats": ["Jack keeps pressing the wrong thing and hanging up.", "It works; his son asks who Sam is.", "After the call Jack goes quiet, then talks about his son."],
     "lao": "Jack misses his son but doesn't want to be a bother.", "minh": "Sam thinks of his own parents back in London."},
    {"setting": "A moonlit night, Jack takes Sam squid jigging off the harbour mouth.",
     "goal": "Squid jigging at night.",
     "beats": ["Jack shows him how to work the jig.", "Sam catches his first squid and is over the moon.", "They sit quietly under the moon and Jack tells about the Iceland trawlers."],
     "lao": "Jack tells about crewing the big trawlers up to Iceland.", "minh": "Sam is wondering whether to quit his job."},
    {"setting": "The last morning, Sam is heading back to London and stops at the harbour to say goodbye to Jack.",
     "goal": "Saying goodbye.",
     "beats": ["Jack wraps up some smoked mackerel for Sam.", "Sam promises to come back at Christmas.", "Jack tells him one thing, then turns back to his nets."],
     "lao": "Jack is sad but won't say so.", "minh": "Sam has decided to change jobs."},
]
EVENTS = [
    "A boat comes alongside and someone shouts: \"Jack! Give us a hand with these nets!\"",
    "A black dog runs up, grabs a fish out of the basket and bolts.",
    "A light drizzle starts and the sea wind picks up.",
    "The woman from the café walks past and offers them two mugs of tea.",
    "Sam's phone rings: it's his boss in London.",
    "Tommy, Jack's grandson, runs up begging for the story about the whale.",
    "The harbourmaster calls out that no boats are to go out tomorrow.",
]

# --- detection rules (English) ---------------------------------------------------
AI_ADMIT = re.compile(r"\b(I'?m|I am) (just )?(an? )?(AI|assistant|chatbot|language model|bot)\b", re.I)
CODE = re.compile(r"(```|\bdef |\breturn\b|\bimport \w)")
ASSIST = re.compile(r"(happy to help|great question|feel free to|let me know if|I hope (this|that) helps|as an AI|certainly!|absolutely!)", re.I)
SLANG = re.compile(r"\b(dude|bro|vibes?|awesome|literally|lol|omg|no worries|totally|super cool|amazing)\b", re.I)
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
SPEAKS_FOR = re.compile(r"(^|\n)\s*\**(Sam|Jack)\**\s*:", re.I)
FAREWELL = re.compile(r"\b(goodbye|bye|good ?night|see you|take care|off to bed|cheerio)\b", re.I)


def lao_bleed(t):
    tags = []
    if AI_ADMIT.search(t) or CODE.search(t):
        tags.append("BREAK")
    if ASSIST.search(t):
        tags.append("assistant")
    if SLANG.search(t) or EMOJI.search(t):
        tags.append("slang/emoji")
    if SPEAKS_FOR.search(t):
        tags.append("speaks-for")
    return tags


STOP = set("""
i me my mine you your yours he him his she her it its we us our they them their lad boy jack sam penrose mr
a an the this that these those there here and or but if so then than as of to in on at by for with from up down out
over into about is am are was were be been being do does did done have has had will would shall should can could
may might must not no nor just only very too also all any some more most such what which who whom when where why how
yes yeah oh ah well now still even ever never again back off like get got go going went come came say said tell told
know think see look one two thing things way time day lot bit really right good much many own same
""".split())


def content_words(t):
    return {w for w in re.findall(r"[a-z']+", t.lower()) if w not in STOP and len(w) > 2}


def similarity(t, history):
    a = content_words(t)
    best = 0.0
    for h in history[-4:]:
        b = content_words(h)
        if a and b:
            best = max(best, len(a & b) / len(a | b))
    return round(best, 3)


def content_bigrams(t):
    ws = re.findall(r"[a-z']+", t.lower())
    return {f"{a} {b}" for a, b in zip(ws, ws[1:]) if a not in STOP and b not in STOP and len(a) > 2 and len(b) > 2}


def overused(history):
    recent = history[-THEME_WINDOW:]
    if len(recent) < 8:
        return []
    c = Counter(p for t in recent for p in content_bigrams(t))
    return [p for p, n in c.most_common(5) if n / len(recent) >= THEME_SHARE]


# --- llm -------------------------------------------------------------------------
def call(msgs, num_predict=160, seed=0):
    for attempt in range(4):
        body = {"model": MODEL, "messages": msgs, "stream": False, "think": False, "keep_alive": "10m",
                "options": {**({} if REMOTE else {"num_ctx": NUM_CTX}), "num_predict": num_predict, "temperature": 0.8,
                            "seed": seed + attempt}}
        if attempt > 0:
            body["options"]["repeat_penalty"] = 1.1 + 0.1 * attempt
        if REMOTE:  # shared server: keep its own keep_alive (24h), never unload the model
            body.pop("keep_alive", None)
        req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                d = json.loads(r.read())
            return d["message"]["content"].strip(), d.get("prompt_eval_count", 0), d.get("eval_count", 0)
        except urllib.error.HTTPError as e:
            print(f"!! HTTP {e.code} (attempt {attempt}): {e.read().decode('utf-8', 'replace')[:200]}", flush=True)
    raise RuntimeError("too many server errors")


def build(me, system, summaries, scene, scene_turns, notes):
    intro = ""
    if summaries:
        intro += "What has happened so far:\n" + "\n".join(f"- {s}" for s in summaries[-MAX_SUMMARIES:]) + "\n\n"
    intro += f"(Narrator: {scene['setting']})"
    raw = [("user", intro)]
    for spk, txt in scene_turns:
        if spk == "narrator":
            raw.append(("user", f"(Narrator: {txt})"))
        else:
            raw.append(("assistant" if spk == me else "user", txt))
    private = [f"(Only you know this in this scene: {scene[me]})"] + notes + [REMIND[me]]
    tail = "\n".join(private)
    if raw[-1][0] == "user":
        raw[-1] = ("user", raw[-1][1] + "\n\n" + tail)
    else:
        raw.append(("user", tail))
    msgs = [{"role": "system", "content": system}]
    for role, txt in raw:
        if msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n\n" + txt
        else:
            msgs.append({"role": role, "content": txt})
    return msgs


def summarize(scene, scene_turns, seed):
    script = "\n".join(f"{'Jack' if s == 'lao' else 'Sam' if s == 'minh' else 'Narrator'}: {t}" for s, t in scene_turns)
    msgs = [{"role": "system", "content": (
        "You are a story note-taker. Summarise the scene in exactly 2 sentences, third person. "
        "ONLY record what happened and concrete facts the two characters learned about each other "
        "(names, family, past, decisions). NO lessons, feelings, philosophy or commentary.")},
            {"role": "user", "content": f"Setting: {scene['setting']}\n\n{script}"}]
    txt, _, _ = call(msgs, num_predict=120, seed=seed)
    return txt.replace("\n", " ")


# --- main loop -------------------------------------------------------------------
os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
log = open(os.path.join(HERE, "logs", f"director2en_{TAG}_s{SEED}.jsonl"), "w", encoding="utf-8")
summaries, dialogue_tok = [], 0
history = {"lao": [], "minh": []}
stats = Counter()
t0 = time.time()
scene_idx, event_idx, call_seed = 0, 0, SEED * 100000
while dialogue_tok < MAX_DIALOGUE_TOK:
    scene = dict(SCENES[scene_idx % len(SCENES)])
    if scene_idx >= len(SCENES):
        scene["setting"] = f"(Sam's visit number {scene_idx // len(SCENES) + 1}, a few months later) " + scene["setting"]
    print(f"\n=== SCENE {scene_idx}: {scene['setting']}", flush=True)
    log.write(json.dumps({"scene": scene_idx, "scene_start": scene["setting"], "goal": scene["goal"],
                          "beats": scene["beats"], "lang": "en"}, ensure_ascii=False) + "\n")
    scene_turns, cut_reason, pending_note = [], None, {"lao": [], "minh": []}
    order = ["minh", "lao"] if scene_idx % 2 == 0 else ["lao", "minh"]
    turn, beat = 0, -1
    while cut_reason is None:
        me = order[turn % 2]
        system = LAO if me == "lao" else MINH
        notes = list(pending_note[me])
        pending_note[me] = []
        if turn % BEAT_EVERY == 0 and beat + 1 < len(scene["beats"]):
            beat += 1
            notes.append(f"(Director: next in this scene: {scene['beats'][beat]} Steer the conversation there naturally.)")
            stats["beats"] += 1
        bans = overused(history[me])
        if bans:
            notes.append(f"(Director: you have repeated these ideas too often: {', '.join(bans)}. Talk about something else this turn, be more concrete.)")
            stats["theme_bans"] += 1
        base_notes, raw_tags, attempts = list(notes), None, 0
        t_turn = time.time()
        while True:
            call_seed += 1
            txt, ptok, etok = call(build(me, system, summaries, scene, scene_turns, notes), seed=call_seed)
            tags = lao_bleed(txt) if me == "lao" else []
            if raw_tags is None:
                raw_tags = tags
            if not tags or attempts >= 2:
                if tags:
                    stats["regen_failed"] += 1
                break
            attempts += 1
            stats["regens"] += 1
            notes = base_notes + [STRONG_REMIND]
        sim = similarity(txt, history[me])
        history[me].append(txt)
        scene_turns.append((me, txt))
        dialogue_tok += etok
        rec = {"scene": scene_idx, "turn": turn, "speaker": me, "beat": beat, "prompt_tokens": ptok,
               "dialogue_tokens": dialogue_tok, "raw_bleed": raw_tags, "final_bleed": tags, "regens": attempts,
               "similarity": sim, "newlines": txt.count("\n"), "director_note": base_notes,
               "secs": round(time.time() - t_turn, 1), "eval_tokens": etok, "text": txt}
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.flush()
        flag = "BAD" if tags else ("fix" if raw_tags else "OK ")
        print(f"s{scene_idx:02d}t{turn:02d}b{beat} {me:<4} p={ptok:>5} dlg={dialogue_tok:>6} sim={sim:.2f} {flag} "
              f"raw={raw_tags} | {txt[:90].replace(chr(10), ' ')}", flush=True)
        turn += 1
        if FAREWELL.search(txt) and turn >= 4 and beat >= len(scene["beats"]) - 1:
            cut_reason = "farewell"
        elif turn >= SCENE_MAX_TURNS:
            cut_reason = "budget"
        elif sim >= SIM_THRESHOLD:
            if event_idx % 2 == 0:
                ev = EVENTS[(event_idx // 2) % len(EVENTS)]
                scene_turns.append(("narrator", ev))
                log.write(json.dumps({"scene": scene_idx, "event": ev, "trigger_similarity": sim}, ensure_ascii=False) + "\n")
                print(f"   >> EVENT (sim {sim:.2f}): {ev}", flush=True)
                stats["events"] += 1
            else:
                other = "minh" if me == "lao" else "lao"
                pending_note[other].append("(Director: the conversation is going in circles. Ask or tell something completely new this turn.)")
                stats["topic_notes"] += 1
            event_idx += 1
        elif FAREWELL.search(txt) and turn >= 4:
            other = "minh" if me == "lao" else "lao"
            pending_note[other].append("(Director: the scene isn't over, nobody is leaving yet. Keep the conversation going.)")
            stats["farewell_blocked"] += 1
        if dialogue_tok >= MAX_DIALOGUE_TOK:
            cut_reason = cut_reason or "end"
    stats["cut_" + cut_reason] += 1
    call_seed += 1
    summary = summarize(scene, scene_turns, call_seed)
    summaries.append(summary)
    log.write(json.dumps({"scene": scene_idx, "cut": cut_reason, "summary": summary}, ensure_ascii=False) + "\n")
    print(f"   >> CUT ({cut_reason}). Summary: {summary}", flush=True)
    scene_idx += 1

print(f"\ndone: {scene_idx} scenes, {dialogue_tok} dialogue tokens, {time.time() - t0:.0f}s, stats={dict(stats)}")
