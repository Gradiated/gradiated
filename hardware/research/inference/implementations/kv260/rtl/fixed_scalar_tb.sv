// Behavioural protocol/arithmetic tests; Python supplies independent expected bits.
`timescale 1ns/1ps
module fixed_scalar_tb;
    logic clk;
    initial begin clk=0;forever #5 clk=!clk;end
    logic reset=1,cmd_valid=0,cmd_ready,table_valid=0,table_ready,table_kind=0;
    logic [2:0] cmd_op=0;
    logic signed [63:0] cmd_a=0,cmd_b=0,result;
    logic signed [7:0] cmd_shift=0,result_exponent;
    logic [8:0] table_index=0;
    logic [31:0] table_value=0;
    logic result_valid,result_ready=0,error;
    fixed_scalar dut(.*);
    localparam integer MAX_CASES=4096;
    logic [7:0] ops[0:MAX_CASES-1],errs[0:MAX_CASES-1];
    logic signed [63:0] aa[0:MAX_CASES-1],bb[0:MAX_CASES-1],answers[0:MAX_CASES-1];
    logic signed [7:0] shifts[0:MAX_CASES-1],exponents[0:MAX_CASES-1];
    logic [31:0] exptable[0:256],rsqrttable[0:255];
    integer cases,csv,cycle=0,passed=0;
    string opfile,afile,bfile,shiftfile,answerfile,exponentfile,errorfile,expfile,rsqrtfile,csvfile,wavefile;
    task automatic tick;
        @(posedge clk);#1;cycle=int'($time/10);
    endtask
    task automatic load_tables;
        for(integer i=0;i<513;i=i+1)begin
            table_valid=1;cmd_valid=0;table_kind=i>=257;
            table_index=9'(i<257 ? i:i-257);
            table_value=i<257 ? exptable[i]:rsqrttable[i-257];
            #1;if(!table_ready)$fatal(1,"Valid table load not ready");
            tick();@(negedge clk);
        end
        table_valid=0;
    endtask
    task automatic missing_table;
        cmd_op=3;cmd_a=0;cmd_valid=1;tick();@(negedge clk);cmd_valid=0;
        while(!result_valid)begin tick();@(negedge clk);end
        if(error!==1 || result!==0)$fatal(1,"Missing table was used");
        result_ready=1;tick();@(negedge clk);result_ready=0;
    endtask
    task automatic run_case(input integer id);
        integer edges,stalls;
        cmd_op=ops[id][2:0];cmd_a=aa[id];cmd_b=bb[id];cmd_shift=shifts[id];cmd_valid=1;
        #1;if(!cmd_ready)$fatal(1,"Command not ready while idle");
        tick();edges=1;@(negedge clk);cmd_valid=0;
        while(!result_valid)begin
            // Busy commands/table writes must be refused without changing work.
            cmd_valid=1;cmd_op=7;cmd_a=64'sd1234;cmd_b=-64'sd99;table_valid=1;
            table_value=32'h1234;table_index=0;tick();edges=edges+1;
            if(cmd_ready || table_ready)$fatal(1,"Busy request accepted");
            if(edges>650)$fatal(1,"Scalar command exceeded bounded latency");
            @(negedge clk);
        end
        if(result!==answers[id] || result_exponent!==exponents[id] || error!==errs[id][0])
            $fatal(1,"Scalar mismatch case %0d op %0d got %0d exp %0d err %0d",id,ops[id],result,result_exponent,error);
        stalls=1+id%5;
        repeat(stalls)begin
            tick();
            if(!result_valid || cmd_ready || table_ready || result!==answers[id] ||
               result_exponent!==exponents[id] || error!==errs[id][0])$fatal(1,"Scalar result changed under backpressure");
            @(negedge clk);
        end
        $fwrite(csv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",id,ops[id],aa[id],bb[id],shifts[id],
            result,result_exponent,error,edges,stalls);
        cmd_valid=0;table_valid=0;result_ready=1;tick();
        if(result_valid)$fatal(1,"Result acceptance failed");
        @(negedge clk);result_ready=0;passed=passed+1;
    endtask
    initial begin
        if(!$value$plusargs("N=%d",cases) || cases<=0 || cases>MAX_CASES ||
           !$value$plusargs("OP=%s",opfile) || !$value$plusargs("A=%s",afile) || !$value$plusargs("B=%s",bfile) ||
           !$value$plusargs("SHIFT=%s",shiftfile) || !$value$plusargs("ANSWER=%s",answerfile) ||
           !$value$plusargs("EXPONENT=%s",exponentfile) || !$value$plusargs("ERROR=%s",errorfile) ||
           !$value$plusargs("EXP=%s",expfile) || !$value$plusargs("RSQRT=%s",rsqrtfile) ||
           !$value$plusargs("CSV=%s",csvfile) || !$value$plusargs("VCD=%s",wavefile))$fatal(1,"Missing scalar fixtures");
        $readmemh(opfile,ops,0,cases-1);$readmemh(afile,aa,0,cases-1);$readmemh(bfile,bb,0,cases-1);
        $readmemh(shiftfile,shifts,0,cases-1);$readmemh(answerfile,answers,0,cases-1);
        $readmemh(exponentfile,exponents,0,cases-1);$readmemh(errorfile,errs,0,cases-1);
        $readmemh(expfile,exptable);$readmemh(rsqrtfile,rsqrttable);
        csv=$fopen(csvfile,"w");if(csv==0)$fatal(1,"Cannot open CSV");
        $fwrite(csv,"case,op,a,b,shift,result,exponent,error,edges,stalls\n");
        $dumpfile(wavefile);$dumpvars(0,dut);
        tick();@(negedge clk);reset=0;
        missing_table();
        // Simultaneous idle command/configuration requests are both refused.
        cmd_valid=1;table_valid=1;tick();
        if(cmd_ready || table_ready || result_valid)$fatal(1,"Conflicting idle requests accepted");
        @(negedge clk);cmd_valid=0;table_valid=1;table_kind=0;table_index=257;table_value=1;
        #1;if(table_ready)$fatal(1,"Invalid exp index accepted");
        table_index=0;table_value=32'h80000001;
        #1;if(table_ready)$fatal(1,"Invalid exp value accepted");
        table_kind=1;table_index=256;table_value=1;
        #1;if(table_ready)$fatal(1,"Invalid rsqrt index accepted");
        table_index=0;table_value=0;
        #1;if(table_ready)$fatal(1,"Invalid rsqrt zero accepted");
        table_value=32'h40000001;
        #1;if(table_ready)$fatal(1,"Invalid rsqrt value accepted");
        load_tables();
        for(integer id=0;id<cases;id=id+1)run_case(id);
        // Cancel a division, then verify an old RAM word survives but is invalid.
        cmd_valid=1;cmd_op=1;cmd_a=64'sh7fff_ffff_ffff_ffff;cmd_b=3;tick();
        @(negedge clk);cmd_valid=0;
        repeat(7)begin tick();@(negedge clk);end
        reset=1;tick();
        if(result_valid || error || result!==0)$fatal(1,"Reset did not cancel scalar command");
        if(dut.exp_memory[0]!==exptable[0])$fatal(1,"Reset cleared table RAM");
        @(negedge clk);reset=0;missing_table();load_tables();run_case(cases-1);
        // A held output is also cancelled by reset.
        cmd_valid=1;cmd_op=0;cmd_a=7;cmd_shift=0;tick();
        @(negedge clk);cmd_valid=0;
        if(!result_valid)$fatal(1,"Output reset setup failed");
        reset=1;tick();if(result_valid)$fatal(1,"Reset left a held result valid");
        $fclose(csv);$display("PASS fixed_scalar requests=%0d reset_probes=2",passed);$finish;
    end
    initial begin #30000000;$fatal(1,"Absolute scalar simulation-time limit");end
endmodule
