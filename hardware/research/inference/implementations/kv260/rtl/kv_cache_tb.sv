// Behavioural testbench. Python independently replays the full observed protocol.
`timescale 1ns/1ps
module kv_cache_tb;
    logic clk;
    initial begin clk=0; forever #5 clk=!clk; end
    logic reset=1,write_valid=0,read_valid=0,output_ready=0;
    logic write_ready,read_ready,output_valid,commit_valid;
    logic [8:0] write_position=0,read_position=0,token_count;
    logic [5:0] write_coordinate=0,read_coordinate=0;
    logic signed [15:0] write_k=0,write_v=0,output_k,output_v;
    logic [7:0] output_position;
    logic [4:0] output_coordinate,next_coordinate;
    kv_cache dut (.*);
    logic signed [15:0] ks [0:24575],vs [0:24575];
    integer csv,cycle=0,bank=0,section=0;
    bit pre_write_ready,pre_read_ready,pre_valid,write_fire,read_fire,reply_fire;
    string kfile,vfile,csvfile,wavefile;
    task automatic tick;
        @(posedge clk);
        pre_write_ready=write_ready; pre_read_ready=read_ready; pre_valid=output_valid;
        write_fire=write_valid && write_ready; read_fire=read_valid && read_ready;
        reply_fire=output_valid && output_ready;
        #1; cycle=int'($time/10);
        $fwrite(csv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            cycle,bank,section,reset,write_valid,write_position,write_coordinate,write_k,write_v,
            read_valid,read_position,read_coordinate,output_ready,pre_write_ready,pre_read_ready,pre_valid,
            write_fire,read_fire,reply_fire,token_count,next_coordinate,commit_valid,
            output_valid,output_position,output_coordinate,output_k,output_v,dut.pending);
    endtask
    task automatic quiet;
        write_valid=0;read_valid=0;output_ready=0;
    endtask
    task automatic reset_cache;
        reset=1;write_valid=1;read_valid=1;output_ready=1;tick();
        if (token_count!=0 || next_coordinate!=0 || output_valid || commit_valid ||
            output_k!=0 || output_v!=0 || write_ready || read_ready) $fatal(1,"Reset failed");
        @(negedge clk);reset=0;quiet();
    endtask
    task automatic put(input integer position,input integer coordinate);
        if (bank<0 || bank>=3 || position<0 || position>=256 || coordinate<0 || coordinate>=32)
            $fatal(1,"Invalid write fixture");
        quiet();write_valid=1;write_position=9'(position);write_coordinate=6'(coordinate);
        write_k=ks[bank*8192+position*32+coordinate];write_v=vs[bank*8192+position*32+coordinate];
        tick();
        if (!write_fire || int'(token_count)!=position+(coordinate==31 ? 1:0) ||
            int'(next_coordinate)!=(coordinate+1)%32 || commit_valid!=(coordinate==31)) $fatal(1,"Append/commit failed");
        @(negedge clk);quiet();
    endtask
    task automatic reject_write(input integer position,input integer coordinate);
        integer before_count,before_coordinate;
        if(position<0 || position>=512 || coordinate<0 || coordinate>=64) $fatal(1,"Invalid rejection fixture");
        before_count=int'(token_count);before_coordinate=int'(next_coordinate);
        quiet();write_valid=1;write_position=9'(position);write_coordinate=6'(coordinate);
        write_k=-16'sd1234;write_v=16'sd6789;tick();
        if (write_fire || int'(token_count)!=before_count || int'(next_coordinate)!=before_coordinate || commit_valid)
            $fatal(1,"Invalid write accepted");
        @(negedge clk);quiet();
    endtask
    task automatic reject_read(input integer position,input integer coordinate);
        if(position<0 || position>=512 || coordinate<0 || coordinate>=64) $fatal(1,"Invalid rejection fixture");
        quiet();read_valid=1;read_position=9'(position);read_coordinate=6'(coordinate);tick();
        if (read_fire || output_valid) $fatal(1,"Uncommitted/invalid read accepted");
        @(negedge clk);quiet();
    endtask
    task automatic get(input integer position,input integer coordinate);
        logic [14:0] offset;
        if (bank<0 || bank>=3 || position<0 || position>=256 || coordinate<0 || coordinate>=32)
            $fatal(1,"Invalid read fixture");
        offset=15'(bank*8192+position*32+coordinate);
        quiet();read_valid=1;read_position=9'(position);read_coordinate=6'(coordinate);tick();
        if (!read_fire || !output_valid || int'(output_position)!=position || int'(output_coordinate)!=coordinate ||
            output_k!=ks[offset] || output_v!=vs[offset]) $fatal(1,"Read value/tag failed");
        @(negedge clk);
        for (integer stall=0;stall<(position+coordinate)%3;stall=stall+1) begin
            write_valid=1;read_valid=1;write_position=token_count;write_coordinate={1'b0,next_coordinate};
            write_k=16'sd23;write_v=-16'sd27;tick();
            if (write_fire || read_fire || !output_valid || output_k!=ks[offset] || output_v!=vs[offset] ||
                int'(output_position)!=position || int'(output_coordinate)!=coordinate) $fatal(1,"Stalled result changed");
            @(negedge clk);
        end
        quiet();output_ready=1;tick();
        if (!reply_fire || output_valid) $fatal(1,"Response acceptance failed");
        @(negedge clk);quiet();
    endtask
    initial begin
        if (!$value$plusargs("K=%s",kfile) || !$value$plusargs("V=%s",vfile) ||
            !$value$plusargs("CSV=%s",csvfile) || !$value$plusargs("VCD=%s",wavefile)) $fatal(1,"Missing fixtures");
        $readmemh(kfile,ks);$readmemh(vfile,vs);
        csv=$fopen(csvfile,"w");if(csv==0)$fatal(1,"Cannot open CSV");
        $fwrite(csv,"cycle,bank,section,reset,write_valid,write_position,write_coordinate,write_k,write_v,read_valid,read_position,read_coordinate,output_ready,pre_write_ready,pre_read_ready,pre_valid,write_fire,read_fire,reply_fire,token_count,next_coordinate,commit_valid,output_valid,output_position,output_coordinate,output_k,output_v,pending\n");
        $dumpfile(wavefile);$dumpvars(0,dut);
        tick();@(negedge clk);reset=0;
        // Conflicting commands cannot change either port's state.
        write_valid=1;read_valid=1;tick();
        if (write_fire || read_fire || token_count!=0 || next_coordinate!=0) $fatal(1,"Conflicting commands accepted");
        @(negedge clk);quiet();
        for (integer b=0;b<3;b=b+1) begin
            bank=b;section=10*b;
            for (integer p=0;p<256;p=p+1) begin
                reject_read(p,0);put(p,0);reject_read(p,0);
                reject_write(p,0);reject_write(p,32);reject_write(p+1,1);reject_write(p,31);
                if(p>0)get(p-1,(p*13)%32);
                for(integer c=1;c<31;c=c+1)put(p,c);
                reject_read(p,31);put(p,31);get(p,0);get(p,31);
            end
            section=10*b+1;
            // Permutations visit every one of 8,192 addresses in each payload.
            for(integer p=0;p<256;p=p+1)
                for(integer c=0;c<32;c=c+1)get((p*73)%256,(c*13)%32);
            section=10*b+2;
            for(integer invalid=256;invalid<512;invalid=invalid+1)begin
                reject_write(invalid,0);reject_read(invalid,0);
            end
            reject_write(0,0);reject_write(255,31);
            for(integer c=32;c<64;c=c+1)reject_read(127,c);
            section=10*b+3;get(0,0);get(255,31);
            section=10*b+4;reset_cache();
            if(dut.k_memory[0]!=ks[b*8192] || dut.v_memory[0]!=vs[b*8192]) $fatal(1,"Reset changed RAM bits");
            for(integer p=0;p<256;p=p+1)reject_read(p,0);
        end
        // Partial writes must never expose stale data after a new sequence begins.
        section=40;
        for(integer n=0;n<4;n=n+1)begin
            bank=0;
            for(integer c=0;c<(n==0 ? 0:n==1 ? 1:n==2 ? 15:31);c=c+1)put(0,c);
            reject_read(0,0);reset_cache();reject_read(0,0);
            bank=1;for(integer c=0;c<32;c=c+1)put(0,c);
            for(integer c=0;c<32;c=c+1)get(0,c);
            reset_cache();
        end
        // Reset with a read response held under backpressure.
        bank=2;section=41;for(integer c=0;c<32;c=c+1)put(0,c);
        read_valid=1;read_position=0;read_coordinate=31;tick();
        if(!output_valid || !read_fire)$fatal(1,"Pending-read setup failed");
        @(negedge clk);reset_cache();reject_read(0,31);
        $fclose(csv);$display("PASS kv_cache banks=3 positions=256 coordinates=32");$finish;
    end
    initial begin #20000000;$fatal(1,"Absolute simulation-time limit");end
endmodule
