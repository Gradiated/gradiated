"""Materialise a fresh packet using the exact last accepted warning boundary."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys


ANCHOR_PIN = "29db873d990607570303f6b586402d61a6f781ca137dd3562884ff66f022bf9c"
ANCHOR_LOCATION = (".agents/runtime/hardware/inference/outputs/observer-qualification-20261115T182057Z-11c575/"
                   "restore-original/after.state.json")
ABORTED = "autonomous-prefill-decode-20261115T204825Z-46cd07"


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Expected one approved replacement for {old!r}")
    return source.replace(old, new)


def generate(source, destination, project):
    if sha256((project / ANCHOR_LOCATION).read_bytes()).hexdigest() != ANCHOR_PIN:
        raise ValueError("Accepted restoration anchor differs")
    shutil.copytree(source, destination)
    supervisor = destination / "observer_validation.py"
    text = supervisor.read_text()
    declaration = f'''
def accepted_warning_anchor(assets, lifecycle, baseline):
    anchor = assets['warning_anchor']
    raw = anchor['raw_text'].encode()
    expected = '{ANCHOR_PIN}'
    require(anchor['sha256']==expected and sha256(raw).hexdigest()==expected
            and anchor['reference']=='{ANCHOR_LOCATION}',
            'Last accepted restoration warning reference differs')
    state = json.loads(raw)
    lifecycle.check_state(state,baseline,STOCK)
    return state

'''
    text = replace(text, "\ndef board(args, modules, assets):",
                   "\n" + declaration + "\ndef board(args, modules, assets):")
    text = replace(text, "    last_state = baseline\n",
                   "    last_state = accepted_warning_anchor(assets,lifecycle,baseline)\n")
    text = replace(text, "    lifecycle.notices(progress.get('last',baseline),start)",
                   "    prior_state = progress.get('last')\n"
                   "    if prior_state is None:\n"
                   "        prior_state = accepted_warning_anchor(assets,lifecycle,baseline)\n"
                   "    lifecycle.notices(prior_state,start)")
    compile(text, str(supervisor), "exec")
    supervisor.write_text(text)

    controller = destination / "observer_host.py"
    text = controller.read_text()
    text = replace(text, "    assets = {'files':pins,", f'''
    anchor_path = repo / '{ANCHOR_LOCATION}'
    anchor = read(anchor_path,'{ANCHOR_PIN}')
    assets = {{'warning_anchor':{{'sha256':digest(anchor),'raw_text':anchor.decode(),
                                'reference':'{ANCHOR_LOCATION}'}},
              'files':pins,'''.lstrip("\n"))
    text = replace(text, "'native_clear_tb.c','prepare_support.py','offline-tests.log'):",
                   "'native_clear_tb.c','prepare_support.py','prepare_retry_support.py','retry-rationale.json','offline-tests.log'):")
    compile(text, str(controller), "exec")
    controller.write_text(text)

    rationale = {
        "first_aborted_attempt": ABORTED,
        "first_invocation_sha256":"3a7942055d23407f5f436b958227c17fbdd0bf99b411bdff7286952b4e87cea0",
        "observed_failure":"Historical warning baseline omitted notices already accepted in the previous restored run.",
        "aborted_preflight_state_equals_prior_restoration_sha256":ANCHOR_PIN,
        "change":"Initial warning comparison is anchored to the exact previous accepted restoration on board and Mac. Historical structural baseline and later strict checks are unchanged.",
        "unchanged":"Frozen circuit, weights, protocol, measurement schedule, full transfer and final restoration.",
    }
    (destination/"retry-rationale.json").write_text(json.dumps(rationale,indent=2,sort_keys=True)+"\n")
    shutil.copyfile(Path(__file__),destination/"prepare_retry_support.py")


if __name__=="__main__":
    generate(*(Path(p) for p in sys.argv[1:]))
