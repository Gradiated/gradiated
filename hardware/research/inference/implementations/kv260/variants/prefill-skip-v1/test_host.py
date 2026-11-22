"""Check held score-count contracts for both images without board access."""
import argparse
from pathlib import Path
import runpy
import tempfile
from unittest.mock import Mock, patch
from types import SimpleNamespace
from prepare_host import prepare


def test(baseline):
    with tempfile.TemporaryDirectory() as root:
        output=Path(root)/"host"
        prepare(baseline, output)
        runtime=SimpleNamespace(**runpy.run_path(str(output/"autonomous_runtime.py")))
        for abi,skips in ((runtime.ABI,0),(runtime.SKIP_ABI,10)):
            registers={0x24:abi,0x3c:1,0x44:0,0x54:11,0x58:(11-skips)*320,0x20:11,
                       0x00:1,0x50:400,0x48:200,0x4c:200}
            if skips:
                registers[0x5c]=skips
            library=SimpleNamespace(autonomous_read=Mock(),autonomous_start=Mock(),autonomous_wait=Mock())
            with patch.object(runtime.ctypes,"CDLL",return_value=library), patch.object(runtime.Port,"read",side_effect=registers.__getitem__):
                port=runtime.Port(None,"unused.so",abi)
                assert runtime.finish_candidate(port,[65],[200],"output_limit",401,0x432,11)["skipped_positions"]==skips
                broken=[0x58,0x20]+([0x5c] if skips else [])
                for address in broken:
                    registers[address]+=1
                    try:
                        runtime.finish_candidate(port,[65],[200],"output_limit",401,0x432,11)
                    except runtime.RequestFailure:
                        pass
                    else:
                        raise AssertionError(f"Accepted wrong value at {address:#x}")
                    registers[address]-=1
                try:
                    runtime.Port(None,"unused.so", runtime.ABI if skips else runtime.SKIP_ABI)
                except runtime.RequestFailure:
                    pass
                else:
                    raise AssertionError("Accepted the wrong ABI")
    print("PASS common host contract, both ABIs and count/identity rejection")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("baseline",type=Path)
    test(p.parse_args().baseline)
