// Behavioural fixture-driven tests. Expected RNE/clipping is independently Python supplied.
`timescale 1ns/1ps
module dense_tb #(
    parameter integer INPUTS = 32,
    parameter integer OUTPUTS = 32,
    parameter integer SHIFT = 15,
    parameter integer RESULT_BITS = 16
);
    logic clk;
    initial begin clk=0; forever #5 clk=!clk; end
    logic reset=1, input_valid=0, weight_valid=0, start=0, result_ready=0;
    logic input_ready, weight_ready, start_ready, busy, result_valid, saturated, step_valid;
    logic [7:0] input_address=0, weight_address=0, step_index;
    logic [8:0] weight_row=0, result_row, step_row;
    logic signed [15:0] input_value=0, weight_value=0, step_input, step_weight;
    logic signed [RESULT_BITS-1:0] result;
    logic signed [31:0] step_product;
    logic signed [47:0] step_sum;
    dense #(.INPUTS(INPUTS),.OUTPUTS(OUTPUTS),.SHIFT(SHIFT),.RESULT_BITS(RESULT_BITS)) dut (.*);
    localparam integer MAX_CASES=64, RESET_PROBES=7;
    logic signed [15:0] xs [0:MAX_CASES*INPUTS-1], ws [0:MAX_CASES*OUTPUTS*INPUTS-1];
    logic signed [RESULT_BITS-1:0] answers [0:MAX_CASES*OUTPUTS-1];
    logic [7:0] clips [0:MAX_CASES*OUTPUTS-1];
    integer cases, csv, case_id=-1, cycle=0, passed=0;
    string xfile,wfile,answerfile,clipfile,csvfile,wavefile;

    task automatic tick;
        @(posedge clk); #1; cycle=int'($time/10);
        $fwrite(csv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            case_id,cycle,dut.state,busy,input_ready,weight_ready,start_ready,
            input_valid,weight_valid,start,result_ready,result_valid,result_row,result,saturated,
            step_valid,step_row,step_index,step_input,step_weight,step_product,step_sum);
    endtask

    task automatic load_fixture(input integer id,input bit weights);
        for(integer r=0;r<(weights ? OUTPUTS : 1);r=r+1) begin
            for(integer j=0;j<INPUTS;j=j+1) begin
                @(negedge clk); input_valid=(r==0); weight_valid=weights; start=0; result_ready=0;
                input_address=8'(j); input_value=xs[id*INPUTS+j];
                weight_row=9'(r); weight_address=8'(j); weight_value=ws[(id*OUTPUTS+r)*INPUTS+j];
                tick();
                if(!input_ready || !weight_ready || busy) $fatal(1,"Idle loading failed");
            end
        end
        @(negedge clk); input_valid=0; weight_valid=0;
    endtask

    task automatic launch;
        start=1; input_valid=0; weight_valid=0; result_ready=0; tick();
        if(!busy || start_ready || input_ready || weight_ready) $fatal(1,"Start failed");
        @(negedge clk);start=0;
    endtask

    task automatic run_case(input integer id,input integer label_id,input bit reload,input bit weights);
        integer seen,elapsed;
        longint signed total,expected_product;
        case_id=label_id;
        if(reload)load_fixture(id,weights);
        launch();
        for(integer r=0;r<OUTPUTS;r=r+1)begin
            seen=0;elapsed=0;total=0;
            while(!result_valid)begin
                // All attempted input/weight writes and starts are refused while busy.
                input_valid=1;weight_valid=1;input_address=0;weight_address=0;weight_row=0;
                input_value=16'sh1234;weight_value=-16'sd1234;start=(elapsed%3)==0;
                tick();elapsed=elapsed+1;
                if(input_ready || weight_ready || start_ready || !busy)$fatal(1,"Busy request accepted");
                if(step_valid)begin
                    if(seen>=INPUTS || int'(step_index)!=seen || int'(step_row)!=r)$fatal(1,"Wrong term tag");
                    expected_product=longint'(xs[id*INPUTS+seen])*longint'(ws[(id*OUTPUTS+r)*INPUTS+seen]);
                    total=total+expected_product;
                    if(step_input!=xs[id*INPUTS+seen] || step_weight!=ws[(id*OUTPUTS+r)*INPUTS+seen] ||
                       longint'(step_product)!=expected_product || longint'(step_sum)!=total)
                        $fatal(1,"Term mismatch case %0d row %0d term %0d",id,r,seen);
                    seen=seen+1;
                end
                if(elapsed>2*INPUTS+2)$fatal(1,"Bounded row latency exceeded");
                @(negedge clk);
            end
            if(seen!=INPUTS || elapsed!=2*INPUTS+1 || int'(result_row)!=r ||
               result!=answers[id*OUTPUTS+r] || saturated!=clips[id*OUTPUTS+r][0])
                $fatal(1,"Output/tag mismatch case %0d row %0d got %0d",id,r,result);
            for(integer stall=0;stall<1+(id+r)%4;stall=stall+1)begin
                start=1;input_valid=1;weight_valid=1;tick();
                if(!result_valid || !busy || step_valid || input_ready || weight_ready || start_ready ||
                   int'(result_row)!=r || result!=answers[id*OUTPUTS+r] || saturated!=clips[id*OUTPUTS+r][0])
                    $fatal(1,"Output changed under backpressure");
                @(negedge clk);
            end
            start=0;input_valid=0;weight_valid=0;result_ready=1;tick();
            if(result_valid || step_valid || busy!=(r<OUTPUTS-1))$fatal(1,"Premature matrix completion");
            @(negedge clk);result_ready=0;
        end
        passed=passed+1;
    endtask

    task automatic abort_after(input integer edges);
        case_id=-1;load_fixture(0,1);launch();result_ready=1;
        repeat(edges)begin tick();@(negedge clk);end
        reset=1;input_valid=0;weight_valid=0;start=0;tick();
        if(busy || result_valid || step_valid || dut.accumulator!=0 || result!=0 || result_row!=0)
            $fatal(1,"Reset did not cancel calculation");
        if(dut.input_memory[0]!=xs[0] || dut.weight_memory[0]!=ws[0])$fatal(1,"Reset erased RAM bits");
        @(negedge clk);reset=0;result_ready=0;
    endtask

    initial begin
        if(INPUTS<1 || INPUTS>128 || OUTPUTS<1 || OUTPUTS>320 || SHIFT<0 || SHIFT>47 ||
           (RESULT_BITS!=16 && RESULT_BITS!=32))$fatal(1,"Unsupported test geometry");
        if(!$value$plusargs("CASES=%d",cases) || cases<2 || cases>MAX_CASES ||
           !$value$plusargs("X=%s",xfile) || !$value$plusargs("W=%s",wfile) ||
           !$value$plusargs("ANSWERS=%s",answerfile) || !$value$plusargs("CLIPS=%s",clipfile) ||
           !$value$plusargs("CSV=%s",csvfile) || !$value$plusargs("VCD=%s",wavefile))$fatal(1,"Missing fixtures");
        $readmemh(xfile,xs,0,cases*INPUTS-1);$readmemh(wfile,ws,0,cases*OUTPUTS*INPUTS-1);
        $readmemh(answerfile,answers,0,cases*OUTPUTS-1);$readmemh(clipfile,clips,0,cases*OUTPUTS-1);
        csv=$fopen(csvfile,"w");if(csv==0)$fatal(1,"Cannot open trace");
        $fwrite(csv,"case,cycle,phase,busy,input_ready,weight_ready,start_ready,input_valid,weight_valid,start,result_ready,result_valid,result_row,result,saturated,step_valid,step_row,step_index,step_input,step_weight,step_product,step_sum\n");
        $dumpfile(wavefile);$dumpvars(0,dut);
        tick();@(negedge clk);reset=0;
        start=1;input_valid=1;weight_valid=1;tick();
        if(busy || start_ready || input_ready || weight_ready)$fatal(1,"Conflicting idle requests accepted");
        @(negedge clk);start=0;input_valid=0;weight_valid=0;
        for(integer j=INPUTS;j<256;j=j+1)begin
            input_valid=1;input_address=8'(j);tick();
            if(input_ready || busy)$fatal(1,"Invalid input address accepted");
            @(negedge clk);
        end
        input_valid=0;input_address=0;
        for(integer r=OUTPUTS;r<512;r=r+1)begin
            weight_valid=1;weight_row=9'(r);weight_address=0;tick();
            if(weight_ready || busy)$fatal(1,"Invalid weight row accepted");
            @(negedge clk);
        end
        weight_row=0;
        for(integer j=INPUTS;j<256;j=j+1)begin
            weight_address=8'(j);tick();
            if(weight_ready || busy)$fatal(1,"Invalid weight coordinate accepted");
            @(negedge clk);
        end
        weight_valid=0;weight_address=0;
        for(integer id=0;id<cases;id=id+1)run_case(id,id,1,id!=1);
        for(integer probe=0;probe<RESET_PROBES;probe=probe+1)begin
            case(probe)
                0:abort_after(0);
                1:abort_after(1);
                2:abort_after(7);
                3:abort_after(2*INPUTS);
                4:abort_after(2*INPUTS+1);
                5:abort_after(2*(2*INPUTS+2)+7);
                6:abort_after((OUTPUTS-1)*(2*INPUTS+2)+2*INPUTS+1);
            endcase
            run_case(0,cases+probe,0,0);
        end
        // Accepted activation-only load changes input while retaining all weights.
        run_case(1,cases+RESET_PROBES,1,0);
        $fclose(csv);
        $display("PASS dense requests=%0d inputs=%0d outputs=%0d shift=%0d bits=%0d reset_probes=%0d",passed,INPUTS,OUTPUTS,SHIFT,RESULT_BITS,RESET_PROBES);
        $finish;
    end
    initial begin #100000000;$fatal(1,"Absolute simulation-time limit");end
endmodule
