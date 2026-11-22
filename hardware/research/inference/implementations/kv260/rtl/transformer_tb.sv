// Full-core loader/token protocol and observed stage traces. No model RAM injection.
// Optional ANSWERS contains original-model golden logits; absent means structural
// smoke only, with archived BOS stage boundaries checked by the Python trace checker.
`timescale 1ns/1ps
module transformer_tb;
    logic clk;
    initial begin clk=0;forever #5 clk=!clk;end
    logic reset=1,weight_valid=0,clear_context=0,token_valid=0,logit_ready=0;
    logic weight_ready,configured,token_ready,busy,logit_valid,saturated,error;
    logic [3:0] weight_bank=0;
    logic [15:0] weight_address=0;
    logic [31:0] weight_value=0;
    logic [8:0] token=256,logit_index,context_count;
    logic signed [31:0] logit;
    logic [4:0] phase;
    transformer dut (.*);
    localparam integer MODEL_WORDS=29281,MAX_STEPS=256;
    logic [31:0] words[0:MODEL_WORDS-1];
    logic [8:0] tokens[0:MAX_STEPS-1];
    logic signed [31:0] answers[0:MAX_STEPS*320-1];
    integer steps=1,stage_csv,step_id=-1,cycle=0,passed=0,total_logits=0;
    bit compare_logits;
    string modelfile,tokenfile,answerfile,csvfile,wavefile;

    function automatic integer bank_length(input integer bank);
        case(bank)
            0:bank_length=10240;
            1,2,3,4:bank_length=1024;
            5,6,7:bank_length=4096;
            8,9,10:bank_length=32;
            11:bank_length=2048;
            13:bank_length=257;
            14:bank_length=256;
            default:bank_length=0;
        endcase
    endfunction
    task automatic event_value(input string stage,input integer index,input longint signed value);
        $fwrite(stage_csv,"%0d,%0d,%s,%0d,%0d\n",step_id,int'($time/10),stage,index,value);
    endtask
    // Configuration valid is independent of ready. Every broadcast recipient
    // must accept exactly the externally accepted word, including refusal of
    // malformed exp/rsqrt values before any configuration counter advances.
    always @(posedge clk)begin
        if(!reset)begin
            if((dut.norm1.scalar.table_valid && dut.norm1.scalar.table_ready)!==
               (dut.accept_weight && (weight_bank==13 || weight_bank==14)))$fatal(1,"Partial norm1 table broadcast");
            if((dut.norm2.scalar.table_valid && dut.norm2.scalar.table_ready)!==
               (dut.accept_weight && (weight_bank==13 || weight_bank==14)))$fatal(1,"Partial norm2 table broadcast");
            if((dut.normfinal.scalar.table_valid && dut.normfinal.scalar.table_ready)!==
               (dut.accept_weight && (weight_bank==13 || weight_bank==14)))$fatal(1,"Partial final-norm table broadcast");
            if((dut.ff.scalar.table_valid && dut.ff.scalar.table_ready)!==
               (dut.accept_weight && weight_bank==13))$fatal(1,"Partial feed-forward table broadcast");
            if((dut.att.scalar.table_valid && dut.att.scalar.table_ready)!==
               (dut.accept_weight && weight_bank==13))$fatal(1,"Partial attention table broadcast");
            if((dut.front.coefficient_valid && dut.front.coefficient_ready)!==
               (dut.accept_weight && weight_bank==11))$fatal(1,"Partial RoPE coefficient load");
            if((dut.logits.weight_valid && dut.logits.weight_ready)!==
               (dut.accept_weight && weight_bank==0))$fatal(1,"Partial tied-head weight load");
            if((dut.output_projection.weight_valid && dut.output_projection.weight_ready)!==
               (dut.accept_weight && weight_bank==4))$fatal(1,"Partial output projection weight load");
            if((dut.ff.weight_valid && dut.ff.weight_ready)!==
               (dut.accept_weight && weight_bank>=5 && weight_bank<=7))$fatal(1,"Partial feed-forward weight load");
            if(!configured && (dut.front.load_valid && dut.front.load_ready)!==
               (dut.accept_weight && weight_bank>=1 && weight_bank<=3))$fatal(1,"Partial QKV weight load");
        end
    end
    // Observe the values accepted by each stage, before its clock-edge update.
    // These are read-only hierarchical taps, never substitutes for neural input.
    always @(posedge clk)begin
        if(!reset && step_id>=0)begin
            if(phase==2 && dut.n1_load_ready)event_value("embed",int'(dut.coordinate),longint'(dut.embed_value));
            if(dut.n1_valid && dut.n1_ready)event_value("norm1",int'(dut.n1_index),longint'(dut.n1_result));
            if(dut.front.projection.result_valid && dut.front.projection.result_ready)begin
                if(dut.front.mac_row<32)event_value("q",int'(dut.front.mac_row),longint'(dut.front.mac_result));
                else if(dut.front.mac_row<64)event_value("k",int'(dut.front.mac_row)-32,longint'(dut.front.mac_result));
                else event_value("v",int'(dut.front.mac_row)-64,longint'(dut.front.mac_result));
            end
            if(dut.front.rotation.result_valid && dut.front.rotation.result_ready)begin
                if(dut.front.rope_index_a<32)begin
                    event_value("qrot",int'(dut.front.rope_index_a),longint'(dut.front.rope_a));
                    event_value("qrot",int'(dut.front.rope_index_b),longint'(dut.front.rope_b));
                end else begin
                    event_value("krot",int'(dut.front.rope_index_a)-32,longint'(dut.front.rope_a));
                    event_value("krot",int'(dut.front.rope_index_b)-32,longint'(dut.front.rope_b));
                end
            end
            if(dut.front.cache.write_valid && dut.front.cache.write_ready)begin
                event_value("cache_k",int'(dut.front.cache.write_position)*32+int'(dut.front.cache.write_coordinate),longint'(dut.front.cache.write_k));
                event_value("cache_v",int'(dut.front.cache.write_position)*32+int'(dut.front.cache.write_coordinate),longint'(dut.front.cache.write_v));
            end
            if(dut.att.score_valid)event_value("scores",int'(dut.att.score_head)*256+int'(dut.att.score_position),longint'(dut.att.score_value));
            if(dut.att.exp_valid)event_value("exp",int'(dut.att.exp_head)*256+int'(dut.att.exp_position),longint'({1'b0,dut.att.exp_value}));
            if(dut.att.probability_valid)event_value("prob",int'(dut.att.probability_head)*256+int'(dut.att.probability_position),longint'({1'b0,dut.att.probability_value}));
            if(dut.att_valid && dut.att_ready)event_value("context",int'(dut.att_index),longint'(dut.att_result));
            if(dut.o_valid && dut.o_ready)begin
                event_value("o",int'(dut.o_row),longint'(dut.o_result));
                event_value("res1",int'(dut.o_row),longint'(dut.res1_value));
            end
            if(dut.n2_valid && dut.n2_ready)event_value("norm2",int'(dut.n2_index),longint'(dut.n2_result));
            if(dut.ff_element_valid)begin
                event_value("gate",int'(dut.ff_element_index),longint'(dut.ff_element_gate));
                event_value("up",int'(dut.ff_element_index),longint'(dut.ff_element_up));
                event_value("silu",int'(dut.ff_element_index),longint'(dut.ff_element_silu));
                event_value("hidden",int'(dut.ff_element_index),longint'(dut.ff_element_hidden));
                event_value("ff_clips",int'(dut.ff_element_index),longint'({1'b0,dut.ff_element_clip}));
            end
            if(dut.ff_valid && dut.ff_ready)begin
                event_value("down",int'(dut.ff_row),longint'(dut.ff_result));
                event_value("res2",int'(dut.ff_row),longint'(dut.res2_value));
            end
            if(dut.nf_valid && dut.nf_ready)event_value("normfinal",int'(dut.nf_index),longint'(dut.nf_result));
            if(logit_valid && logit_ready)event_value("logits",int'(logit_index),longint'(logit));
        end
    end

    task automatic tick;
        @(posedge clk);#1;cycle=int'($time/10);
        if(error)$fatal(1,"Transformer error at phase %0d step %0d cycle %0d",phase,step_id,cycle);
    endtask
    task automatic quiet;
        weight_valid=0;token_valid=0;clear_context=0;logit_ready=0;
    endtask
    task automatic reject_load(input integer bank,input integer address);
        @(negedge clk);quiet();weight_valid=1;weight_bank=4'(bank);weight_address=16'(address);weight_value=32'h12345678;
        #1;if(weight_ready)$fatal(1,"Invalid ordered load accepted");tick();
        @(negedge clk);quiet();
    endtask
    task automatic reject_table_value(input integer bank,input logic [31:0] value);
        @(negedge clk);quiet();weight_valid=1;weight_bank=4'(bank);weight_address=0;weight_value=value;
        #1;if(weight_ready)$fatal(1,"Invalid nonlinear table value accepted");tick();
        @(negedge clk);quiet();
    endtask
    task automatic load_model;
        integer offset;
        offset=0;
        for(integer bank=0;bank<15;bank=bank+1)begin
            if(bank==13)reject_table_value(bank,32'h80000001);
            if(bank==14)begin reject_table_value(bank,0);reject_table_value(bank,32'h40000001);end
            for(integer word_number=0;word_number<bank_length(bank);word_number=word_number+1)begin
                @(negedge clk);quiet();weight_valid=1;weight_bank=4'(bank);weight_address=16'(word_number);weight_value=words[offset];
                #1;if(!weight_ready)$fatal(1,"Ordered load not ready: bank %0d word %0d",bank,word_number);
                tick();offset=offset+1;
                if(configured!=(offset==MODEL_WORDS))$fatal(1,"Configuration completion count differs");
            end
        end
        if(offset!=MODEL_WORDS)$fatal(1,"Model word count differs");
        @(negedge clk);quiet();
    endtask
    task automatic run_token(input integer id,input integer label_id,input bit replay);
        integer outputs,elapsed,before_count;
        logic signed [31:0] held_logit;
        logic held_saturation;
        step_id=label_id;before_count=int'(context_count);
        @(negedge clk);quiet();token_valid=1;token=tokens[id];
        #1;if(!token_ready)$fatal(1,"Token was not ready");tick();
        if(!busy)$fatal(1,"Token did not start");
        @(negedge clk);quiet();outputs=0;elapsed=0;
        while(outputs<320)begin
            // These requests must all be ignored while neural work is running.
            token_valid=1;token=511;weight_valid=1;weight_bank=0;weight_address=0;weight_value=32'hffff1234;clear_context=1;
            if(logit_valid)begin
                if(int'(logit_index)!=outputs)$fatal(1,"Logit order differs");
                if(compare_logits && logit!=answers[(replay ? 0:id)*320+outputs])$fatal(1,"Golden logit mismatch step %0d index %0d",label_id,outputs);
                held_logit=logit;held_saturation=saturated;
                for(integer stall=0;stall<1+(outputs+id)%4;stall=stall+1)begin
                    tick();
                    if(!logit_valid || int'(logit_index)!=outputs || logit!=held_logit || saturated!=held_saturation ||
                       token_ready || weight_ready || int'(context_count)!=before_count+1)$fatal(1,"Logit/backpressure changed");
                    @(negedge clk);
                end
                quiet();logit_ready=1;tick();outputs=outputs+1;total_logits=total_logits+1;
                if(logit_valid || busy!=(outputs<320))$fatal(1,"Logit completion/early idle differs");
                @(negedge clk);quiet();
            end else begin
                tick();elapsed=elapsed+1;
                if(!busy || token_ready || weight_ready)$fatal(1,"Busy request was accepted");
                @(negedge clk);
            end
            if(elapsed>350000)$fatal(1,"Bounded token latency exceeded at phase %0d",phase);
        end
        if(int'(context_count)!=before_count+1 || !configured)$fatal(1,"Token context/configuration differs");
        passed=passed+1;
    endtask

    initial begin
        if(!$value$plusargs("STEPS=%d",steps) || steps<1 || steps>MAX_STEPS ||
           !$value$plusargs("MODEL=%s",modelfile) || !$value$plusargs("TOKENS=%s",tokenfile) ||
           !$value$plusargs("CSV=%s",csvfile))$fatal(1,"Missing full-core fixtures");
        compare_logits=$value$plusargs("ANSWERS=%s",answerfile);
        $readmemh(modelfile,words);$readmemh(tokenfile,tokens,0,steps-1);
        if(tokens[0]!=256)$fatal(1,"First token must be BOS");
        if(compare_logits)$readmemh(answerfile,answers,0,steps*320-1);
        stage_csv=$fopen(csvfile,"w");if(stage_csv==0)$fatal(1,"Cannot open stage trace");
        $fwrite(stage_csv,"step,cycle,stage,index,value\n");
        // Mandatory accepted-value CSV remains complete. Large context tests may
        // omit the expensive internal waveform under the same wall watchdog.
        if($value$plusargs("VCD=%s",wavefile))begin $dumpfile(wavefile);$dumpvars(0,dut);end
        tick();@(negedge clk);reset=0;
        token_valid=1;token=256;tick();if(token_ready || busy)$fatal(1,"Unconfigured token accepted");
        @(negedge clk);quiet();reject_load(12,0);reject_load(0,1);reject_load(1,0);load_model();
        reject_load(14,255);
        token=0;#1;if(token_ready)$fatal(1,"Non-BOS first token accepted");
        token=320;#1;if(token_ready)$fatal(1,"Invalid token accepted");token=256;
        for(integer id=0;id<steps;id=id+1)run_token(id,id,0);
        // Idle context clear retains the loaded model and permits a fresh BOS.
        step_id=-1;quiet();clear_context=1;tick();
        if(context_count!=0 || !configured || busy)$fatal(1,"Idle context clear failed");
        @(negedge clk);quiet();run_token(0,steps,1);
        $fclose(stage_csv);
        $display("PASS transformer requests=%0d logits=%0d golden_logits=%0d clear_replays=1",passed,total_logits,compare_logits);
        $finish;
    end
    initial begin #1000000000;$fatal(1,"Absolute full-core simulation-time limit");end
endmodule
