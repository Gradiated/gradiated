// REAL neural core through the REAL AXI adapter. No synthetic transformer stub.
// SCORES is a prior actual-RTL BOS trace for transport consistency, not a claim
// of independent original Mac full-model golden validation.
`timescale 1ns/1ps
module autonomous_core_tb;
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
    logic [8:0] expected_input[0:255],expected_output[0:255];
    logic signed [31:0] expected_scores[0:81919];
    integer prefix_len,outputs,positions,cap,reason,seen_inputs=0,seen_scores=0;
    bit observing=0;
    string inputfile,outputfile,allscorefile;
    always @(posedge aclk)if(aresetn && observing)begin
        if(dut.selected_valid && dut.core_token_ready)begin
            if(seen_inputs>=positions || dut.selected_token!=expected_input[seen_inputs])
                $fatal(1,"Autonomous input sequence mismatch at %0d",seen_inputs);
            seen_inputs=seen_inputs+1;
        end
        if(dut.core_logit_valid && dut.selected_ready)begin
            if(seen_scores>=positions*320 || dut.core_logit_index!=9'(seen_scores%320) ||
                dut.core_logit!=expected_scores[seen_scores])
                $fatal(1,"Autonomous score mismatch at %0d: got %0d wanted %0d",seen_scores,dut.core_logit,expected_scores[seen_scores]);
            seen_scores=seen_scores+1;
        end
    end
    initial begin
        logic [31:0] data,status;
        integer polls;
        if(!$value$plusargs("MODEL=%s",modelfile) || !$value$plusargs("SCORES=%s",scorefile) ||
           !$value$plusargs("CSV=%s",eventfile) || !$value$plusargs("RETURNS=%s",returnfile) ||
           !$value$plusargs("INPUT=%s",inputfile) || !$value$plusargs("OUTPUT=%s",outputfile) ||
           !$value$plusargs("ALLSCORES=%s",allscorefile) || !$value$plusargs("PREFIX=%d",prefix_len) ||
           !$value$plusargs("OUTPUTS=%d",outputs) || !$value$plusargs("POSITIONS=%d",positions) ||
           !$value$plusargs("CAP=%d",cap) || !$value$plusargs("REASON=%d",reason))$fatal(1,"Missing fixtures");
        $readmemh(modelfile,words);$readmemh(scorefile,scores);
        $readmemh(inputfile,expected_input);$readmemh(outputfile,expected_output);$readmemh(allscorefile,expected_scores);
        events=$fopen(eventfile,"w");returned=$fopen(returnfile,"w");
        repeat(2)begin tick();@(negedge aclk);end aresetn=1;
        for(integer bank=0;bank<15;bank=bank+1)begin
            if(bank_length(bank)!=0)begin
                write_reg(8'h04,32'(bank),4'hf,1,0,OKAY);write_reg(8'h08,0,4'hf,2,0,OKAY);
                for(integer address=0;address<bank_length(bank);address=address+1)begin
                    write_reg(8'h0c,words[word_count],4'hf,0,0,OKAY);word_count=word_count+1;
                end
            end
        end
        if(word_count!=MODEL_WORDS)$fatal(1,"Missing weights");
        // Original full-score host interface remains usable before autonomous mode.
        run_bos(0);write_reg(8'h1c,1,4'hf,0,0,OKAY);
        check_read(8'h24,32'h41553031);
        for(integer i=0;i<prefix_len;i=i+1)write_reg(8'h30,32'(expected_input[i]),4'hf,i%3,0,OKAY);
        write_reg(8'h34,32'(cap),4'hf,0,0,OKAY);
        observing=1;write_reg(8'h38,1,4'hf,0,0,OKAY);
        polls=0;status=0;
        while(!status[1])begin
            repeat(1000)tick();read_reg(8'h28,0,OKAY,status);polls=polls+1;
            if(status[2] || polls>200000)$fatal(1,"Autonomous fault/deadline status %0h",status);
        end
        observing=0;
        if(status[11:8]!=4'(reason) || seen_inputs!=positions || seen_scores!=positions*320)
            $fatal(1,"Autonomous terminal geometry: status %0h inputs %0d scores %0d",status,seen_inputs,seen_scores);
        check_read(8'h54,32'(positions));check_read(8'h58,32'(positions*320));check_read(8'h20,32'(positions));
        check_read(8'h3c,32'(outputs));check_read(8'h44,32'(outputs));
        if(outputs>0 && (!status[4] || !status[5]))$fatal(1,"Missing byte timestamps");
        if(outputs==0 && (status[4] || status[5]))$fatal(1,"Invented byte timestamps");
        for(integer i=0;i<outputs;i=i+1)begin
            read_reg(8'h40,i%7,OKAY,data);
            if(data!=32'(expected_output[i]))$fatal(1,"Output mismatch at %0d",i);
        end
        check_read(8'h44,0);read_reg(8'h40,2,SLVERR,data);
        write_reg(8'h1c,1,4'hf,0,0,OKAY);check_read(8'h28,0);check_read(8'h20,0);check_read(8'h2c,0);
        // Another real BOS request verifies next-request isolation and legacy restoration.
        run_bos(1);
        $fclose(events);$fclose(returned);
        $display("PASS autonomous_real_core positions=%0d exact_scores=%0d outputs=%0d reason=%0d legacy_BOS_scores=640",positions,seen_scores,outputs,reason);
        $finish;
    end
    initial begin #3000000000;$fatal(1,"Absolute real-core simulation cycle limit");end
endmodule
