"""Independent scoreboards for cache contents, bank traffic and weighted sums."""


def integers(path):
    with path.open() as stream:
        for line in stream:
            yield tuple(map(int,line.split()))


def append_words(folder,cache,depths):
    words=[]
    for index,(position,coordinate,key,value) in enumerate(integers(folder/"value-cache-appends.txt")):
        assert (position,coordinate)==divmod(index,32)
        cached=tuple(int(n,16) for n in cache[index].split())
        assert cached==(key&0xffff,value&0xffff),(position,coordinate)
        words.append((key,value))
    assert len(words)==len(cache)==32*depths
    return words


def check_cache(folder,cache,depths,paired):
    words=append_words(folder,cache,depths)
    rows=integers(folder/"value-cache-responses.txt")
    spacing=2 if paired else 1
    for depth in range(1,depths+1):
        for head in range(2):
            head_base=16*head
            for pos in range(depth):
                for coordinate in range(head_base,head_base+16):
                    key,value=words[32*pos+coordinate]
                    wanted=(depth,0,pos,coordinate,0,key,value,0,1,1-coordinate%2,coordinate%2)
                    assert next(rows)==wanted,("score",depth,head,pos,coordinate)
            for coordinate in range(head_base,head_base+16,spacing):
                for pos in range(depth):
                    key,value=words[32*pos+coordinate]
                    second=words[32*pos+coordinate+1][1] if paired else 0
                    wanted=(depth,1,pos,coordinate,int(paired),key,value,second,1,
                            int(paired or coordinate%2==0),int(paired or coordinate%2==1))
                    assert next(rows)==wanted,("value",depth,head,pos,coordinate)
    assert next(rows,None) is None
    return words


def probabilities(path,depths):
    groups=[[[],[]] for _ in range(depths)]
    depth=0
    with path.open() as stream:
        for line in stream:
            kind,head,pos,*values=line.split()
            head=int(head)
            pos=int(pos)
            if kind=="S" and head==pos==0:
                depth+=1
            if kind=="P":
                assert 1<=depth<=depths
                positions=groups[depth-1][head]
                number=int(values[0])
                assert pos==len(positions) and 0<=number<=32768
                positions.append(number)
    assert depth==depths and all(len(a)==len(b)==d for d,(a,b) in enumerate(groups,1))
    return groups


def rounded(value):
    quotient,remainder=divmod(value,1<<15)
    quotient+=int(remainder>1<<14 or (remainder==1<<14 and quotient%2))
    clipped=min(max(quotient,-32768),32767)
    return clipped,quotient!=clipped


def check_terms(folder,words,depths,paired):
    groups=probabilities(folder/"attention-events.txt",depths)
    terms=integers(folder/"value-terms.txt")
    results=integers(folder/"value-results.txt")
    spacing=2 if paired else 1
    count=0
    for depth in range(1,depths+1):
        saturated=0
        for head in range(2):
            for first in range(0,16,spacing):
                sums=[0]*spacing
                for pos,probability in enumerate(groups[depth-1][head]):
                    for lane in range(spacing):
                        coord=first+lane
                        value=words[pos*32+head*16+coord][1]
                        product=probability*value
                        sums[lane]+=product
                        wanted=(depth,head,coord,pos,probability,value,product,sums[lane])
                        assert next(terms)==wanted,("weighted product",depth,head,coord,pos)
                        count+=1
                for lane,total in enumerate(sums):
                    expected,clipped=rounded(total)
                    d,index,result,clip=next(results)
                    assert (d,index,result)==(depth,head*16+first+lane,expected)
                    assert clip in (0,1) and clip>=saturated and (not clipped or clip)
                    saturated=clip
    assert next(terms,None) is None and next(results,None) is None
    assert count==32*sum(range(1,depths+1))


def audit_values(folder,cache,depths,paired):
    words=check_cache(folder,cache,depths,paired)
    check_terms(folder,words,depths,paired)
    reports=[]
    for n,row in enumerate(integers(folder/"value-profile.txt"),1):
        d,req,data,mac,send,wait,out,refused,delayed,held,*traffic=row
        groups=16 if paired else 32
        assert (d,req,data,mac,send,wait,out,refused,delayed,held)==(n,groups,n*groups,n*groups,32,32,32,0,0,0)
        assert traffic==[32*n,32*n,32*n,16*n,16*n,groups*n,groups*n,groups*n,16*n,16*n]
        reports.append(dict(depth=d,value_req=req,value_data=data,value_mac=mac,value_send=send,
                            value_round_wait=wait,value_output=out,value_phase_cycles=req+data+mac+send+wait+out,
                            refused_value_requests=refused,delayed_value_responses=delayed,held_output_clocks=held,
                            score_transactions=traffic[0],score_responses=traffic[1],score_k_reads=traffic[2],
                            score_even_v_words=traffic[3],score_odd_v_words=traffic[4],
                            value_transactions=traffic[5],value_responses=traffic[6],value_k_reads=traffic[7],
                            value_even_v_words=traffic[8],value_odd_v_words=traffic[9],weighted_v_terms=32*d))
    assert len(reports)==depths
    return reports
