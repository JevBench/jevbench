"""Security operations: an alert or report reaches a company's security team."""

from __future__ import annotations

from jevbench.datagen.spec import UNKNOWN, Archetype, Domain, Fact, Question, known

FACTS = (
    Fact("incident", "cat", "what kind of security event this is: repeated password guessing against an account "
         "(brute_force), a deceptive email reported by an employee (phishing), malicious software detected on a "
         "machine (malware), or data copied out of the company (exfiltration)",
         values=("brute_force", "phishing", "malware", "exfiltration"), always=True,
         topic="what kind of security event this is",
         labels={"brute_force": "repeated password guessing against one account",
                 "phishing": "an employee reports a deceptive email",
                 "malware": "malicious software detected on a machine",
                 "exfiltration": "data being copied out of the company"}),
    Fact("failed_logins", "int", "how many failed login attempts were seen", lo=5, hi=999,
         subject="failed login attempts"),
    Fact("source_ips", "int", "how many distinct source IP addresses the activity came from", lo=1, hi=20,
         subject="source IP addresses"),
    Fact("login_succeeded", "bool", "whether a login succeeded after the failed attempts"),
    Fact("clicked_link", "bool", "whether the employee clicked the link in the email"),
    Fact("entered_credentials", "bool", "whether the employee typed their password on the page the link opened"),
    Fact("quarantined", "bool", "whether the security software quarantined the malicious file"),
    Fact("persistence", "bool", "whether the attacker set up a way to keep access, such as a scheduled task or a "
         "new service"),
    Fact("data_mb", "int", "how many megabytes of data were transferred out", lo=5, hi=9000,
         subject="megabytes transferred"),
    Fact("recipients", "int", "how many employees received the suspicious email", lo=1, hi=400,
         subject="employees who received the email"),
    Fact("hosts", "int", "how many machines the malicious software was found on", lo=1, hi=60,
         subject="machines with the malware"),
    Fact("environment", "cat", "what kind of machine or system is involved",
         values=("production server", "staging server", "employee laptop"), implied_ok=True),
    Fact("mfa", "bool", "whether the affected account has multi-factor authentication enabled"),
    Fact("privileged", "bool", "whether the affected account is an administrator account", implied_ok=True),
)


def _base(rng, **kw):
    f = {"failed_logins": None, "source_ips": None, "login_succeeded": None, "clicked_link": None,
         "entered_credentials": None, "quarantined": None, "persistence": None, "data_mb": None,
         "recipients": None, "hosts": None,
         "environment": rng.choice(("production server", "staging server", "employee laptop")),
         "mfa": rng.random() < 0.5, "privileged": rng.random() < 0.3}
    f.update(kw)
    return f


def _phishing(rng):
    clicked = rng.random() < 0.6
    return _base(rng, incident="phishing", clicked_link=clicked,
                 entered_credentials=clicked and rng.random() < 0.5, environment="employee laptop",
                 recipients=rng.choice((1, rng.randint(2, 20), rng.randint(21, 400))))


ARCHETYPES = (
    Archetype("brute_force", "an alert about many failed logins to one account",
              lambda rng: _base(rng, incident="brute_force",
                                failed_logins=rng.choice((rng.randint(5, 49), rng.randint(50, 299), rng.randint(300, 999))),
                                source_ips=rng.choice((1, rng.randint(2, 5), rng.randint(6, 20))),
                                login_succeeded=rng.random() < 0.5, persistence=rng.random() < 0.3)),
    Archetype("phishing", "an employee reports a suspicious email", _phishing),
    Archetype("malware", "endpoint security detects malicious software on a machine",
              lambda rng: _base(rng, incident="malware", quarantined=rng.random() < 0.5,
                                persistence=rng.random() < 0.4,
                                hosts=rng.choice((1, rng.randint(2, 9), rng.randint(10, 60))))),
    Archetype("exfiltration", "monitoring sees data leaving the company to an unknown destination",
              lambda rng: _base(rng, incident="exfiltration", source_ips=rng.choice((1, rng.randint(2, 20))),
                                data_mb=rng.choice((rng.randint(5, 999), rng.randint(1000, 9000))))),
)


def _compromised(f, m):
    """Did the attacker get into the account? UNKNOWN when the text does not settle it."""
    if f["incident"] == "brute_force":
        return known(f, m, "login_succeeded")
    if f["incident"] == "phishing":
        return known(f, m, "entered_credentials")
    return UNKNOWN


def _response(f, m):
    kind = f["incident"]
    if kind == "exfiltration":
        return "isolate_host"
    if kind == "brute_force":
        ok = known(f, m, "login_succeeded")
        if ok == UNKNOWN:
            return UNKNOWN
        if not ok:
            return "monitor"
        persist = known(f, m, "persistence")
        return UNKNOWN if persist == UNKNOWN else ("isolate_host" if persist else "reset_credentials")
    if kind == "phishing":
        entered, clicked = known(f, m, "entered_credentials"), known(f, m, "clicked_link")
        if entered is True:
            return "reset_credentials"
        if clicked is False:
            return "close"
        return "monitor" if (clicked is True and entered is False) else UNKNOWN
    quarantined, persist = known(f, m, "quarantined"), known(f, m, "persistence")
    if UNKNOWN in (quarantined, persist):
        return UNKNOWN
    return "monitor" if quarantined and not persist else "isolate_host"


def _stage(f, m):
    kind = f["incident"]
    if kind == "exfiltration":
        return "exfiltration"
    if kind in ("brute_force", "malware"):
        persist = known(f, m, "persistence")
        if persist is True:
            return "persistence"
        if kind == "malware":
            return UNKNOWN if persist == UNKNOWN else "initial_access"
    got_in = _compromised(f, m)
    if got_in == UNKNOWN:
        return UNKNOWN
    if kind == "brute_force" and got_in and known(f, m, "persistence") == UNKNOWN:
        return UNKNOWN
    return "initial_access" if got_in else "recon"


def _severity(f, m):
    if f["incident"] == "phishing" and known(f, m, "clicked_link") is False:
        return 0
    stage = _stage(f, m)
    if stage == UNKNOWN:
        return UNKNOWN
    base = {"recon": 1, "initial_access": 2, "persistence": 3, "exfiltration": 3}[stage]
    if base == 1:
        return 1
    env = known(f, m, "environment")
    if env == UNKNOWN:
        return UNKNOWN
    return min(4, base + (env == "production server"))


def _account_risk(f, m):
    got_in = _compromised(f, m)
    if got_in == UNKNOWN:
        return UNKNOWN
    if got_in:
        admin = known(f, m, "privileged")
        return UNKNOWN if admin == UNKNOWN else (3 if admin else 2)
    mfa = known(f, m, "mfa")
    return UNKNOWN if mfa == UNKNOWN else (0 if mfa else 1)


def _is(value, target):
    return UNKNOWN if value == UNKNOWN else value == target


QUESTIONS = (
    Question("login_succeeded", "noul", "Was there a successful login after the failed attempts?",
             lambda f, m: known(f, m, "login_succeeded"), ("login_succeeded",),
             applies=lambda f: f["incident"] == "brute_force"),
    Question("credentials_entered", "noul", "Did the employee enter their password on the page the link opened?",
             lambda f, m: known(f, m, "entered_credentials"), ("entered_credentials",),
             applies=lambda f: f["incident"] == "phishing"),
    Question("link_clicked", "noul", "Did the employee click the link in the email?",
             lambda f, m: known(f, m, "clicked_link"), ("clicked_link",),
             applies=lambda f: f["incident"] == "phishing"),
    Question("production_involved", "noul", "Is a production system involved?",
             lambda f, m: _is(known(f, m, "environment"), "production server"), ("environment",)),
    Question("persistence_created", "noul", "Did the attacker set up a way to keep access, such as a scheduled task?",
             lambda f, m: known(f, m, "persistence"), ("persistence",),
             applies=lambda f: f["incident"] in ("brute_force", "malware")),
    Question("file_quarantined", "noul", "Was the malicious file quarantined?",
             lambda f, m: known(f, m, "quarantined"), ("quarantined",), applies=lambda f: f["incident"] == "malware"),
    Question("mfa_enabled", "noul", "Does the affected account have multi-factor authentication enabled?",
             lambda f, m: known(f, m, "mfa"), ("mfa",)),
    Question("admin_account", "noul", "Is the affected account an administrator account?",
             lambda f, m: known(f, m, "privileged"), ("privileged",)),
    Question("many_sources", "noul", "Did the activity come from more than one IP address?",
             lambda f, m: (lambda n: UNKNOWN if n == UNKNOWN else n > 1)(known(f, m, "source_ips")), ("source_ips",),
             applies=lambda f: f["incident"] in ("brute_force", "exfiltration")),
    Question("wide_campaign", "noul", "Did the email reach more than 10 employees?",
             lambda f, m: (lambda n: UNKNOWN if n == UNKNOWN else n > 10)(known(f, m, "recipients")), ("recipients",),
             applies=lambda f: f["incident"] == "phishing"),
    Question("spread", "noul", "Was the malware found on more than one machine?",
             lambda f, m: (lambda n: UNKNOWN if n == UNKNOWN else n > 1)(known(f, m, "hosts")), ("hosts",),
             applies=lambda f: f["incident"] == "malware"),
    Question("large_transfer", "noul", "Was more than 1 GB of data transferred out?",
             lambda f, m: (lambda n: UNKNOWN if n == UNKNOWN else n > 1000)(known(f, m, "data_mb")), ("data_mb",),
             applies=lambda f: f["incident"] == "exfiltration"),
    Question("incident_type", "choice", "What kind of security event is this?",
             lambda f, m: f["incident"], ("incident",),
             criteria={"brute_force": "Repeated password guessing against an account",
                       "phishing": "A deceptive email trying to steal credentials",
                       "malware": "Malicious software found on a machine",
                       "exfiltration": "Data copied out of the company"},
             hierarchy={"account_attack": ["brute_force", "phishing"], "system_attack": ["malware", "exfiltration"]}),
    Question("response", "choice", "What is the right immediate response?", _response,
             ("incident", "login_succeeded", "persistence", "entered_credentials", "clicked_link", "quarantined"),
             criteria={"monitor": "Keep watching; no action yet",
                       "reset_credentials": "Reset the account's password and sessions",
                       "isolate_host": "Disconnect the machine and start incident response",
                       "close": "Close as harmless"},
             hierarchy={"no_action": ["monitor", "close"], "containment": ["reset_credentials", "isolate_host"]}),
    Question("attack_stage", "choice", "Which stage has the attack reached?", _stage,
             ("incident", "login_succeeded", "entered_credentials", "persistence"),
             criteria={"recon": "Probing only; no access gained",
                       "initial_access": "The attacker got in",
                       "persistence": "The attacker set up lasting access",
                       "exfiltration": "Data has left the company"},
             hierarchy={"no_foothold": ["recon", "initial_access"], "established": ["persistence", "exfiltration"]}),
    Question("severity", "score", "How severe is this incident?", _severity,
             ("incident", "clicked_link", "login_succeeded", "entered_credentials", "persistence", "environment"),
             criteria=["Informational", "Low", "Medium", "High", "Critical"]),
    Question("account_risk", "score", "How much risk does the affected account face?", _account_risk,
             ("incident", "login_succeeded", "entered_credentials", "privileged", "mfa"),
             criteria=["No risk", "Low", "Elevated", "High"],
             applies=lambda f: f["incident"] in ("brute_force", "phishing")),
)

DOMAIN = Domain(
    name="security_ops", title="Security operations",
    facts=FACTS, archetypes=ARCHETYPES, questions=QUESTIONS,
    styles=("SIEM alert summary", "employee report email", "analyst shift note", "chat message to the security channel"),
)
