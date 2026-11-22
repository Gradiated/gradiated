// Connected-block behavioural tests. All synthetic expectations come from Python.
`timescale 1ns/1ps
module frontend_tb;
    logic clk;
    initial begin clk=0;forever #5 clk=!clk;end
    logic reset=1,load_valid=0,coefficient_valid=0,start=0,query_ready=0,read_valid=0,output_ready=0;
    logic load_ready,coefficient_ready,start_ready,busy,query_valid,saturated,read_ready,output_valid;
    logic [4:0] load_address=0,query_coordinate,output_coordinate;
    logic [6:0] load_row=0;
    logic signed [15:0] load_input=0,load_weight=0,load_cosine=0,load_sine=0,query_value,output_k,output_v;
    logic [7:0] coefficient_position=0,output_position;
    logic [2:0] coefficient_pair=0;
    logic [8:0] token_position=0,read_position=0,token_count;
    logic [5:0] read_coordinate=0;
    frontend dut(.*);
    logic signed [15:0] xs[0:8191],ws[0:3071],qs[0:8191],ks[0:8191],vs[0:8191];
    logic signed [15:0] cs[0:2047],ss[0:2047];
    logic [7:0] clips[0:255];
    integer csv,cycle=0,case_id=-1,passed=0;
    string xfile,wfile,qfile,kfile,vfile,cfile,sfile,clipfile,csvfile,wavefile;
    bit pw,pr,pv,wf,rf,of;
    logic [8:0] wp,rp;
    logic [5:0] wc,rc;
    logic signed [15:0] wk,wv;
    task automatic tick;
        @(posedge clk);
        pw=dut.cache_write_ready;pr=dut.cache_read_ready;pv=dut.cache_output_valid;
        wf=(dut.state==6)&&pw;rf=dut.cache_read_valid&&pr;of=pv&&output_ready;
        wp=dut.position;wc=dut.index;wk=dut.rotated[32+dut.index];wv=dut.v_buffer[dut.index];
        rp=read_position;rc=read_coordinate;
        if(query_valid&&query_ready)$fwrite(csv,"Q,%0d,%0d,%0d,%0d,%0d,0,0,0\n",case_id,cycle,query_coordinate,query_value,saturated);
        #1;cycle=int'($time/10);
        if(dut.mac_step_valid)$fwrite(csv,"M,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",case_id,cycle,
            dut.mac_step_row,dut.mac_step_index,dut.mac_step_input,dut.mac_step_weight,dut.mac_step_product,dut.mac_step_sum);
        if(dut.rope_step_valid)$fwrite(csv,"R,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",case_id,cycle,
            dut.rope_step_pair,dut.rope_step_kind,dut.rope_step_input,dut.rope_step_coefficient,dut.rope_step_product,dut.rope_step_total);
        if(wf)$fwrite(csv,"W,%0d,%0d,%0d,%0d,%0d,%0d,%0d,0\n",case_id,cycle,wp,wc,wk,wv,token_count);
        if(rf)$fwrite(csv,"K,%0d,%0d,%0d,%0d,%0d,%0d,%0d,0\n",case_id,cycle,rp,rc,output_k,output_v,token_count);
        if(reset)$fwrite(csv,"Z,%0d,%0d,%0d,%0d,%0d,%0d,%0d,0\n",case_id,cycle,token_count,dut.next_coordinate,output_valid,busy,query_valid);
    endtask
    task automatic quiet;
        load_valid=0;coefficient_valid=0;start=0;read_valid=0;query_ready=0;output_ready=0;
    endtask
    task automatic clear_sequence;
        quiet();reset=1;tick();
        if(busy||query_valid||output_valid||token_count!=0||saturated)$fatal(1,"Frontend reset failed");
        if(dut.projection.weight_memory[3071]!=ws[3071]||dut.rotation.cosine_memory[2047]!=cs[2047])
            $fatal(1,"Reset destroyed loaded model/table memory");
        @(negedge clk);reset=0;
    endtask
    task automatic load_input_vector(input integer id);
        quiet();
        for(integer c=0;c<32;c=c+1)begin
            load_valid=1;load_address=5'(c);load_row=0;load_input=xs[id*32+c];load_weight=ws[c];
            tick();if(!load_ready)$fatal(1,"Idle input load failed");@(negedge clk);
        end
        load_valid=0;
    endtask
    task automatic launch(input integer position);
        token_position=9'(position);start=1;tick();
        if(!busy||start_ready)$fatal(1,"Frontend start failed");
        @(negedge clk);start=0;
    endtask
    task automatic run_token(input integer id,input integer position);
        integer elapsed;
        case_id=id;load_input_vector(id);launch(position);elapsed=0;
        while(!query_valid)begin
            start=1;token_position=511;load_valid=1;load_row=127;load_weight=-1234;
            coefficient_valid=1;load_cosine=37;load_sine=39;read_valid=1;
            tick();elapsed=elapsed+1;
            if(load_ready||coefficient_ready||start_ready||read_ready||!busy)$fatal(1,"Busy external command accepted");
            if(elapsed>6800)$fatal(1,"Connected frontend latency bound");
            @(negedge clk);
        end
        quiet();
        if(int'(token_count)!=position+1)$fatal(1,"Query visible before complete K/V commit");
        for(integer c=0;c<32;c=c+1)begin
            for(integer stall=0;stall<1+(id+c)%3;stall=stall+1)begin
                tick();
                if(!query_valid||int'(query_coordinate)!=c||query_value!=qs[id*32+c]||saturated!=clips[id][0])
                    $fatal(1,"Connected query/result stall mismatch id=%0d coordinate=%0d",id,c);
                @(negedge clk);
            end
            query_ready=1;tick();@(negedge clk);query_ready=0;
        end
        if(busy||query_valid)$fatal(1,"Final query acceptance failed");passed=passed+1;
    endtask
    task automatic get(input integer position,input integer coordinate);
        quiet();read_valid=1;read_position=9'(position);read_coordinate=6'(coordinate);
        tick();
        if(!output_valid||output_position!=8'(position)||output_coordinate!=5'(coordinate)||
           output_k!=ks[position*32+coordinate]||output_v!=vs[position*32+coordinate])$fatal(1,"Connected cache readback mismatch");
        @(negedge clk);read_valid=0;
        // A stalled response must prevent a new token start and remain stable.
        start=1;token_position=token_count;tick();
        if(start_ready||busy||!output_valid||output_k!=ks[position*32+coordinate]||output_v!=vs[position*32+coordinate])
            $fatal(1,"Pending cache response/start interlock failed");
        @(negedge clk);start=0;output_ready=1;tick();@(negedge clk);output_ready=0;
        if(output_valid)$fatal(1,"Cache response did not retire");
    endtask
    initial begin
        if(!$value$plusargs("X=%s",xfile)||!$value$plusargs("W=%s",wfile)||!$value$plusargs("Q=%s",qfile)||
           !$value$plusargs("K=%s",kfile)||!$value$plusargs("V=%s",vfile)||!$value$plusargs("C=%s",cfile)||
           !$value$plusargs("S=%s",sfile)||!$value$plusargs("CLIPS=%s",clipfile)||!$value$plusargs("CSV=%s",csvfile)||
           !$value$plusargs("VCD=%s",wavefile))$fatal(1,"Missing frontend fixtures");
        $readmemh(xfile,xs);$readmemh(wfile,ws);$readmemh(qfile,qs);$readmemh(kfile,ks);$readmemh(vfile,vs);
        $readmemh(cfile,cs);$readmemh(sfile,ss);$readmemh(clipfile,clips);
        csv=$fopen(csvfile,"w");if(csv==0)$fatal(1,"Cannot open connected trace");
        $dumpfile(wavefile);$dumpvars(0,dut);
        tick();@(negedge clk);reset=0;
        // Model/table loading remains host work, only while idle.
        for(integer r=0;r<96;r=r+1)for(integer c=0;c<32;c=c+1)begin
            load_valid=1;load_row=7'(r);load_address=5'(c);load_input=xs[c];load_weight=ws[r*32+c];
            tick();if(!load_ready)$fatal(1,"Initial projection weights load failed");@(negedge clk);
        end
        load_valid=0;
        for(integer i=0;i<2048;i=i+1)begin
            coefficient_valid=1;coefficient_position=8'(i/8);coefficient_pair=3'(i%8);load_cosine=cs[i];load_sine=ss[i];
            tick();if(!coefficient_ready)$fatal(1,"Initial RoPE table load failed");@(negedge clk);
        end
        quiet();
        start=1;load_valid=1;coefficient_valid=1;tick();
        if(start_ready||load_ready||coefficient_ready||busy)$fatal(1,"Conflicting idle commands accepted");
        @(negedge clk);quiet();
        // Reject skipped append position and every invalid nine-bit position.
        for(integer p=1;p<512;p=p+1)begin
            start=1;token_position=9'(p);tick();if(start_ready||busy)$fatal(1,"Invalid token position accepted");
            @(negedge clk);
        end
        quiet();
        // Cancel at every connected stage. Reset clears cache visibility while
        // retaining weights/tables; the next complete request must still work.
        for(integer stage=1;stage<=7;stage=stage+1)begin
            case_id=-1;load_input_vector(0);launch(0);
            $display("Frontend reset probe stage=%0d state_after_launch=%0d cast=%0d",stage,dut.state,int'(dut.state));
            while(dut.state!=stage[3:0])begin tick();@(negedge clk);end
            if(stage==3||stage==6)repeat(3)begin tick();@(negedge clk);end
            clear_sequence();run_token(0,0);get(0,31);clear_sequence();
        end
        for(integer p=0;p<256;p=p+1)begin run_token(p,p);get(p,0);get(p,31);end
        for(integer p=0;p<256;p=p+1)for(integer c=0;c<32;c=c+1)get(p,c);
        quiet();start=1;token_position=256;tick();
        if(start_ready||busy||token_count!=256)$fatal(1,"Full cache start was accepted");
        @(negedge clk);quiet();clear_sequence();
        $fclose(csv);$display("PASS frontend tokens=%0d positions=256 reset_stages=7",passed);$finish;
    end
    initial begin #25000000;$fatal(1,"Connected testbench absolute simulation-time limit");end
endmodule
