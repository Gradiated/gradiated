// REAL neural core through the REAL AXI adapter. No synthetic transformer stub.
// SCORES is a prior actual-RTL BOS trace for transport consistency, not a claim
// of independent original Mac full-model golden validation.
`timescale 1ns/1ps
module axi_transformer_core_tb;
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
    localparam integer MODEL_WORDS=29281;
    logic [31:0] words[0:MODEL_WORDS-1];
    logic signed [31:0] scores[0:319];
    integer events,returned,request_id=-1,write_count=0,read_count=0,word_count=0,score_count=0;
    integer write_stall_edges=0,read_stall_edges=0;
    string modelfile,scorefile,eventfile,returnfile,wavefile;
    localparam logic [1:0] OKAY=0,SLVERR=2;
    task automatic tick;
        @(posedge aclk);#1;
    endtask
    task automatic quiet;
        s_axi_awvalid=0;s_axi_wvalid=0;s_axi_bready=0;s_axi_arvalid=0;s_axi_rready=0;
    endtask
    task automatic bus_event(input string kind,input integer address,input logic [31:0] data,input logic [1:0] response);
        $fwrite(events,"%0d,%0d,%s,%0d,%0d,%0d\n",int'($time/10),request_id,kind,address,data,response);
    endtask
    always @(posedge aclk)if(aresetn)begin
        if(s_axi_awvalid && s_axi_awready)bus_event("AW",int'(s_axi_awaddr),0,0);
        if(s_axi_wvalid && s_axi_wready)bus_event("W",0,s_axi_wdata,{1'b0,s_axi_wstrb!=4'hf});
        if(s_axi_bvalid && s_axi_bready)bus_event("B",0,0,s_axi_bresp);
        if(s_axi_arvalid && s_axi_arready)bus_event("AR",int'(s_axi_araddr),0,0);
        if(s_axi_rvalid && s_axi_rready)bus_event("R",0,s_axi_rdata,s_axi_rresp);
    end
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
    task automatic send_aw(input logic [7:0] address);
        @(negedge aclk);s_axi_awaddr=address;s_axi_awvalid=1;
        #1;if(!s_axi_awready)$fatal(1,"Real-core AW not ready");tick();
        @(negedge aclk);s_axi_awvalid=0;
    endtask
    task automatic send_w(input logic [31:0] data,input logic [3:0] strobe);
        @(negedge aclk);s_axi_wdata=data;s_axi_wstrb=strobe;s_axi_wvalid=1;
        #1;if(!s_axi_wready)$fatal(1,"Real-core W not ready");tick();
        @(negedge aclk);s_axi_wvalid=0;
    endtask
    task automatic write_reg(input logic [7:0] address,input logic [31:0] data,input logic [3:0] strobe,
                             input integer order,input integer stalls,input logic [1:0] wanted);
        integer watchdog;
        if(order==1)begin send_aw(address);send_w(data,strobe);end
        else if(order==2)begin send_w(data,strobe);send_aw(address);end
        else begin
            @(negedge aclk);s_axi_awaddr=address;s_axi_awvalid=1;s_axi_wdata=data;s_axi_wstrb=strobe;s_axi_wvalid=1;
            #1;if(!s_axi_awready || !s_axi_wready)$fatal(1,"Real-core write channels not ready");tick();
            @(negedge aclk);s_axi_awvalid=0;s_axi_wvalid=0;
        end
        watchdog=0;
        while(!s_axi_bvalid)begin tick();@(negedge aclk);watchdog=watchdog+1;if(watchdog>20)$fatal(1,"No real-core B response");end
        if(s_axi_bresp!=wanted)$fatal(1,"Real-core B response %0d wanted %0d at offset %0h model word %0d",s_axi_bresp,wanted,address,word_count);
        repeat(stalls)begin
            tick();write_stall_edges=write_stall_edges+1;
            if(!s_axi_bvalid || s_axi_bresp!=wanted || s_axi_awready || s_axi_wready)$fatal(1,"Real-core B response changed during stall");
            @(negedge aclk);
        end
        s_axi_bready=1;tick();if(s_axi_bvalid)$fatal(1,"Real-core B response not accepted");
        @(negedge aclk);s_axi_bready=0;write_count=write_count+1;
    endtask
    task automatic read_reg(input logic [7:0] address,input integer stalls,input logic [1:0] wanted,output logic [31:0] data);
        logic [31:0] held;
        @(negedge aclk);s_axi_araddr=address;s_axi_arvalid=1;
        #1;if(!s_axi_arready)$fatal(1,"Real-core AR not ready");tick();
        @(negedge aclk);s_axi_arvalid=0;
        if(!s_axi_rvalid || s_axi_rresp!=wanted)$fatal(1,"Real-core R response differs at offset %0h",address);
        held=s_axi_rdata;
        repeat(stalls)begin
            tick();read_stall_edges=read_stall_edges+1;
            if(!s_axi_rvalid || s_axi_rresp!=wanted || s_axi_rdata!=held || s_axi_arready)$fatal(1,"Real-core R response changed during stall");
            @(negedge aclk);
        end
        data=held;s_axi_rready=1;tick();if(s_axi_rvalid)$fatal(1,"Real-core R response not accepted");
        @(negedge aclk);s_axi_rready=0;read_count=read_count+1;
    endtask
    task automatic check_read(input logic [7:0] address,input logic [31:0] wanted);
        logic [31:0] data;
        read_reg(address,2,OKAY,data);if(data!=wanted)$fatal(1,"Real-core register %0h got %0h wanted %0h",address,data,wanted);
    endtask
    task automatic wait_logit;
        logic [31:0] status;
        integer polls;
        status=0;polls=0;
        while(!status[4])begin
            read_reg(8'h00,0,OKAY,status);polls=polls+1;
            if(!status[0] || !status[1] || status[2] || status[5] || status[6] || status[31:7]!=0)
                $fatal(1,"Invalid busy real-core status %0h",status);
            if(polls>150000)$fatal(1,"Bounded real-core status polling exceeded");
        end
    endtask
    task automatic run_bos(input integer id);
        logic [31:0] index_word,data,status;
        request_id=id;check_read(8'h20,0);check_read(8'h00,32'h21);
        write_reg(8'h10,0,4'hf,1,2,SLVERR);check_read(8'h20,0);
        write_reg(8'h10,256,4'hf,2,3,OKAY);
        for(integer index=0;index<320;index=index+1)begin
            wait_logit();read_reg(8'h14,1+(index%3),OKAY,index_word);
            if(index_word!=32'(index))$fatal(1,"Real-core AXI index mismatch");
            read_reg(8'h18,1+(index%4),OKAY,data);
            if($signed(data)!=scores[index])$fatal(1,"Real-core AXI transport score mismatch at %0d: got %0d wanted %0d",index,$signed(data),scores[index]);
            $fwrite(returned,"%0d,%0d,%0d\n",id,index,$signed(data));score_count=score_count+1;
        end
        read_reg(8'h00,2,OKAY,status);
        if(status!=32'h21)$fatal(1,"Real-core did not return configured idle capacity");
        check_read(8'h20,1);
    endtask
    initial begin
        logic [31:0] data;
        if(!$value$plusargs("MODEL=%s",modelfile) || !$value$plusargs("SCORES=%s",scorefile) ||
           !$value$plusargs("CSV=%s",eventfile) || !$value$plusargs("RETURNS=%s",returnfile) ||
           !$value$plusargs("VCD=%s",wavefile))$fatal(1,"Missing real-core AXI fixtures");
        $readmemh(modelfile,words);$readmemh(scorefile,scores);
        events=$fopen(eventfile,"w");returned=$fopen(returnfile,"w");if(events==0 || returned==0)$fatal(1,"Cannot open actual AXI traces");
        $fwrite(events,"cycle,request,kind,address,data,response\n");$fwrite(returned,"request,index,score\n");
        $dumpfile(wavefile);$dumpvars(0,dut);
        repeat(2)begin tick();@(negedge aclk);end aresetn=1;
        check_read(8'h00,32'h40);check_read(8'h20,0);
        // Actual ordered-loader refusal, before any model words enter the core.
        write_reg(8'h08,1,4'hf,0,2,OKAY);write_reg(8'h0c,words[0],4'hf,0,2,SLVERR);check_read(8'h08,1);
        write_reg(8'h08,0,4'hf,0,0,OKAY);write_reg(8'h0c,words[0],4'h3,0,2,SLVERR);check_read(8'h08,0);
        for(integer bank=0;bank<15;bank=bank+1)begin
            if(bank_length(bank)!=0)begin
                write_reg(8'h04,32'(bank),4'hf,1,2,OKAY);write_reg(8'h08,0,4'hf,2,1,OKAY);
                for(integer address=0;address<bank_length(bank);address=address+1)begin
                    write_reg(8'h0c,words[word_count],4'hf,address%257==0 ? (address%3):0,address%257==0 ? 3:0,OKAY);
                    word_count=word_count+1;
                end
                check_read(8'h08,32'(bank_length(bank)));check_read(8'h00,bank==14 ? 32'h21:32'h40);
            end
        end
        if(word_count!=MODEL_WORDS)$fatal(1,"Not all real model words passed AXI");
        run_bos(0);
        request_id=-1;write_reg(8'h1c,1,4'hf,0,3,OKAY);check_read(8'h20,0);check_read(8'h00,32'h21);
        run_bos(1);
        // Empty DATA reads cannot duplicate the last neural score.
        read_reg(8'h18,2,SLVERR,data);if(data!=0)$fatal(1,"Empty AXI data returned a stale score");
        $fclose(events);$fclose(returned);
        $display("PASS axi_real_core requests=2 model_words=%0d logits=%0d writes=%0d reads=%0d B_stalls=%0d R_stalls=%0d",word_count,score_count,write_count,read_count,write_stall_edges,read_stall_edges);
        $finish;
    end
    initial begin #200000000;$fatal(1,"Absolute real-core AXI simulation limit");end
endmodule
