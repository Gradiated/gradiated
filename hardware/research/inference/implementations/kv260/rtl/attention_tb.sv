// Behavioural only: external append-only cache plus deliberate request/reply stalls.
`timescale 1ns/1ps
module attention_tb;
    logic clk;
    initial begin clk=0;forever #5 clk=!clk;end
    logic reset=1,load_valid=0,table_valid=0,start=0,result_ready=0;
    logic load_ready,table_ready,start_ready,busy,result_valid,saturated,error;
    logic [4:0] load_index=0,result_index;
    logic signed [15:0] load_value=0,result;
    logic [8:0] table_index=0,context_length=0;
    logic [31:0] table_value=0;
    logic cache_read_valid,cache_read_ready,cache_output_valid,cache_output_ready;
    logic [8:0] cache_read_position;
    logic [5:0] cache_read_coordinate;
    logic [7:0] cache_output_position;
    logic [4:0] cache_output_coordinate;
    logic signed [15:0] cache_output_k,cache_output_v;
    logic score_valid,score_head,exp_valid,exp_head,probability_valid,probability_head;
    logic [7:0] score_position,exp_position,probability_position;
    logic signed [31:0] score_value;
    logic [31:0] exp_value;
    logic [15:0] probability_value;
    logic step_valid,step_mode,step_head;
    logic [7:0] step_position;
    logic [3:0] step_coordinate;
    logic signed [16:0] step_input;
    logic signed [15:0] step_weight;
    logic signed [32:0] step_product;
    logic signed [47:0] step_sum;
    attention dut(.*);
    logic backing_read_ready,backing_output_valid;
    logic [7:0] backing_output_position;
    logic [4:0] backing_output_coordinate;
    logic signed [15:0] backing_output_k,backing_output_v;
    logic write_valid=0,write_ready,commit_valid;
    logic [8:0] write_position=0,token_count;
    logic [5:0] write_coordinate=0;
    logic [4:0] next_coordinate;
    logic signed [15:0] write_k=0,write_v=0;
    integer cycle=0,case_id=-1,csv,cases,passed=0;
    logic allow_read,allow_reply;
    logic corrupt_tag=0;
    assign allow_read=(cycle%4)!=0;
    assign allow_reply=(cycle%5)!=0;
    assign cache_read_ready=backing_read_ready && allow_read;
    assign cache_output_valid=backing_output_valid && allow_reply;
    assign cache_output_position=corrupt_tag ? backing_output_position+8'd1 : backing_output_position;
    assign cache_output_coordinate=backing_output_coordinate;
    assign cache_output_k=backing_output_k;
    assign cache_output_v=backing_output_v;
    kv_cache backing(
        .clk(clk),.reset(reset),.write_valid(write_valid),.write_ready(write_ready),
        .write_position(write_position),.write_coordinate(write_coordinate),.write_k(write_k),.write_v(write_v),
        .read_valid(cache_read_valid && allow_read),.read_ready(backing_read_ready),
        .read_position(cache_read_position),.read_coordinate(cache_read_coordinate),
        .output_valid(backing_output_valid),.output_ready(cache_output_ready && allow_reply),
        .output_position(backing_output_position),.output_coordinate(backing_output_coordinate),
        .output_k(backing_output_k),.output_v(backing_output_v),.token_count(token_count),
        .next_coordinate(next_coordinate),.commit_valid(commit_valid)
    );
    localparam integer MAX_CASES=16;
    logic signed [15:0] qs[0:MAX_CASES*32-1],ks[0:MAX_CASES*8192-1],vs[0:MAX_CASES*8192-1];
    logic signed [15:0] answers[0:MAX_CASES*32-1];
    logic [7:0] clips[0:MAX_CASES*32-1];
    logic [8:0] lengths[0:MAX_CASES-1];
    logic [31:0] exp_table[0:256];
    string qfile,kfile,vfile,answerfile,clipfile,lengthfile,tablefile,csvfile,wavefile;
    task automatic tick;
        @(posedge clk);
        if(result_valid && result_ready)$fwrite(csv,"O,%0d,%0d,0,0,%0d,0,0,0,0,%0d,%0d,%0d\n",
            case_id,cycle,result_index,result,error,saturated);
        #1;cycle=int'($time/10);
        if(step_valid)$fwrite(csv,"%s,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,0,0,0\n",
            step_mode ? "C":"D",case_id,cycle,step_head,step_position,step_coordinate,
            step_input,step_weight,step_product,step_sum);
        if(score_valid)$fwrite(csv,"S,%0d,%0d,%0d,%0d,0,0,0,0,0,%0d,0,0\n",
            case_id,cycle,score_head,score_position,score_value);
        if(exp_valid)$fwrite(csv,"E,%0d,%0d,%0d,%0d,0,0,0,0,0,%0d,0,0\n",
            case_id,cycle,exp_head,exp_position,exp_value);
        if(probability_valid)$fwrite(csv,"P,%0d,%0d,%0d,%0d,0,0,0,0,0,%0d,0,0\n",
            case_id,cycle,probability_head,probability_position,probability_value);
    endtask
    task automatic quiet;
        load_valid=0;table_valid=0;start=0;result_ready=0;write_valid=0;corrupt_tag=0;
    endtask
    task automatic clear;
        quiet();reset=1;tick();
        if(busy || result_valid || saturated || error || token_count!=0)$fatal(1,"Attention reset failed");
        @(negedge clk);reset=0;
    endtask
    task automatic prepare(input integer id,input bit with_table);
        clear();
        for(integer p=0;p<int'(lengths[id]);p=p+1)for(integer c=0;c<32;c=c+1)begin
            write_valid=1;write_position=9'(p);write_coordinate=6'(c);
            write_k=ks[id*8192+p*32+c];write_v=vs[id*8192+p*32+c];
            tick();
            if(int'(token_count)!=p+(c==31 ? 1:0) || int'(next_coordinate)!=(c+1)%32)
                $fatal(1,"Cache fixture append failed");
            @(negedge clk);
        end
        write_valid=0;
        for(integer c=0;c<32;c=c+1)begin
            load_valid=1;load_index=5'(c);load_value=qs[id*32+c];
            tick();if(!load_ready)$fatal(1,"Query loading refused");@(negedge clk);
        end
        load_valid=0;
        if(with_table)for(integer j=0;j<=256;j=j+1)begin
            table_valid=1;table_index=9'(j);table_value=exp_table[j];
            tick();if(!table_ready)$fatal(1,"Exp table load refused");@(negedge clk);
        end
        table_valid=0;context_length=lengths[id];
    endtask
    task automatic launch;
        start=1;tick();if(!busy || start_ready)$fatal(1,"Attention start handshake failed");
        @(negedge clk);start=0;
    endtask
    task automatic run_case(input integer id,input integer label_id);
        integer elapsed;
        case_id=label_id;prepare(id,1);launch();
        for(integer c=0;c<32;c=c+1)begin
            elapsed=0;
            while(!result_valid)begin
                start=1;context_length=511;load_valid=1;load_index=31;load_value=-1234;
                table_valid=1;table_index=0;table_value=0;
                tick();elapsed=elapsed+1;
                if(load_ready || table_ready || start_ready || !busy)$fatal(1,"Busy attention request accepted");
                if(elapsed>400000)$fatal(1,"Attention result latency bound");@(negedge clk);
            end
            quiet();
            if(error || result_index!=5'(c) || result!=answers[id*32+c] || saturated!=clips[id*32+c][0])
                $fatal(1,"Attention context mismatch case=%0d coordinate=%0d got=%0d error=%0d saturation=%0d",id,c,result,error,saturated);
            for(integer stall=0;stall<1+(id+c)%3;stall=stall+1)begin
                tick();if(!result_valid || !busy || result_index!=5'(c) || result!=answers[id*32+c] ||
                    saturated!=clips[id*32+c][0] || error)$fatal(1,"Attention stalled context changed");@(negedge clk);
            end
            result_ready=1;tick();@(negedge clk);result_ready=0;
        end
        if(busy || result_valid)$fatal(1,"Attention final response acceptance failed");passed=passed+1;
    endtask
    initial begin
        if(!$value$plusargs("N=%d",cases)||cases<=0||cases>MAX_CASES||!$value$plusargs("Q=%s",qfile)||
           !$value$plusargs("K=%s",kfile)||!$value$plusargs("V=%s",vfile)||!$value$plusargs("ANSWERS=%s",answerfile)||
           !$value$plusargs("CLIPS=%s",clipfile)||!$value$plusargs("LENGTHS=%s",lengthfile)||!$value$plusargs("TABLE=%s",tablefile)||
           !$value$plusargs("CSV=%s",csvfile)||!$value$plusargs("VCD=%s",wavefile))$fatal(1,"Missing attention fixtures");
        $readmemh(qfile,qs,0,cases*32-1);$readmemh(kfile,ks,0,cases*8192-1);$readmemh(vfile,vs,0,cases*8192-1);
        $readmemh(answerfile,answers,0,cases*32-1);$readmemh(clipfile,clips,0,cases*32-1);
        $readmemh(lengthfile,lengths,0,cases-1);$readmemh(tablefile,exp_table);
        csv=$fopen(csvfile,"w");if(csv==0)$fatal(1,"Cannot open attention trace");
        $fwrite(csv,"kind,case,cycle,head,position,coordinate,a,b,product,total,value,error,saturated\n");
        $dumpfile(wavefile);$dumpvars(0,dut);
        tick();@(negedge clk);reset=0;
        start=1;context_length=1;tick();if(start_ready||busy)$fatal(1,"Incomplete query accepted");
        @(negedge clk);quiet();
        // Missing table returns a held error packet, never fabricated probabilities.
        prepare(0,0);case_id=-1;launch();
        while(!result_valid)begin tick();@(negedge clk);end
        if(!error || result!=0)$fatal(1,"Missing exp table was accepted");
        repeat(3)begin tick();if(!error||!result_valid)$fatal(1,"Error response was not held");@(negedge clk);end
        result_ready=1;tick();@(negedge clk);quiet();
        prepare(0,1);
        for(integer invalid=0;invalid<512;invalid=invalid+1)if(invalid==0 || invalid>256)begin
            start=1;context_length=9'(invalid);tick();if(start_ready||busy)$fatal(1,"Invalid context length accepted");
            @(negedge clk);
        end
        quiet();
        // Conflicting input/table/start attempts are refused.
        context_length=1;load_valid=1;table_valid=1;start=1;tick();
        if(load_ready||table_ready||start_ready||busy)$fatal(1,"Conflicting attention commands accepted");
        @(negedge clk);quiet();
        // A wrong cache response tag returns an error, even when data is plausible.
        prepare(0,1);case_id=-1;corrupt_tag=1;launch();
        while(!result_valid)begin tick();@(negedge clk);end
        if(!error)$fatal(1,"Incorrect cache response tag accepted");
        result_ready=1;tick();@(negedge clk);quiet();
        for(integer id=0;id<cases;id=id+1)run_case(id,id);
        // Reset cancels score reads, scalar nonlinear work, value reads and output.
        for(integer probe=0;probe<4;probe=probe+1)begin
            prepare(0,1);case_id=-2;launch();
            case(probe)
                0: while(dut.state!=5'd2)begin tick();@(negedge clk);end
                1: while(dut.state!=5'd8)begin tick();@(negedge clk);end
                2: while(dut.state!=5'd13)begin tick();@(negedge clk);end
                3: while(!result_valid)begin tick();@(negedge clk);end
            endcase
            clear();run_case(0,cases+probe);
        end
        $fclose(csv);$display("PASS attention requests=%0d heads=2 coordinates=32 reset_probes=4",passed);$finish;
    end
    initial begin #50000000;$fatal(1,"Attention absolute simulation-time limit");end
endmodule
