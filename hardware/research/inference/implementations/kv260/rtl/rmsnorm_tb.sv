// Behavioural RMSNorm testbench; fixtures and bit-exact answers come from Python.
`timescale 1ns/1ps
module rmsnorm_tb #(
    parameter integer SOURCE_EXP=-14,
    parameter integer GAIN_EXP=-14,
    parameter integer OUTPUT_EXP=-11
);
    logic clk;
    initial begin clk=0;forever #5 clk=!clk;end
    logic reset=1,load_valid=0,load_ready,start=0,start_ready,busy;
    logic [4:0] load_address=0,result_index;
    logic signed [15:0] load_input=0,load_gain=0,result;
    logic table_valid=0,table_ready,table_kind=1;
    logic [8:0] table_index=0;
    logic [31:0] table_value=0;
    logic result_valid,result_ready=0,saturated,error;
    rmsnorm #(.SOURCE_EXP(SOURCE_EXP),.GAIN_EXP(GAIN_EXP),.OUTPUT_EXP(OUTPUT_EXP)) dut(.*);
    localparam integer MAX_CASES=128;
    logic signed [15:0] xs[0:MAX_CASES*32-1],gains[0:MAX_CASES*32-1],answers[0:MAX_CASES*32-1];
    logic [7:0] clips[0:MAX_CASES*32-1];
    logic [31:0] rsqrttable[0:255];
    integer cases,csv,cycle=0,passed=0;
    string xfile,gainfile,answerfile,clipfile,rsqrtfile,csvfile,wavefile;
    task automatic tick;
        @(posedge clk);#1;cycle=int'($time/10);
    endtask
    task automatic quiet;
        load_valid=0;table_valid=0;start=0;result_ready=0;
    endtask
    task automatic load_tables;
        quiet();
        for(integer i=0;i<256;i=i+1)begin
            table_valid=1;table_kind=1;table_index=9'(i);table_value=rsqrttable[i];
            #1;if(!table_ready)$fatal(1,"RMS table not ready while idle");
            tick();@(negedge clk);
        end
        table_valid=0;
    endtask
    task automatic load_fixture(input integer id);
        quiet();
        for(integer i=0;i<32;i=i+1)begin
            load_valid=1;load_address=5'(i);load_input=xs[id*32+i];load_gain=gains[id*32+i];
            #1;if(!load_ready)$fatal(1,"RMS input loading not ready");
            tick();@(negedge clk);
        end
        load_valid=0;
    endtask
    task automatic launch;
        quiet();start=1;
        #1;if(!start_ready)$fatal(1,"RMS not ready with loaded inputs");
        tick();if(!busy)$fatal(1,"RMS did not start");
        @(negedge clk);start=0;
    endtask
    task automatic run_case(input integer id,input integer label_id);
        integer elapsed;
        load_fixture(id);launch();
        for(integer coordinate=0;coordinate<32;coordinate=coordinate+1)begin
            elapsed=0;
            while(!result_valid)begin
                load_valid=1;table_valid=1;start=1;
                load_input=-16'sd1234;load_gain=16'sd2345;table_value=32'h1000;
                tick();elapsed=elapsed+1;
                if(!busy || load_ready || table_ready || start_ready)$fatal(1,"Busy RMS accepted a request");
                if(elapsed>7000)$fatal(1,"RMS output latency exceeded");
                @(negedge clk);
            end
            if(result_index!==5'(coordinate) || result!==answers[id*32+coordinate] ||
               saturated!==clips[id*32+coordinate][0] || error!==0)
                $fatal(1,"RMS mismatch case %0d coordinate %0d got %0d",id,coordinate,result);
            for(integer stall=0;stall<1+(id+coordinate)%3;stall=stall+1)begin
                tick();
                if(!result_valid || !busy || load_ready || table_ready || start_ready ||
                   result_index!==5'(coordinate) || result!==answers[id*32+coordinate] ||
                   saturated!==clips[id*32+coordinate][0] || error!==0)$fatal(1,"Stalled RMS result changed");
                @(negedge clk);
            end
            $fwrite(csv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
                label_id,coordinate,xs[id*32+coordinate],gains[id*32+coordinate],result,saturated,error,
                dut.squares,dut.r,dut.y,dut.exponent,dut.xy,dut.product,elapsed);
            quiet();result_ready=1;tick();
            if(result_valid || busy!=(coordinate<31))$fatal(1,"RMS result acceptance failed");
            @(negedge clk);result_ready=0;
        end
        passed=passed+1;
    endtask
    task automatic abort_after(input integer edges);
        load_fixture(0);launch();result_ready=1;
        repeat(edges)begin tick();@(negedge clk);end
        reset=1;tick();
        if(busy || result_valid || result!==0 || saturated || error || result_index!==0)
            $fatal(1,"RMS reset did not cancel work");
        if(dut.input_memory[0]!==xs[0] || dut.gain_memory[0]!==gains[0] ||
           dut.scalar.rsqrt_memory[0]!==rsqrttable[0])$fatal(1,"RMS reset cleared RAM bits");
        @(negedge clk);reset=0;quiet();
        #1;if(start_ready)$fatal(1,"RMS reset retained stale load validity");
        load_tables();
    endtask
    initial begin
        if(!$value$plusargs("N=%d",cases) || cases<=0 || cases>MAX_CASES ||
           !$value$plusargs("X=%s",xfile) || !$value$plusargs("GAIN=%s",gainfile) ||
           !$value$plusargs("ANSWER=%s",answerfile) || !$value$plusargs("CLIP=%s",clipfile) ||
           !$value$plusargs("RSQRT=%s",rsqrtfile) || !$value$plusargs("CSV=%s",csvfile) ||
           !$value$plusargs("VCD=%s",wavefile))$fatal(1,"Missing RMS fixtures");
        $readmemh(xfile,xs,0,cases*32-1);$readmemh(gainfile,gains,0,cases*32-1);
        $readmemh(answerfile,answers,0,cases*32-1);$readmemh(clipfile,clips,0,cases*32-1);
        $readmemh(rsqrtfile,rsqrttable);
        csv=$fopen(csvfile,"w");if(csv==0)$fatal(1,"Cannot open RMS trace");
        $fwrite(csv,"case,coordinate,input,gain,result,saturated,error,squares,r,y,k,xy,product,edges\n");
        $dumpfile(wavefile);$dumpvars(0,dut);
        tick();@(negedge clk);reset=0;start=1;tick();
        if(start_ready || busy)$fatal(1,"RMS accepted unloaded inputs");
        @(negedge clk);quiet();
        // Loaded vectors without a valid rsqrt table must report an error.
        load_fixture(0);launch();
        while(!result_valid)begin tick();@(negedge clk);end
        if(error!==1 || result!==0)$fatal(1,"RMS used unloaded rsqrt table");
        result_ready=1;tick();@(negedge clk);quiet();
        load_tables();
        for(integer id=0;id<cases;id=id+1)run_case(id,id);
        abort_after(0);run_case(0,cases);
        abort_after(1000);run_case(0,cases+1);
        abort_after(5000);run_case(0,cases+2);
        $fclose(csv);$display("PASS rmsnorm requests=%0d coordinates=32 reset_probes=3",passed);$finish;
    end
    initial begin #40000000;$fatal(1,"Absolute RMS simulation-time limit");end
endmodule
