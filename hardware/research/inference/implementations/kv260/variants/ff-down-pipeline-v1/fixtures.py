"""Independent integer oracle for ordered signed products and row results."""

from pathlib import Path
from random import Random


GEOMETRIES = ((128,32),(5,3),(1,3))


def hexadecimal(path, values, bits):
    mask = (1 << bits) - 1
    path.write_text("".join(f"{value & mask:0{(bits+3)//4}x}\n" for value in values))


def rounded(total):
    base, remainder = divmod(total, 1<<15)
    base += int(remainder>1<<14 or (remainder==1<<14 and base%2))
    result = min(max(base,-32768),32767)
    return result, result != base, remainder == 1<<14


def write_fixtures(root):
    report = {}
    for inputs,outputs in GEOMETRIES:
        path=root/f"{inputs}x{outputs}"
        path.mkdir()
        rng=Random(446106+inputs)
        x = [16384] if inputs==1 else [1,-1,32767,-32768] + [rng.randrange(-32768,32768) for _ in range(inputs-4)]
        weights=[]
        terms=[]
        results=[]
        saturation=ties=0
        for row in range(outputs):
            if inputs==1:
                weights_row=[(1,3,-3)[row]]
            else:
                weights_row=[rng.randrange(-32768,32768) for _ in range(inputs)]
                if row<3:
                    weights_row=[0]*inputs
                    weights_row[0]=(16384,-16384,16384)[row]
                    weights_row[1]=0 if row<2 else -32768
                elif row in (3,4):
                    weights_row=[(32767 if val>=0 else -32768) * (1 if row==3 else -1) for val in x]
                    weights_row=[max(-32768,min(32767,v)) for v in weights_row]
            weights.extend(weights_row)
            total=0
            for u,v in zip(x,weights_row,strict=True):
                product=u*v
                total+=product
                assert -(1<<47)<=total<1<<47
                terms.append(((product&0xffffffff)<<48) | (total&((1<<48)-1)))
            value,clipped,tie=rounded(total)
            saturation+=int(clipped)
            ties+=int(tie)
            results.append((int(clipped)<<16)|(value&0xffff))
        hexadecimal(path/"inputs.hex",x,16)
        hexadecimal(path/"weights.hex",weights,16)
        hexadecimal(path/"terms.hex",terms,80)
        hexadecimal(path/"results.hex",results,17)
        report[path.name]={"terms_per_pass":len(terms),"ties":ties,"saturations":saturation,
                           "control_clocks":outputs*(2*inputs+2),"candidate_clocks":outputs*(inputs+3)}
    return report
