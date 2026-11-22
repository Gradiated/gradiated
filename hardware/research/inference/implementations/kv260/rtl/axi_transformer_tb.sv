// BUS PROTOCOL TEST ONLY. The transformer module below is a synthetic stub.
// It deliberately generates recognisable integers, not neural-network logits.
`timescale 1ns/1ps
module axi_transformer_tb;
    logic aclk;
    initial begin aclk=0;forever #5 aclk=!aclk;end
    logic aresetn=0;
    logic [7:0] s_axi_awaddr=0,s_axi_araddr=0;
    logic [2:0] s_axi_awprot=0,s_axi_arprot=0;
    logic s_axi_awvalid=0,s_axi_awready,s_axi_wvalid=0,s_axi_wready,s_axi_bvalid,s_axi_bready=0;
    logic s_axi_arvalid=0,s_axi_arready,s_axi_rvalid,s_axi_rready=0;
    logic [31:0] s_axi_wdata=0,s_axi_rdata;
    logic [3:0] s_axi_wstrb=4'hf;
    logic [1:0] s_axi_bresp,s_axi_rresp;
    axi_transformer dut (.*);
    integer csv,cycle=0,writes=0,reads=0;
    string csvfile,wavefile;
    localparam logic [1:0] OKAY=0,SLVERR=2;
    task automatic tick;
        @(posedge aclk);#1;cycle=int'($time/10);
    endtask
    always @(posedge aclk)begin
        $fwrite(csv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
            int'($time/10),aresetn,s_axi_awvalid,s_axi_awready,s_axi_awaddr,s_axi_wvalid,s_axi_wready,s_axi_wdata,s_axi_wstrb,
            s_axi_bvalid,s_axi_bready,s_axi_bresp,s_axi_arvalid,s_axi_arready,s_axi_araddr,s_axi_rvalid,s_axi_rready,s_axi_rresp,s_axi_rdata,
            dut.core.accepted_weights,dut.core.accepted_tokens,dut.core.accepted_logits,dut.core.clear_count,dut.core.reset_count,
            dut.core_logit_index,dut.core_error,dut.core_configured,dut.core_busy,dut.core_logit_valid,
            dut.core_saturated,dut.core_context_count,dut.soft_reset);
    end
    task automatic quiet;
        s_axi_awvalid=0;s_axi_wvalid=0;s_axi_bready=0;s_axi_arvalid=0;s_axi_rready=0;
    endtask
    task automatic send_aw(input logic [7:0] address);
        bit accepted;
        @(negedge aclk);s_axi_awaddr=address;s_axi_awvalid=1;accepted=0;
        while(!accepted)begin #1;accepted=s_axi_awready;tick();if(!accepted)@(negedge aclk);end
        @(negedge aclk);s_axi_awvalid=0;
    endtask
    task automatic send_w(input logic [31:0] data,input logic [3:0] strobe);
        bit accepted;
        @(negedge aclk);s_axi_wdata=data;s_axi_wstrb=strobe;s_axi_wvalid=1;accepted=0;
        while(!accepted)begin #1;accepted=s_axi_wready;tick();if(!accepted)@(negedge aclk);end
        @(negedge aclk);s_axi_wvalid=0;
    endtask
    task automatic send_both(input logic [7:0] address,input logic [31:0] data,input logic [3:0] strobe);
        @(negedge aclk);s_axi_awaddr=address;s_axi_awvalid=1;s_axi_wdata=data;s_axi_wstrb=strobe;s_axi_wvalid=1;
        #1;if(!s_axi_awready || !s_axi_wready)$fatal(1,"Write channels not ready");tick();
        @(negedge aclk);s_axi_awvalid=0;s_axi_wvalid=0;
    endtask
    task automatic finish_b(input logic [1:0] wanted);
        integer watchdog;
        watchdog=0;
        while(!s_axi_bvalid)begin tick();@(negedge aclk);watchdog=watchdog+1;if(watchdog>20)$fatal(1,"No write response");end
        if(s_axi_bresp!=wanted)$fatal(1,"Write response differs: %0d wanted %0d",s_axi_bresp,wanted);
        repeat(3)begin
            // Additional addresses/data cannot enter while this response is held.
            s_axi_awvalid=1;s_axi_wvalid=1;s_axi_awaddr=8'h7c;s_axi_wdata=32'hdeadcafe;
            tick();
            if(!s_axi_bvalid || s_axi_bresp!=wanted || s_axi_awready || s_axi_wready)$fatal(1,"Write response/backpressure changed");
            @(negedge aclk);
        end
        s_axi_awvalid=0;s_axi_wvalid=0;s_axi_bready=1;tick();
        if(s_axi_bvalid)$fatal(1,"Write response not accepted");
        @(negedge aclk);s_axi_bready=0;writes=writes+1;
    endtask
    task automatic write_reg(input logic [7:0] address,input logic [31:0] data,input logic [3:0] strobe,input integer order,input logic [1:0] wanted);
        if(order==0)send_both(address,data,strobe);
        else if(order==1)begin send_aw(address);repeat(2)begin tick();@(negedge aclk);if(s_axi_bvalid)$fatal(1,"Write executed without data");end send_w(data,strobe);end
        else begin send_w(data,strobe);repeat(2)begin tick();@(negedge aclk);if(s_axi_bvalid)$fatal(1,"Write executed without address");end send_aw(address);end
        finish_b(wanted);
    endtask
    task automatic send_ar(input logic [7:0] address);
        @(negedge aclk);s_axi_araddr=address;s_axi_arvalid=1;
        #1;if(!s_axi_arready)$fatal(1,"Read address not ready");tick();
        @(negedge aclk);s_axi_arvalid=0;
        if(!s_axi_rvalid)$fatal(1,"No captured read response");
    endtask
    task automatic finish_r(input logic [1:0] wanted,input logic [31:0] data,input bit consumes);
        integer old_reads;
        old_reads=dut.core.accepted_logits;
        if(s_axi_rresp!=wanted || s_axi_rdata!=data)$fatal(1,"Read response differs: data %0h wanted %0h resp %0d wanted %0d",s_axi_rdata,data,s_axi_rresp,wanted);
        repeat(3)begin
            s_axi_arvalid=1;s_axi_araddr=8'h04;tick();
            if(!s_axi_rvalid || s_axi_rresp!=wanted || s_axi_rdata!=data || s_axi_arready || dut.core.accepted_logits!=old_reads)
                $fatal(1,"Read response changed or logit consumed under backpressure");
            @(negedge aclk);
        end
        s_axi_arvalid=0;s_axi_rready=1;tick();
        if(s_axi_rvalid || dut.core.accepted_logits!=old_reads+int'(consumes))$fatal(1,"Read consumed logit wrong number of times");
        @(negedge aclk);s_axi_rready=0;reads=reads+1;
    endtask
    task automatic read_reg(input logic [7:0] address,input logic [1:0] wanted,input logic [31:0] data,input bit consumes);
        send_ar(address);finish_r(wanted,data,consumes);
    endtask
    task automatic reset_bus;
        @(negedge aclk);quiet();aresetn=0;repeat(2)begin tick();@(negedge aclk);end
        if(s_axi_bvalid || s_axi_rvalid || s_axi_awready || s_axi_arready || s_axi_wready)$fatal(1,"Bus reset did not clear channels");
        aresetn=1;
    endtask
    task automatic configure_stub;
        write_reg(8'h04,0,4'hf,1,OKAY);write_reg(8'h08,0,4'hf,2,OKAY);
        write_reg(8'h0c,32'h12345678,4'hf,0,OKAY);
        read_reg(8'h08,OKAY,1,0);
        write_reg(8'h0c,32'h87654321,4'hf,1,OKAY);
        read_reg(8'h08,OKAY,2,0);read_reg(8'h00,OKAY,32'h21,0);read_reg(8'h20,OKAY,0,0);
    endtask
    function automatic logic [31:0] synthetic_logit(input integer tok,input integer index);
        synthetic_logit=32'(tok*65536+index-1000);
    endfunction
    initial begin
        integer old_count,old_reset,old_tokens,old_clear;
        if(!$value$plusargs("CSV=%s",csvfile) || !$value$plusargs("VCD=%s",wavefile))$fatal(1,"Missing bus trace paths");
        csv=$fopen(csvfile,"w");if(csv==0)$fatal(1,"Cannot open bus trace");
        $fwrite(csv,"cycle,resetn,awvalid,awready,awaddr,wvalid,wready,wdata,wstrb,bvalid,bready,bresp,arvalid,arready,araddr,rvalid,rready,rresp,rdata,core_weights,core_tokens,core_reads,core_clears,core_resets,core_index,core_error,core_configured,core_busy,core_logit_valid,core_saturated,core_context,soft_reset\n");
        $dumpfile(wavefile);$dumpvars(0,dut);
        repeat(2)begin tick();@(negedge aclk);end aresetn=1;
        read_reg(8'h00,OKAY,32'h40,0);read_reg(8'h20,OKAY,0,0);read_reg(8'h18,SLVERR,0,0);
        // All byte strobes, alignment, reserved values and RO/WO directions.
        write_reg(8'h04,12,4'hf,0,SLVERR);write_reg(8'h04,15,4'hf,1,SLVERR);
        write_reg(8'h04,16,4'hf,2,SLVERR);write_reg(8'h08,32'h10000,4'hf,0,SLVERR);
        write_reg(8'h04,1,4'h7,0,SLVERR);read_reg(8'h04,OKAY,0,0);
        write_reg(8'h05,0,4'hf,1,SLVERR);write_reg(8'h00,0,4'hf,2,SLVERR);
        write_reg(8'h14,0,4'hf,0,SLVERR);write_reg(8'h18,0,4'hf,0,SLVERR);
        write_reg(8'h20,0,4'hf,0,SLVERR);write_reg(8'h1c,3,4'hf,1,SLVERR);
        write_reg(8'h1c,4,4'hf,2,SLVERR);write_reg(8'h1c,0,4'hf,0,OKAY);
        read_reg(8'h01,SLVERR,0,0);read_reg(8'h0c,SLVERR,0,0);read_reg(8'h10,SLVERR,0,0);read_reg(8'h1c,SLVERR,0,0);read_reg(8'hfc,SLVERR,0,0);
        old_tokens=dut.core.accepted_tokens;write_reg(8'h10,256,4'hf,0,SLVERR);
        if(dut.core.accepted_tokens!=old_tokens)$fatal(1,"Unconfigured token executed");
        configure_stub();old_count=dut.core.accepted_weights;
        write_reg(8'h0c,32'hbad01234,4'hf,0,SLVERR);read_reg(8'h08,OKAY,2,0);
        if(dut.core.accepted_weights!=old_count)$fatal(1,"Rejected model word changed core");
        write_reg(8'h10,320,4'hf,0,SLVERR);write_reg(8'h10,32'h10000,4'hf,1,SLVERR);
        write_reg(8'h10,256,4'h3,2,SLVERR);write_reg(8'h10,0,4'hf,0,SLVERR);
        write_reg(8'h10,256,4'hf,1,OKAY);
        while(!dut.core_logit_valid)begin tick();@(negedge aclk);end
        read_reg(8'h20,OKAY,1,0);
        old_tokens=dut.core.accepted_tokens;old_clear=dut.core.clear_count;
        write_reg(8'h10,77,4'hf,0,SLVERR);write_reg(8'h1c,1,4'hf,2,SLVERR);
        if(dut.core.accepted_tokens!=old_tokens || dut.core.clear_count!=old_clear)$fatal(1,"Busy command had side effect");
        read_reg(8'h14,OKAY,0,0);read_reg(8'h14,OKAY,0,0);
        old_count=dut.core.accepted_logits;old_reset=dut.core.reset_count;
        // Incoming logit-read ownership and a reset execute on the same edge.
        send_both(8'h1c,2,4'hf);
        s_axi_araddr=8'h18;s_axi_arvalid=1;#1;if(!s_axi_arready)$fatal(1,"Simultaneous read not ready");tick();
        @(negedge aclk);s_axi_arvalid=0;finish_b(SLVERR);
        if(!s_axi_rvalid || s_axi_rdata!=synthetic_logit(256,0) || dut.core.reset_count!=old_reset || dut.core.accepted_logits!=old_count)
            $fatal(1,"Simultaneous reset corrupted pending logit read");
        write_reg(8'h1c,2,4'hf,0,SLVERR);
        if(dut.core.reset_count!=old_reset)$fatal(1,"Reset occurred with pending logit read");
        finish_r(OKAY,synthetic_logit(256,0),1);
        for(integer index=1;index<320;index=index+1)begin
            read_reg(8'h14,OKAY,32'(index),0);
            read_reg(8'h18,OKAY,synthetic_logit(256,index),1);
        end
        if(dut.core.accepted_logits!=old_count+320)$fatal(1,"Did not consume all320 logits exactly once");
        read_reg(8'h00,OKAY,32'h21,0);read_reg(8'h20,OKAY,1,0);old_clear=dut.core.clear_count;write_reg(8'h1c,1,4'hf,0,OKAY);
        if(dut.core.clear_count!=old_clear+1)$fatal(1,"Idle context clear did not fire once");
        read_reg(8'h20,OKAY,0,0);
        write_reg(8'h10,77,4'hf,0,SLVERR);write_reg(8'h10,256,4'hf,0,OKAY);
        old_reset=dut.core.reset_count;write_reg(8'h1c,2,4'hf,2,OKAY);
        if(dut.core.reset_count!=old_reset+1)$fatal(1,"Soft reset did not pulse once");read_reg(8'h00,OKAY,32'h40,0);read_reg(8'h20,OKAY,0,0);
        configure_stub();write_reg(8'h10,256,4'hf,0,OKAY);
        // A bus reset abandons a captured, unaccepted read without consuming it.
        send_ar(8'h18);old_count=dut.core.accepted_logits;reset_bus();
        if(dut.core.accepted_logits!=old_count)$fatal(1,"Reset consumed pending logit");
        // Independent AW and W buffers are both discarded by bus reset.
        send_aw(8'h04);reset_bus();send_w(0,4'hf);
        repeat(3)begin tick();@(negedge aclk);if(s_axi_bvalid)$fatal(1,"Reset retained old AW");end
        send_aw(8'h04);finish_b(OKAY);
        send_w(32'hffff,4'hf);reset_bus();send_aw(8'h08);
        repeat(3)begin tick();@(negedge aclk);if(s_axi_bvalid)$fatal(1,"Reset retained old W");end
        send_w(0,4'hf);finish_b(OKAY);configure_stub();
        // Synthetic token319 deliberately produces the stub's FAULT packet.
        write_reg(8'h10,256,4'hf,0,OKAY);
        write_reg(8'h1c,2,4'hf,0,OKAY);configure_stub();
        write_reg(8'h10,256,4'hf,0,OKAY);
        for(integer index=0;index<320;index=index+1)read_reg(8'h18,OKAY,synthetic_logit(256,index),1);
        // Synthetic token318 advances the stub's count directly to256, allowing
        // a fast transport-only check of the ninth count bit/full-capacity flag.
        write_reg(8'h10,318,4'hf,0,OKAY);
        for(integer index=0;index<320;index=index+1)read_reg(8'h18,OKAY,synthetic_logit(318,index),1);
        read_reg(8'h20,OKAY,256,0);read_reg(8'h00,OKAY,1,0);old_tokens=dut.core.accepted_tokens;
        write_reg(8'h10,0,4'hf,0,SLVERR);
        if(dut.core.accepted_tokens!=old_tokens)$fatal(1,"Full-context token was accepted");
        write_reg(8'h1c,1,4'hf,0,OKAY);read_reg(8'h20,OKAY,0,0);read_reg(8'h00,OKAY,32'h21,0);
        write_reg(8'h10,256,4'hf,0,OKAY);
        for(integer index=0;index<320;index=index+1)read_reg(8'h18,OKAY,synthetic_logit(256,index),1);
        write_reg(8'h10,319,4'hf,0,OKAY);
        while(!dut.core_error)begin tick();@(negedge aclk);end
        read_reg(8'h00,OKAY,32'h17,0);old_count=dut.core.accepted_logits;
        send_ar(8'h18);if(s_axi_rresp!=SLVERR)$fatal(1,"FAULT data was exposed as a neural logit");
        write_reg(8'h1c,2,4'hf,0,OKAY);finish_r(SLVERR,0,0);
        if(dut.core.accepted_logits!=old_count)$fatal(1,"FAULT data was consumed");read_reg(8'h00,OKAY,32'h40,0);read_reg(8'h20,OKAY,0,0);
        $fclose(csv);$display("PASS axi protocol_only=1 writes=%0d reads=%0d logit_consumptions=%0d fault_probes=1",writes,reads,dut.core.accepted_logits);$finish;
    end
    initial begin #1000000;$fatal(1,"Absolute AXI test time limit");end
endmodule

// Synthetic bus-test stub. Compile this file instead of the real transformer.sv
// only for protocol tests; the separate real-core elaboration excludes this file.
module transformer (
    input logic clk,reset,input logic weight_valid,output logic weight_ready,
    input logic [3:0] weight_bank,input logic [15:0] weight_address,input logic [31:0] weight_value,
    output logic configured,input logic clear_context,input logic token_valid,output logic token_ready,input logic [8:0] token,
    output logic busy,output logic logit_valid,input logic logit_ready,output logic [8:0] logit_index,
    output logic signed [31:0] logit,output logic saturated,error,output logic [8:0] context_count,output logic [4:0] phase
);
    logic [1:0] loaded,delay_count;
    logic [8:0] current_token;
    logic [31:0] model_memory[0:1];
    integer accepted_weights=0,accepted_tokens=0,accepted_logits=0,clear_count=0,reset_count=0;
    assign weight_ready=!reset && !configured && !token_valid && !clear_context && weight_bank==0 && weight_address=={14'd0,loaded};
    assign token_ready=!reset && configured && !busy && !clear_context && !weight_valid && token<320 && context_count<256 && (context_count!=0 || token==256);
    assign phase=busy ? 5'd1:5'd0;
    always_ff @(posedge clk)begin
        if(reset)begin
            loaded<=0;delay_count<=0;current_token<=0;configured<=0;busy<=0;logit_valid<=0;logit_index<=0;logit<=0;saturated<=0;error<=0;context_count<=0;
            reset_count<=reset_count+1;
        end else begin
            if(weight_valid && weight_ready)begin
                model_memory[loaded[0]]<=weight_value;loaded<=loaded+1'b1;accepted_weights<=accepted_weights+1;
                if(loaded==1)configured<=1;
            end
            if(clear_context && !busy)begin context_count<=0;clear_count<=clear_count+1;end
            if(token_valid && token_ready)begin
                busy<=1;current_token<=token;context_count<=token==318 ? 9'd256 : context_count+1'b1;delay_count<=3;accepted_tokens<=accepted_tokens+1;error<=0;
            end
            if(busy && !logit_valid && delay_count!=0)begin
                delay_count<=delay_count-1'b1;
                if(delay_count==1)begin
                    logit_valid<=1;logit_index<=0;
                    if(current_token==319)begin error<=1;logit<=0;end
                    else logit<=32'(int'(current_token)*65536-1000);
                end
            end
            if(logit_valid && logit_ready && !error)begin
                accepted_logits<=accepted_logits+1;
                if(logit_index==319)begin logit_valid<=0;busy<=0;end
                else begin logit_index<=logit_index+1'b1;logit<=logit+1;end
            end
        end
    end
endmodule
