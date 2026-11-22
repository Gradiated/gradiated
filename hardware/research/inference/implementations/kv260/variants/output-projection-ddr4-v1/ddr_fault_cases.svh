    integer injected_fault = 0;
    logic hold_ar, hold_r;
    integer command_count, response_count;
    logic saw_held_ar;
    logic [48:0] held_araddr;
    always @(posedge aclk) if (aresetn) begin
        if (saw_held_ar && (!m_axi_arvalid || m_axi_araddr != held_araddr))
            $fatal(1,"AXI master withdrew or changed a stalled AR command");
        saw_held_ar <= m_axi_arvalid && !m_axi_arready;
        held_araddr <= m_axi_araddr;
        if (m_axi_arvalid && m_axi_arready) command_count <= command_count + 1;
        if (m_axi_rvalid && m_axi_rready) response_count <= response_count + 1;
    end

    task automatic await_transport(input bit return_phase);
        integer clocks_started;
        clocks_started = 0;
        while (!(return_phase ? m_axi_rready : m_axi_arvalid)) begin
            tick();
            if (++clocks_started > 100000) $fatal(1,"Never reached intended outstanding state");
        end
    endtask

    task automatic qualify_fault;
        logic [31:0] status;
        bit timeout_case, cancel_case, bad_completion;
        timeout_case = injected_fault == 4 || injected_fault == 5;
        cancel_case = injected_fault == 6 || injected_fault == 7;
        bad_completion = injected_fault == 3;
        hold_ar = injected_fault == 4 || injected_fault == 6;
        hold_r = injected_fault == 5 || injected_fault == 7;
        write_reg(8'h30,256,4'hf,0,0,OKAY);
        write_reg(8'h34,0,4'hf,0,0,OKAY);
        write_reg(8'h38,1,4'hf,0,0,OKAY);
        await_transport(!hold_ar);
        if (cancel_case) begin
            check_read(8'h64,3);
            write_reg(8'h64,0,4'hf,0,0,SLVERR);
        end else begin
            status = 0;
            for (int attempt = 0; !status[1] && attempt < 44; attempt++) begin
                repeat(100) tick();
                read_reg(8'h28,0,OKAY,status);
            end
            if (!status[1] || !status[2] || status[11:8] != 5)
                $fatal(1,"Did not terminate with an autonomous fault: %h",status);
            check_read(8'h64,timeout_case || bad_completion ? 7 : 5);
            check_read(8'h68,0);
            check_read(8'h6c,injected_fault == 4 ? 0 : 1);
            check_read(8'h70,timeout_case ? 0 : 1);
            check_read(8'h74,1);
            check_read(8'h84,1);
        end
        write_reg(8'h1c,2,4'hf,0,0,OKAY);
        check_read(8'h60,0);
        check_read(8'h64,(timeout_case || bad_completion || cancel_case) ? 2 : 8);
        check_read(8'h68,0);
        check_read(8'h74,0);
        if (hold_ar || hold_r || bad_completion) begin
            write_reg(8'h60,DDR_BASE,4'hf,0,0,SLVERR);
            if (bad_completion) m_axi_rlast = 1;
            hold_ar = 0;
            hold_r = 0;
            repeat(8) tick();
        end
        check_read(8'h64,8);
        if (command_count != 1 || response_count != (bad_completion ? 2 : 1))
            $fatal(1,"Fault recovery command / response count %d / %d",command_count,response_count);
        check_read(8'h6c,0);
        check_read(8'h70,0);

        // Recover through the normal reconfigure entry point with the same image.
        word_count = 0;
        for (integer bank=0;bank<15;bank=bank+1) begin
            if (bank_length(bank)!=0) begin
                write_reg(8'h04,32'(bank),4'hf,1,0,OKAY);write_reg(8'h08,0,4'hf,2,0,OKAY);
                for (integer address=0;address<bank_length(bank);address=address+1) begin
                    write_reg(8'h0c,words[word_count],4'hf,0,0,OKAY);word_count=word_count+1;
                end
            end
        end
        run_bos(0);
        if (command_count != 1) $fatal(1,"Recovered BRAM arm started an AXI command");
        $display("PASS DDR fault or cancel %0d, commands=%0d beats=%0d",injected_fault,command_count,response_count);
        $finish;
    endtask
