`timescale 1ns/1ps
module cache_pair_tb;
    bit clk=0, reset=1, write_valid=0, read_valid=0, read_pair=0, output_ready=0;
    always #5 clk=!clk;
    logic write_ready, read_ready, output_valid, output_pair, commit_valid;
    logic [8:0] write_position=0, read_position=0, token_count;
    logic [5:0] write_coordinate=0, read_coordinate=0;
    logic [7:0] output_position;
    logic [4:0] output_coordinate,next_coordinate;
    logic signed [15:0] write_k=0, write_v=0, output_k, output_v, output_v_second;
    kv_cache_value_pair dut(.*);

    function automatic logic signed [15:0] key(input int p,c);
        key=16'(p*257-c*101+119);
    endfunction
    function automatic logic signed [15:0] value(input int p,c);
        value=(p==255 && c==31) ? -16'sd32768 : 16'(p*193+c*43+271);
    endfunction
    task automatic tick;
        @(posedge clk);#1;@(negedge clk);
    endtask

    task automatic append(input int p,c);
        write_position=9'(p);write_coordinate=6'(c);
        write_k=key(p,c);write_v=value(p,c);write_valid=1;
        #1;
        if(!write_ready) $fatal(1,"Rejected ordered cache append");
        tick();write_valid=0;
        if(token_count!=9'(p+(c==31)) || next_coordinate!=5'(c+1) || commit_valid!=(c==31))
            $fatal(1,"Incorrect row commit");
    endtask
    task automatic reject_read(input int p,c,input bit pair);
        read_position=9'(p);read_coordinate=6'(c);read_pair=pair;read_valid=1;
        #1;
        if(read_ready || dut.key_read_enable || dut.even_read_enable || dut.odd_read_enable)
            $fatal(1,"Attempted to read invalid/uncommitted/pending location");
        tick();read_valid=0;
        if(output_valid) $fatal(1,"Rejected read produced data");
    endtask
    task automatic read_word(input int p,c,input bit pair);
        read_position=9'(p);read_coordinate=6'(c);read_pair=pair;read_valid=1;
        #1;
        if(!read_ready || !dut.key_read_enable ||
           dut.even_read_enable!=(pair || c%2==0) || dut.odd_read_enable!=(pair || c%2==1))
            $fatal(1,"Wrong bank selection");
        tick();
        read_position=0;read_coordinate=1;read_pair=0;write_valid=1;
        for(int hold=0;hold<3;hold++) begin
            #1;
            if(!output_valid || read_ready || write_ready ||
               dut.key_read_enable || dut.even_read_enable || dut.odd_read_enable ||
               output_pair!=pair || output_position!=8'(p) || output_coordinate!=5'(c) ||
               output_k!==key(p,c) || output_v!==value(p,c) ||
               output_v_second!==(pair ? value(p,c+1) : 16'sd0))
                $fatal(1,"Held response changed for pos=%0d coord=%0d pair=%0d",p,c,pair);
            tick();
        end
        write_valid=0;read_valid=0;output_ready=1;
        tick();output_ready=0;
        if(output_valid) $fatal(1,"Held cache response did not retire");
    endtask
    initial begin
        tick();reset=0;
        append(0,0);
        reject_read(0,0,1);
        reject_read(0,0,0);
        write_valid=1;write_position=0;write_coordinate=2;
        #1;if(write_ready) $fatal(1,"Allowed a skipped append");
        tick();write_valid=0;
        for(int c=1;c<32;c++) append(0,c);
        reject_read(0,1,1);
        reject_read(0,31,1);
        reject_read(0,32,0);
        reject_read(1,0,1);
        for(int p=1;p<256;p++) for(int c=0;c<32;c++) append(p,c);
        if(token_count!=256 || write_ready) $fatal(1,"Cache capacity differs");
        for(int p=0;p<256;p++) begin
            for(int c=0;c<32;c++) read_word(p,c,0);
            for(int c=0;c<32;c+=2) read_word(p,c,1);
        end
        reject_read(256,0,1);
        read_valid=1;read_pair=1;read_position=255;read_coordinate=30;
        tick();
        if(!output_valid || !output_pair) $fatal(1,"Did not arm pending reset probe");
        reset=1;read_valid=0;
        tick();reset=0;
        #1;
        if(output_valid || output_pair || token_count!=0 || next_coordinate!=0)
            $fatal(1,"Reset exposed stale paired cache state");
        reject_read(0,0,1);
        $display("PASS pair cache: 8192 scalar reads, 4096 paired reads with held replies, 8192 ordered writes and reset");
        $finish;
    end
    initial begin #100000000; $fatal(1,"Cache bench timeout"); end
endmodule
