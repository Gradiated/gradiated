// Synthetic normalized inputs with pinned real weights/tables; independent expected arrays.
`timescale 1ns/1ps
module feedforward_tb;
    logic clk;
    initial begin clk=0;forever #5 clk=!clk;end
    logic reset=1,input_valid=0,weight_valid=0,table_valid=0,start=0,result_ready=0;
    logic input_ready,weight_ready,table_ready,start_ready,busy,result_valid,saturated,error,element_valid;
    logic [7:0] input_address=0,weight_address=0;
    logic signed [15:0] input_value=0,weight_value=0,result;
    logic [1:0] weight_bank=0;
    logic [8:0] weight_row=0,table_index=0,result_row;
    logic [31:0] table_value=0;
    logic [6:0] element_index;
    logic signed [15:0] element_gate,element_up,element_silu,element_hidden;
    logic [3:0] element_saturated;
    feedforward dut (.*);
    localparam integer MAX_CASES=8;
    logic signed [15:0] xs[0:MAX_CASES*32-1],gates[0:4095],ups[0:4095],downs[0:4095];
    logic [31:0] exps[0:256];
    logic signed [15:0] e_gate[0:MAX_CASES*128-1],e_up[0:MAX_CASES*128-1];
    logic signed [15:0] e_silu[0:MAX_CASES*128-1],e_hidden[0:MAX_CASES*128-1],answers[0:MAX_CASES*32-1];
    logic [7:0] e_clips[0:MAX_CASES*128-1],clips[0:MAX_CASES*32-1];
    integer cases,csv,case_id=-1,cycle=0,passed=0,total_elements=0,total_outputs=0;
    string xfile,gfile,ufile,dfile,expfile,egfile,eufile,esfile,ehfile,ecfile,answerfile,clipfile,csvfile,wavefile;
    // Both dense inputs receive the same offered word. Their address checks
    // must yield one shared acceptance; ready must never feed their own valid.
    always @(posedge clk)begin
        if(!reset)begin
            if((dut.gate_dense.input_valid && dut.gate_dense.input_ready)!==(input_valid && input_ready))
                $fatal(1,"Partial gate input acceptance");
            if((dut.up_dense.input_valid && dut.up_dense.input_ready)!==(input_valid && input_ready))
                $fatal(1,"Partial up input acceptance");
            if((dut.gate_dense.weight_valid && dut.gate_dense.weight_ready)!==(weight_valid && weight_ready && weight_bank==0))
                $fatal(1,"Partial gate weight acceptance");
            if((dut.up_dense.weight_valid && dut.up_dense.weight_ready)!==(weight_valid && weight_ready && weight_bank==1))
                $fatal(1,"Partial up weight acceptance");
            if((dut.down_dense.weight_valid && dut.down_dense.weight_ready)!==(weight_valid && weight_ready && weight_bank==2))
                $fatal(1,"Partial down weight acceptance");
            if((dut.scalar.table_valid && dut.scalar.table_ready)!==(table_valid && table_ready))
                $fatal(1,"Partial scalar table acceptance");
        end
    end
    task automatic tick;
        @(posedge clk);#1;cycle=int'($time/10);
        $fwrite(csv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            case_id,cycle,dut.state,busy,start_ready,input_ready,weight_ready,table_ready,error,
            element_valid,element_index,element_gate,element_up,element_silu,element_hidden,
            element_saturated,result_valid,result_row,result,saturated);
    endtask
    task automatic quiet;
        input_valid=0;weight_valid=0;table_valid=0;start=0;result_ready=0;
    endtask
    task automatic load_tables;
        for(integer j=0;j<257;j=j+1)begin
            @(negedge clk);quiet();table_valid=1;table_index=9'(j);table_value=exps[j];tick();
            if(!table_ready || busy)$fatal(1,"Table load not accepted");
        end
        @(negedge clk);quiet();
    endtask
    task automatic load_weights;
        for(integer bank=0;bank<3;bank=bank+1)begin
            for(integer r=0;r<(bank==2 ? 32:128);r=r+1)begin
                for(integer j=0;j<(bank==2 ? 128:32);j=j+1)begin
                    @(negedge clk);quiet();weight_valid=1;weight_bank=2'(bank);weight_row=9'(r);weight_address=8'(j);
                    weight_value=bank==0 ? gates[r*32+j] : bank==1 ? ups[r*32+j] : downs[r*128+j];tick();
                    if(!weight_ready || busy)$fatal(1,"Weight load not accepted");
                end
            end
        end
        @(negedge clk);quiet();
    endtask
    task automatic load_input(input integer id);
        for(integer j=0;j<32;j=j+1)begin
            @(negedge clk);quiet();input_valid=1;input_address=8'(j);input_value=xs[id*32+j];tick();
            if(!input_ready || busy)$fatal(1,"Input load not accepted");
        end
        @(negedge clk);quiet();
    endtask
    task automatic launch;
        start=1;tick();
        if(!busy || start_ready || input_ready || weight_ready || table_ready)$fatal(1,"Start failed");
        @(negedge clk);start=0;
    endtask
    task automatic run_case(input integer id,input integer label_id,input bit reload);
        integer seen,outputs,elapsed;
        case_id=label_id;
        if(reload)load_input(id);
        launch();seen=0;outputs=0;elapsed=0;
        while(outputs<32)begin
            // Attempted writes/starts while running must not alter any payload.
            input_valid=1;weight_valid=1;table_valid=1;start=(elapsed%3)==0;
            input_address=0;input_value=-16'sd1234;weight_bank=0;weight_row=0;weight_address=0;weight_value=16'sd4321;
            table_index=0;table_value=32'd17;
            tick();elapsed=elapsed+1;
            if(error || !busy || start_ready || input_ready || weight_ready || table_ready)$fatal(1,"Busy work/handshake failed");
            if(element_valid)begin
                if(seen>=128 || int'(element_index)!=seen || element_gate!=e_gate[id*128+seen] ||
                   element_up!=e_up[id*128+seen] || element_silu!=e_silu[id*128+seen] ||
                   element_hidden!=e_hidden[id*128+seen] || element_saturated!=e_clips[id*128+seen][3:0])
                    $fatal(1,"Element mismatch case %0d index %0d",id,seen);
                seen=seen+1;total_elements=total_elements+1;
            end
            @(negedge clk);
            if(result_valid)begin
                if(seen!=128 || int'(result_row)!=outputs || result!=answers[id*32+outputs] || saturated!=clips[id*32+outputs][0])
                    $fatal(1,"Down projection mismatch case %0d row %0d",id,outputs);
                for(integer stall=0;stall<1+(id+outputs)%4;stall=stall+1)begin
                    tick();
                    if(!result_valid || error || int'(result_row)!=outputs || result!=answers[id*32+outputs] || saturated!=clips[id*32+outputs][0])
                        $fatal(1,"Result changed under stall");
                    @(negedge clk);
                end
                quiet();result_ready=1;tick();outputs=outputs+1;total_outputs=total_outputs+1;
                if(result_valid || (outputs==32 && busy))$fatal(1,"Output completion failed");
                @(negedge clk);quiet();
            end
            if(elapsed>150000)$fatal(1,"Bounded feed-forward latency exceeded");
        end
        passed=passed+1;
    endtask
    task automatic abort_after(input integer edges);
        case_id=-1;load_input(0);launch();
        repeat(edges)begin tick();@(negedge clk);end
        reset=1;quiet();tick();
        if(busy || result_valid || element_valid || error)$fatal(1,"Reset did not cancel feed-forward");
        if(dut.gate_dense.input_memory[0]!=xs[0] || dut.gate_dense.weight_memory[0]!=gates[0])$fatal(1,"Reset changed dense RAM bits");
        @(negedge clk);reset=0;load_tables();
    endtask
    initial begin
        if(!$value$plusargs("CASES=%d",cases) || cases<1 || cases>MAX_CASES ||
           !$value$plusargs("X=%s",xfile) || !$value$plusargs("GATE=%s",gfile) || !$value$plusargs("UP=%s",ufile) ||
           !$value$plusargs("DOWN=%s",dfile) || !$value$plusargs("EXP=%s",expfile) || !$value$plusargs("EGATE=%s",egfile) ||
           !$value$plusargs("EUP=%s",eufile) || !$value$plusargs("ESILU=%s",esfile) || !$value$plusargs("EHIDDEN=%s",ehfile) ||
           !$value$plusargs("ECLIPS=%s",ecfile) || !$value$plusargs("ANSWERS=%s",answerfile) ||
           !$value$plusargs("CLIPS=%s",clipfile) || !$value$plusargs("CSV=%s",csvfile) || !$value$plusargs("VCD=%s",wavefile))$fatal(1,"Missing fixtures");
        $readmemh(xfile,xs,0,cases*32-1);$readmemh(gfile,gates);$readmemh(ufile,ups);$readmemh(dfile,downs);$readmemh(expfile,exps);
        $readmemh(egfile,e_gate,0,cases*128-1);$readmemh(eufile,e_up,0,cases*128-1);$readmemh(esfile,e_silu,0,cases*128-1);
        $readmemh(ehfile,e_hidden,0,cases*128-1);$readmemh(ecfile,e_clips,0,cases*128-1);
        $readmemh(answerfile,answers,0,cases*32-1);$readmemh(clipfile,clips,0,cases*32-1);
        csv=$fopen(csvfile,"w");if(csv==0)$fatal(1,"Cannot open trace");
        $fwrite(csv,"case,cycle,phase,busy,start_ready,input_ready,weight_ready,table_ready,error,element_valid,element_index,gate,up,silu,hidden,element_clips,result_valid,result_row,result,saturated\n");
        $dumpfile(wavefile);$dumpvars(0,dut);
        tick();@(negedge clk);reset=0;load_weights();
        // Unloaded scalar coefficients must fault rather than use unknown RAM.
        // Fixture1 is zero when supplied by the standard suite, making EXP(0)
        // require table entries0/1 rather than taking the declared cutoff path.
        load_input(cases>1 ? 1:0);launch();
        for(integer watchdog=0;!error;watchdog=watchdog+1)begin
            tick();@(negedge clk);
            if(watchdog>1000)$fatal(1,"Missing-table fault did not arrive");
        end
        if(!result_valid || !busy || result!=0 || input_ready || weight_ready || table_ready)
            $fatal(1,"Missing-table error response failed");
        repeat(3)begin
            result_ready=1;tick();
            if(!error || !result_valid || result!=0)$fatal(1,"Fault response did not hold until reset");
            @(negedge clk);
        end
        reset=1;quiet();tick();
        if(error || busy || result_valid)$fatal(1,"Fault reset failed");
        @(negedge clk);reset=0;load_tables();
        // Wide/invalid indices are refused before narrowing in each dense engine.
        input_valid=1;input_address=128;tick();if(input_ready)$fatal(1,"Invalid input accepted");
        @(negedge clk);quiet();weight_valid=1;weight_bank=3;tick();if(weight_ready)$fatal(1,"Invalid bank accepted");
        @(negedge clk);quiet();weight_valid=1;weight_bank=2;weight_row=32;weight_address=0;tick();if(weight_ready)$fatal(1,"Invalid down row accepted");
        @(negedge clk);quiet();start=1;table_valid=1;tick();if(busy || start_ready || table_ready)$fatal(1,"Conflicting start accepted");
        @(negedge clk);quiet();
        for(integer id=0;id<cases;id=id+1)run_case(id,id,1);
        abort_after(0);run_case(0,cases,0);
        abort_after(65);run_case(0,cases+1,0);
        abort_after(200);run_case(0,cases+2,0);
        // Reset a held final output rather than accepting it.
        case_id=-1;load_input(0);launch();result_ready=1;
        while(!result_valid || result_row!=31)begin tick();@(negedge clk);end
        result_ready=0;reset=1;quiet();tick();
        if(busy || result_valid || error)$fatal(1,"Reset at output failed");
        @(negedge clk);reset=0;load_tables();run_case(0,cases+3,0);
        $fclose(csv);$display("PASS feedforward requests=%0d elements=%0d outputs=%0d reset_probes=4 fault_probes=1",passed,total_elements,total_outputs);$finish;
    end
    initial begin #20000000;$fatal(1,"Absolute simulation-time limit");end
endmodule
